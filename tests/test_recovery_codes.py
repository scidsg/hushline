import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pyotp
import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.auth import (
    RECOVERY_CODES_PENDING_ACK_SESSION_KEY,
    STRONG_AUTHENTICATION_SESSION_KEY,
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY,
)
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    ChatKey,
    PasswordResetToken,
    RecoveryCode,
    RecoveryCodeBatch,
    User,
    WebAuthnCredential,
)
from hushline.recovery_codes import (
    RECOVERY_CODE_COUNT,
    acknowledge_recovery_codes,
    consume_recovery_code,
    generate_recovery_codes,
    has_usable_recovery_codes,
    hash_recovery_code,
)
from hushline.webauthn import WebAuthnPurpose


def _credential(user: User, marker: bytes = b"recovery-key") -> WebAuthnCredential:
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=marker,
        public_key=b"public-key-" + marker,
        algorithm=-7,
        sign_count=0,
        transports=["usb"],
        device_type="single_device",
        backed_up=False,
        name="Backup key",
        created_at=datetime.now(UTC),
    )
    db.session.add(credential)
    db.session.commit()
    return credential


def _password_login(client: FlaskClient, user: User, password: str) -> None:
    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("verify_2fa_login"))


def _persist_codes(user: User) -> list[str]:
    batch, codes = generate_recovery_codes(user)
    assert acknowledge_recovery_codes(user_id=user.id, batch_id=batch.id)
    db.session.commit()
    return codes


def _generate_codes_from_settings(
    client: FlaskClient, user: User, password: str
) -> tuple[list[str], int]:
    totp_secret = user.totp_secret
    assert totp_secret is not None
    response = client.post(
        url_for("settings.authorize_security_key"),
        data={
            "password": password,
            "verification_code": pyotp.TOTP(totp_secret).now(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.post(
        url_for("settings.generate_security_key_recovery_codes"),
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    soup = BeautifulSoup(response.text, "html.parser")
    codes = [item.get_text(strip=True) for item in soup.select("#recovery-code-list code")]
    with client.session_transaction() as session:
        pending = session[RECOVERY_CODES_PENDING_ACK_SESSION_KEY]
        batch_id = pending["batch_id"]
    return codes, batch_id


def _acknowledge_settings_codes(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.acknowledge_security_key_recovery_codes"),
        data={"saved_codes": "y"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@pytest.mark.usefixtures("_authenticated_user")
def test_generation_displays_high_entropy_codes_once_and_requires_acknowledgement(
    client: FlaskClient,
    user: User,
    user_password: str,
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()

    codes, batch_id = _generate_codes_from_settings(client, user, user_password)

    assert len(codes) == RECOVERY_CODE_COUNT
    assert len(set(codes)) == RECOVERY_CODE_COUNT
    assert all(re.fullmatch(r"(?:[A-Z2-7]{4}-){7}[A-Z2-7]{4}", code) for code in codes)
    stored_codes = db.session.scalars(
        db.select(RecoveryCode).where(RecoveryCode.batch_id == batch_id)
    ).all()
    assert len(stored_codes) == RECOVERY_CODE_COUNT
    assert all(code.encode("ascii") != row.code_hash for code, row in zip(codes, stored_codes))
    assert not has_usable_recovery_codes(user.id)

    refreshed = client.get(url_for("settings.security_keys"))
    assert all(code not in refreshed.text for code in codes)

    original_session_id = user.session_id
    _acknowledge_settings_codes(client)
    db.session.refresh(user)
    batch = db.session.get(RecoveryCodeBatch, batch_id)
    assert batch is not None
    assert batch.acknowledged_at is not None
    assert user.session_id != original_session_id
    assert has_usable_recovery_codes(user.id)
    with client.session_transaction() as session:
        assert session["session_id"] == user.session_id
        assert RECOVERY_CODES_PENDING_ACK_SESSION_KEY not in session


@pytest.mark.usefixtures("_authenticated_user")
def test_regeneration_invalidates_old_codes_before_new_set_is_acknowledged(
    client: FlaskClient,
    user: User,
    user_password: str,
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()
    old_codes, old_batch_id = _generate_codes_from_settings(client, user, user_password)
    _acknowledge_settings_codes(client)

    new_codes, new_batch_id = _generate_codes_from_settings(client, user, user_password)

    old_batch = db.session.get(RecoveryCodeBatch, old_batch_id)
    assert old_batch is not None
    assert old_batch.invalidated_at is not None
    assert not consume_recovery_code(user_id=user.id, value=old_codes[0])
    assert not consume_recovery_code(user_id=user.id, value=new_codes[0])
    db.session.rollback()

    _acknowledge_settings_codes(client)
    assert consume_recovery_code(user_id=user.id, value=new_codes[0])
    db.session.commit()
    assert not consume_recovery_code(user_id=user.id, value=new_codes[0])
    db.session.rollback()
    assert new_batch_id != old_batch_id


@pytest.mark.usefixtures("_authenticated_user")
def test_acknowledgement_revokes_sibling_session_but_preserves_current_session(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()
    sibling = app.test_client()
    with sibling.session_transaction() as session:
        session.update(
            user_id=user.id,
            session_id=user.session_id,
            username=user.primary_username.username,
            is_authenticated=True,
        )
    _generate_codes_from_settings(client, user, user_password)

    _acknowledge_settings_codes(client)

    assert client.get(url_for("settings.security_keys")).status_code == 200
    sibling_response = sibling.get(url_for("settings.security_keys"), follow_redirects=False)
    assert sibling_response.status_code == 302
    assert sibling_response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_key_only_policy_requires_security_key_for_recovery_policy_changes(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    _credential(user, b"lost-primary-key")
    backup_credential = _credential(user, b"backup-key")
    response = client.post(
        url_for("settings.authorize_security_key"),
        data={"password": user_password, "verification_code": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY in session
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session

    begin = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.begin_authentication",
        return_value={
            "challenge": "challenge",
            "allowCredentials": [],
            "userVerification": "required",
        },
    )
    options = client.post(url_for("settings.security_key_authorization_options"), json={})
    assert options.status_code == 200
    assert begin.call_args.kwargs["purpose"] is WebAuthnPurpose.RECOVERY

    finish = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
        return_value=backup_credential,
    )
    verified = client.post(
        url_for("settings.verify_security_key_authorization"),
        json={"credential": {"rawId": "backup-key"}},
    )
    assert verified.status_code == 200
    assert finish.call_args.kwargs["purpose"] is WebAuthnPurpose.RECOVERY
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY in session
        assert WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY not in session


def test_recovery_code_login_is_single_use_account_bound_and_records_strong_authentication(
    client: FlaskClient,
    user: User,
    user2: User,
    user_password: str,
) -> None:
    _credential(user)
    _credential(user2, b"other-recovery-key")
    codes = _persist_codes(user)
    other_codes = _persist_codes(user2)
    _password_login(client, user, user_password)

    cross_account = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": other_codes[0]},
    )
    assert cross_account.status_code == 401
    assert other_codes[0] not in cross_account.text
    other_row = db.session.scalar(
        db.select(RecoveryCode).where(
            RecoveryCode.code_hash == hash_recovery_code(user2.id, other_codes[0])
        )
    )
    assert other_row is not None
    assert other_row.consumed_at is None

    response = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": codes[0].lower()},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["is_authenticated"] is True
        assert session[STRONG_AUTHENTICATION_SESSION_KEY]["method"] == "recovery_code"

    client.get(url_for("logout"))
    _password_login(client, user, user_password)
    replay = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": codes[0]},
    )
    assert replay.status_code == 401


def test_recovered_session_can_replace_lost_key_after_password_reauthentication(
    client: FlaskClient, user: User, user_password: str
) -> None:
    lost_key = _credential(user, b"lost-key-to-remove")
    codes = _persist_codes(user)
    _password_login(client, user, user_password)
    recovered = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": codes[0]},
        follow_redirects=False,
    )
    assert recovered.status_code == 302

    authorized = client.post(
        url_for("settings.authorize_security_key"),
        data={"password": user_password, "verification_code": ""},
        follow_redirects=False,
    )
    assert authorized.status_code == 302
    _credential(user, b"replacement-key")
    original_session_id = user.session_id
    removed = client.post(
        url_for("settings.remove_security_key"),
        data={"credential_id": str(lost_key.id)},
        follow_redirects=False,
    )

    assert removed.status_code == 302
    db.session.refresh(lost_key)
    db.session.refresh(user)
    assert lost_key.disabled_at is not None
    assert user.session_id != original_session_id
    with client.session_transaction() as session:
        assert session["session_id"] == user.session_id


def test_recovery_code_attempts_are_rate_limited_without_consuming_valid_code(
    client: FlaskClient, user: User, user_password: str
) -> None:
    _credential(user)
    codes = _persist_codes(user)
    db.session.add_all([AuthenticationLog(user_id=user.id, successful=False) for _ in range(5)])
    db.session.commit()
    _password_login(client, user, user_password)

    response = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": codes[0]},
    )

    assert response.status_code == 429
    assert has_usable_recovery_codes(user.id)


def test_recovery_code_login_requires_csrf_without_consuming_code(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    _credential(user)
    codes = _persist_codes(user)
    _password_login(client, user, user_password)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("verify_recovery_code_login"),
            data={"recovery_code": codes[0]},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    stored = db.session.scalar(
        db.select(RecoveryCode).where(
            RecoveryCode.code_hash == hash_recovery_code(user.id, codes[0])
        )
    )
    assert stored is not None
    assert stored.consumed_at is None


def test_atomic_consumption_allows_only_one_concurrent_winner(app: Flask, user: User) -> None:
    code = _persist_codes(user)[0]
    user_id = user.id
    barrier = Barrier(2)

    def attempt() -> bool:
        with app.app_context():
            barrier.wait()
            consumed = consume_recovery_code(user_id=user_id, value=code)
            if consumed:
                db.session.commit()
            else:
                db.session.rollback()
            db.session.remove()
            return consumed

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: attempt(), range(2)))

    assert sorted(results) == [False, True]


def test_exhausted_codes_are_removed_from_later_login_policy(
    client: FlaskClient, user: User, user_password: str
) -> None:
    _credential(user)
    codes = _persist_codes(user)
    for code in codes:
        assert consume_recovery_code(user_id=user.id, value=code)
        db.session.commit()
    assert not has_usable_recovery_codes(user.id)

    _password_login(client, user, user_password)
    response = client.get(url_for("verify_2fa_login"))

    assert 'action="/verify-recovery-code-login"' not in response.text
    assert "Use your security key" in response.text


def test_password_reset_does_not_bypass_factor_or_unlock_recovery_boundary(
    client: FlaskClient, user: User
) -> None:
    _credential(user)
    codes = _persist_codes(user)
    chat_key = ChatKey(
        user_id=user.id,
        key_version=1,
        public_key="public-chat-key",
        encrypted_private_key='{"algorithm":"AES-GCM","iv":"old","ciphertext":"old"}',
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000, "hash": "SHA-256"},
        kdf_salt="old-salt",
        wrapping_algorithm="AES-GCM",
    )
    token, raw_token = PasswordResetToken.create_for_user(user.id, ttl=timedelta(hours=1))
    db.session.add_all([chat_key, token])
    db.session.commit()

    response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": "ResetPassword123!!"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    _password_login(client, user, "ResetPassword123!!")
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False

    response = client.post(
        url_for("verify_recovery_code_login"),
        data={"recovery_code": codes[0]},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["is_authenticated"] is True
    db.session.refresh(chat_key)
    assert chat_key.recovery_state == "password_reset_locked"
    assert ChatKey.active_for_user_id(user.id) is None


def test_missing_all_factors_guidance_disclaims_server_recovery(
    client: FlaskClient, user: User, user_password: str
) -> None:
    _credential(user)
    _password_login(client, user, user_password)

    response = client.get(url_for("verify_2fa_login"))

    assert "Lost access to all authentication factors?" in response.text
    assert "support and administrators cannot bypass" in response.text
    assert "cannot" in response.text
    assert "recover encrypted message history" in response.text
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp

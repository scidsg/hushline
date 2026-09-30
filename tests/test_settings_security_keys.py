import base64
import json
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pyotp
import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.auth import (
    STRONG_AUTHENTICATION_SESSION_KEY,
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
)
from hushline.config import WEBAUTHN_ENROLLMENT_ENABLED
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    RecoveryCodeBatch,
    User,
    WebAuthnChallenge,
    WebAuthnCredential,
    WebAuthnUserHandle,
)
from hushline.webauthn import (
    WebAuthnPurpose,
    WebAuthnVerificationError,
    _session_binding_hash,
)

WEBAUTHN_FIXTURE_PATH = Path(__file__).parent / "testdata" / "webauthn-ceremonies.json"
SESSION_BINDING = "settings-session-binding-that-is-long-enough"


def _authorize(client: FlaskClient, password: str, code: str = "") -> None:
    response = client.post(
        url_for("settings.authorize_security_key"),
        data={"password": password, "verification_code": code},
        follow_redirects=False,
    )
    assert response.status_code == 302


def _mark_recent_strong_authentication(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session[STRONG_AUTHENTICATION_SESSION_KEY] = {
            "authenticated_at": int(time.time()),
            "method": "security_key",
            "session_id": user.session_id,
            "user_id": user.id,
        }


def _credential(user: User, marker: bytes, name: str) -> WebAuthnCredential:
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=marker,
        public_key=b"public-key-" + marker,
        algorithm=-7,
        sign_count=0,
        transports=["usb"],
        device_type="single_device",
        backed_up=False,
        name=name,
        created_at=datetime.now(UTC),
    )
    db.session.add(credential)
    db.session.commit()
    return credential


def _decode_base64url(value: str) -> bytes:
    encoded = value.encode("ascii")
    return base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))


def _registration_fixture() -> tuple[bytes, dict[str, object]]:
    fixture = json.loads(WEBAUTHN_FIXTURE_PATH.read_text(encoding="utf-8"))["registration"]
    challenge = fixture["challenge"]
    response = fixture["response"]
    assert isinstance(challenge, str)
    assert isinstance(response, dict)
    return _decode_base64url(challenge), response


@pytest.mark.usefixtures("_authenticated_user")
def test_security_key_settings_lists_keys_and_recovery_guidance(
    client: FlaskClient, user: User
) -> None:
    _credential(user, b"primary-key", "Office USB key")
    _credential(user, b"backup-key", "Backup NFC key")

    response = client.get(url_for("settings.security_keys"))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert "Office USB key" in response.text
    assert "Backup NFC key" in response.text
    assert "Register at least two" in response.text
    assert "keep the backup in a separate safe place" in response.text
    soup = BeautifulSoup(response.text, "html.parser")
    current_tab = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current_tab is not None
    assert current_tab.get_text(strip=True) == "Authentication"


@pytest.mark.usefixtures("_authenticated_user")
def test_security_key_list_shows_last_use_without_exposing_credential_material(
    client: FlaskClient, user: User
) -> None:
    used = _credential(user, b"used-key", "Used key")
    used.last_used_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    unused = _credential(user, b"unused-key", "Unused key")
    db.session.commit()

    response = client.get(url_for("settings.security_keys"))

    assert response.status_code == 200
    assert "Last used" in response.text
    assert "2026-01-02 03:04 UTC" in response.text
    assert "Never used" in response.text
    assert base64.urlsafe_b64encode(used.credential_id).decode() not in response.text
    assert base64.urlsafe_b64encode(unused.public_key).decode() not in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_enrollment_requires_current_password(client: FlaskClient, user_password: str) -> None:
    _authorize(client, "wrong-password")
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session

    _authorize(client, user_password)
    response = client.get(url_for("settings.security_keys"))
    assert response.status_code == 200
    assert 'id="security-key-enrollment-form"' in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_mfa_account_requires_existing_totp_factor(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()

    _authorize(client, user_password, "abcdef")
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session

    _authorize(client, user_password, pyotp.TOTP(user.totp_secret).now())
    response = client.get(url_for("settings.security_keys"))
    assert 'id="security-key-enrollment-form"' in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_security_key_success_does_not_hide_reused_totp_reauthentication(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = pyotp.random_base32()
    totp = pyotp.TOTP(user.totp_secret)
    code = totp.now()
    now = datetime.now()
    timecode = totp.timecode(now)
    prior_totp = AuthenticationLog(
        user_id=user.id,
        successful=True,
        otp_code=code,
        timecode=timecode,
    )
    prior_totp.timestamp = now - timedelta(seconds=1)
    # Non-TOTP successes do not store an OTP code or timecode.
    later_security_key = AuthenticationLog(user_id=user.id, successful=True)
    later_security_key.timestamp = now
    db.session.add_all([prior_totp, later_security_key])
    db.session.commit()

    response = client.post(
        url_for("settings.authorize_security_key"),
        data={"password": user_password, "verification_code": code},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session


@pytest.mark.usefixtures("_authenticated_user")
def test_registration_options_require_recent_account_bound_authorization(
    client: FlaskClient,
    user: User,
    user2: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    begin_registration = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.begin_registration",
        return_value={"challenge": "challenge"},
    )
    options_url = url_for("settings.security_key_registration_options")

    assert client.post(options_url, json={"name": "Office key"}).status_code == 403

    _authorize(client, user_password)
    with client.session_transaction() as session:
        authorization = session[WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY]
        authorization["authorized_at"] = int(time.time()) - 301
        session[WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY] = authorization
    assert client.post(options_url, json={"name": "Office key"}).status_code == 403

    _authorize(client, user_password)
    with client.session_transaction() as session:
        session["user_id"] = user2.id
        session["session_id"] = user2.session_id
        session["username"] = user2.primary_username.username
    assert client.post(options_url, json={"name": "Office key"}).status_code == 403
    begin_registration.assert_not_called()

    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
    _authorize(client, user_password)
    response = client.post(options_url, json={"name": "  Office key  "})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert begin_registration.call_args.kwargs["user"].id == user.id
    assert begin_registration.call_args.kwargs["username"] == user.primary_username.username


@pytest.mark.usefixtures("_authenticated_user")
def test_enrollment_kill_switch_blocks_only_new_credentials(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    credential = _credential(user, b"existing-key", "Existing key")
    app.config[WEBAUTHN_ENROLLMENT_ENABLED] = False
    begin = mocker.patch("hushline.webauthn.WebAuthnCeremonyService.begin_registration")
    finish = mocker.patch("hushline.webauthn.WebAuthnCeremonyService.finish_registration")

    page = client.get(url_for("settings.security_keys"))
    _mark_recent_strong_authentication(client, user)
    _authorize(client, user_password)
    options = client.post(
        url_for("settings.security_key_registration_options"),
        json={"name": "Blocked key"},
    )
    verification = client.post(
        url_for("settings.verify_security_key_registration"),
        json={"name": "Blocked key", "credential": {"id": "blocked"}},
    )

    assert page.status_code == 200
    assert "New security key enrollment is currently paused" in page.text
    assert 'id="security-key-enrollment-form"' not in page.text
    assert "Existing key" in page.text
    assert options.status_code == 503
    assert verification.status_code == 503
    assert options.headers["Cache-Control"] == "no-store"
    assert verification.headers["Cache-Control"] == "no-store"
    begin.assert_not_called()
    finish.assert_not_called()
    db.session.refresh(credential)
    assert credential.disabled_at is None


@pytest.mark.usefixtures("_authenticated_user")
def test_registration_rejects_invalid_label_and_bounded_key_count(
    client: FlaskClient, app: Flask, user: User, user_password: str
) -> None:
    app.config["WEBAUTHN_MAX_CREDENTIALS_PER_USER"] = 2
    _authorize(client, user_password)
    options_url = url_for("settings.security_key_registration_options")
    assert client.post(options_url, json={"name": " "}).status_code == 400
    assert client.post(options_url, json={"name": "x" * 101}).status_code == 400

    _credential(user, b"first-key", "First key")
    _credential(user, b"second-key", "Second key")
    response = client.post(options_url, json={"name": "Third key"})
    assert response.status_code == 409
    assert response.json == {"error": "The security key limit has been reached."}


@pytest.mark.usefixtures("_authenticated_user")
def test_verification_stores_only_verified_key_and_consumes_authorization(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    verify_url = url_for("settings.verify_security_key_registration")
    payload = {"name": "Office key", "credential": {"id": "response"}}
    finish_registration = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_registration",
        side_effect=WebAuthnVerificationError("invalid"),
    )
    _authorize(client, user_password)

    response = client.post(verify_url, json=payload)

    assert response.status_code == 400
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
        )
        == 0
    )
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session

    credential = _credential(user, b"verified-key", "Office key")
    finish_registration.side_effect = None
    finish_registration.return_value = credential
    _mark_recent_strong_authentication(client, user)
    _authorize(client, user_password)
    response = client.post(verify_url, json=payload)
    assert response.status_code == 201
    response_json = response.get_json()
    assert isinstance(response_json, dict)
    assert "backup key" in response_json["message"]
    with client.session_transaction() as session:
        assert WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY not in session


@pytest.mark.usefixtures("_authenticated_user")
def test_registration_route_verifies_persists_and_rejects_replay(
    client: FlaskClient,
    app: Flask,
    user: User,
    user_password: str,
) -> None:
    app.config.update(
        WEBAUTHN_RP_ID="localhost",
        WEBAUTHN_ORIGIN="http://localhost:5000",
        WEBAUTHN_RP_NAME="Hush Line Test",
    )
    challenge, registration_response = _registration_fixture()
    now = datetime.now(UTC)
    user.webauthn_user_handle = WebAuthnUserHandle()
    db.session.add(
        WebAuthnChallenge(
            user_id=user.id,
            purpose=WebAuthnPurpose.REGISTRATION.value,
            challenge_hash=sha256(challenge).digest(),
            session_binding_hash=_session_binding_hash(SESSION_BINDING),
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )
    db.session.commit()
    with client.session_transaction() as session:
        session[WEBAUTHN_SESSION_BINDING_KEY] = SESSION_BINDING
    _authorize(client, user_password)
    verify_url = url_for("settings.verify_security_key_registration")
    payload = {"name": "  Office USB key  ", "credential": registration_response}

    response = client.post(verify_url, json=payload)

    assert response.status_code == 201
    credential = db.session.scalar(
        db.select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )
    assert credential is not None
    assert credential.name == "Office USB key"

    _mark_recent_strong_authentication(client, user)
    _authorize(client, user_password)
    replay = client.post(verify_url, json=payload)
    assert replay.status_code == 400
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
        )
        == 1
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_security_key_json_routes_require_csrf(
    app: Flask,
    client: FlaskClient,
    user_password: str,
    mocker: MockFixture,
) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("settings.authorize_security_key"),
            data={"password": user_password},
        )
        assert response.status_code == 400

        response = client.post(
            url_for("settings.security_key_registration_options"),
            json={"name": "Office key"},
        )
        assert response.status_code == 400

        page = client.get(url_for("settings.security_keys"))
        csrf_meta = BeautifulSoup(page.text, "html.parser").find(
            "meta", attrs={"name": "csrf-token"}
        )
        assert csrf_meta is not None
        csrf_token = csrf_meta.get("content")
        assert isinstance(csrf_token, str)
        response = client.post(
            url_for("settings.authorize_security_key"),
            data={"password": user_password, "csrf_token": csrf_token},
        )
        assert response.status_code == 302

        mocker.patch(
            "hushline.webauthn.WebAuthnCeremonyService.begin_registration",
            return_value={"challenge": "challenge"},
        )
        response = client.post(
            url_for("settings.security_key_registration_options"),
            json={"name": "Office key"},
            headers={"X-CSRFToken": csrf_token},
        )
        assert response.status_code == 200
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting


@pytest.mark.usefixtures("_authenticated_user")
def test_rename_security_key_requires_recent_reauthentication(
    client: FlaskClient, user: User, user_password: str
) -> None:
    credential = _credential(user, b"rename-key", "Old label")
    rename_url = url_for("settings.rename_security_key")

    response = client.post(
        rename_url,
        data={"credential_id": credential.id, "name": "New label"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    db.session.refresh(credential)
    assert credential.name == "Old label"

    user.totp_secret = pyotp.random_base32()
    db.session.commit()
    _authorize(client, user_password, pyotp.TOTP(user.totp_secret).now())
    response = client.post(
        rename_url,
        data={"credential_id": credential.id, "name": "  New label  "},
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(credential)
    assert credential.name == "New label"


@pytest.mark.usefixtures("_authenticated_user")
def test_removal_revokes_key_consumes_challenges_and_bounds_metadata(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
) -> None:
    app.config["WEBAUTHN_MAX_REVOKED_CREDENTIALS_PER_USER"] = 2
    app.config["WEBAUTHN_REVOKED_CREDENTIAL_RETENTION_DAYS"] = 30
    removed_before = _credential(user, b"old-revoked-key", "Old revoked key")
    removed_before.disabled_at = datetime.now(UTC) - timedelta(days=31)
    removed_before_id = removed_before.id
    target = _credential(user, b"target-key", "Target key")
    _credential(user, b"backup-key-for-removal", "Backup key")
    now = datetime.now(UTC)
    challenge = WebAuthnChallenge(
        user_id=user.id,
        purpose=WebAuthnPurpose.AUTHENTICATION.value,
        challenge_hash=sha256(b"outstanding-challenge").digest(),
        session_binding_hash=sha256(b"session-binding").digest(),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    db.session.add(challenge)
    db.session.commit()
    _mark_recent_strong_authentication(client, user)
    _authorize(client, user_password)

    response = client.post(
        url_for("settings.remove_security_key"),
        data={"credential_id": target.id},
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(target)
    db.session.refresh(challenge)
    assert target.disabled_at is not None
    assert challenge.consumed_at is not None
    assert db.session.get(WebAuthnCredential, removed_before_id) is None
    revoked_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(WebAuthnCredential)
        .where(
            WebAuthnCredential.user_id == user.id,
            WebAuthnCredential.disabled_at.is_not(None),
        )
    )
    assert revoked_count == 1


@pytest.mark.usefixtures("_authenticated_user")
def test_last_factor_requires_explicit_disable_mfa_flow(
    client: FlaskClient, user: User, user_password: str
) -> None:
    credential = _credential(user, b"only-key", "Only key")
    batch = RecoveryCodeBatch(user_id=user.id, acknowledged_at=datetime.now(UTC))
    db.session.add(batch)
    db.session.commit()
    original_session_id = user.session_id
    _mark_recent_strong_authentication(client, user)
    _authorize(client, user_password)

    blocked = client.post(
        url_for("settings.remove_security_key"),
        data={"credential_id": credential.id},
        follow_redirects=True,
    )
    assert "Add another security key or authenticator app" in blocked.text
    db.session.refresh(credential)
    assert credential.disabled_at is None

    unconfirmed = client.post(
        url_for("settings.disable_mfa"),
        data={},
        follow_redirects=False,
    )
    assert unconfirmed.status_code == 400
    db.session.refresh(credential)
    assert credential.disabled_at is None

    disabled = client.post(
        url_for("settings.disable_mfa"),
        data={"confirm": "y"},
        follow_redirects=False,
    )

    assert disabled.status_code == 302
    db.session.refresh(credential)
    db.session.refresh(batch)
    db.session.refresh(user)
    assert credential.disabled_at is not None
    assert batch.invalidated_at is not None
    assert user.session_id != original_session_id
    with client.session_transaction() as client_session:
        assert client_session["session_id"] == user.session_id


@pytest.mark.usefixtures("_authenticated_user")
def test_remove_totp_keeps_security_key_mfa_enabled(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = pyotp.random_base32()
    credential = _credential(user, b"remaining-key", "Remaining key")
    code = pyotp.TOTP(user.totp_secret).now()
    _authorize(client, user_password, code)

    response = client.post(
        url_for("settings.remove_totp_factor"),
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(user)
    db.session.refresh(credential)
    assert user.totp_secret is None
    assert credential.disabled_at is None

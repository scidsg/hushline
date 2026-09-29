import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pyotp
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from passlib.hash import scrypt
from pytest_mock import MockFixture

from hushline.auth import (
    AUTH_SESSION_KEYS,
    CHAT_KEY_SESSION_ID_SESSION_KEY,
    PENDING_MFA_METHODS_SESSION_KEY,
    POST_AUTH_REDIRECT_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
)
from hushline.config import PASSWORD_HASH_REHASH_ON_AUTH_ENABLED
from hushline.db import db
from hushline.model import AuthenticationLog, ChatKey, User, WebAuthnCredential
from hushline.password_hasher import PINNED_WERKZEUG_SCRYPT_METHOD
from hushline.webauthn import WebAuthnRateLimitError, WebAuthnVerificationError

TOTP_SECRET = "KBOVHCCELV67CYGOQ2QYU5SCNYVAREMH"
ROOT = Path(__file__).resolve().parents[1]


def _credential(user: User, marker: bytes = b"login-key") -> WebAuthnCredential:
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=marker,
        public_key=b"public-key-" + marker,
        algorithm=-7,
        sign_count=0,
        transports=["usb"],
        device_type="single_device",
        backed_up=False,
        name="Login key",
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


def _chat_key_payload() -> dict[str, object]:
    return {
        "public_key": '{"kty":"EC","crv":"P-256","x":"login-x","y":"login-y"}',
        "public_signing_key": ('{"kty":"EC","crv":"P-256","x":"signing-x","y":"signing-y"}'),
        "encrypted_private_key": (
            '{"algorithm":"AES-GCM","iv":"bG9naW4tbm9uY2Uh",'
            '"ciphertext":"bG9naW4td3JhcHBlZC1wcml2YXRlLWtleQ=="}'
        ),
        "kdf_algorithm": "PBKDF2-SHA-256",
        "kdf_params": {"iterations": 310000, "hash": "SHA-256"},
        "kdf_salt": "bG9naW4tc2FsdC0xMjM0NQ==",
        "wrapping_algorithm": "AES-GCM",
    }


def test_key_only_password_login_remains_pending_and_only_presents_security_key(
    client: FlaskClient, user: User, user_password: str
) -> None:
    _credential(user)
    original_session_id = user.session_id

    _password_login(client, user, user_password)
    response = client.get(url_for("verify_2fa_login"))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert "Use your security key" in response.text
    assert "Enter your 2FA Code" not in response.text
    assert url_for("security_key_login_options") in response.text
    soup = BeautifulSoup(response.text, "html.parser")
    button = soup.find("button", id="security-key-login-button")
    status = soup.find(id="security-key-login-status")
    assert button is not None
    assert button.get_text(strip=True) == "Verify Security Key"
    assert status is not None
    assert status.get("role") == "status"
    assert status.get("aria-live") == "polite"
    protected = client.get(url_for("settings.profile"), follow_redirects=False)
    canceled = client.get(url_for("login"), follow_redirects=False)
    assert protected.status_code == 302
    assert protected.headers["Location"].endswith(url_for("verify_2fa_login"))
    assert canceled.status_code == 200
    db.session.refresh(user)
    assert user.session_id == original_session_id
    assert db.session.scalars(db.select(AuthenticationLog).filter_by(user_id=user.id)).all() == []
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False
        assert session[PENDING_MFA_METHODS_SESSION_KEY] == ["security_key"]
        assert CHAT_KEY_SESSION_ID_SESSION_KEY not in session


def test_combined_account_presents_only_its_two_permitted_alternatives(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = TOTP_SECRET
    _credential(user)

    _password_login(client, user, user_password)
    response = client.get(url_for("verify_2fa_login"))

    assert "Enter your 2FA Code" in response.text
    assert "Or use a security key" in response.text
    totp_response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(TOTP_SECRET).now()},
        follow_redirects=False,
    )
    assert totp_response.status_code == 302
    with client.session_transaction() as session:
        assert session["is_authenticated"] is True
        assert PENDING_MFA_METHODS_SESSION_KEY not in session


def test_totp_only_pending_login_rejects_security_key_api(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = TOTP_SECRET
    db.session.commit()
    _password_login(client, user, user_password)

    options_response = client.post(url_for("security_key_login_options"), json={})
    verify_response = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "not-permitted"}},
    )

    assert options_response.status_code == 403
    assert verify_response.status_code == 403
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False


def test_security_key_api_cannot_start_passwordless_login(client: FlaskClient) -> None:
    options_response = client.post(url_for("security_key_login_options"), json={})
    verify_response = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "not-pending"}},
    )

    assert options_response.status_code == 401
    assert verify_response.status_code == 401


def test_security_key_options_are_bound_to_pending_account_and_enforce_rate_limit(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    _credential(user)
    _password_login(client, user, user_password)
    begin = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.begin_authentication",
        return_value={
            "challenge": "challenge",
            "allowCredentials": [],
            "userVerification": "required",
        },
    )

    response = client.post(url_for("security_key_login_options"), json={})

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    response_json = response.json
    assert isinstance(response_json, dict)
    assert response_json["userVerification"] == "required"
    assert begin.call_args.kwargs["user"].id == user.id
    assert isinstance(begin.call_args.kwargs["session_binding"], str)

    begin.side_effect = WebAuthnRateLimitError("limited")
    response = client.post(url_for("security_key_login_options"), json={})
    assert response.status_code == 429
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False


def test_tampered_security_key_assertion_does_not_authenticate(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    _credential(user)
    _password_login(client, user, user_password)
    finish = mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
        side_effect=WebAuthnVerificationError("invalid"),
    )

    response = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "wrong-account-key"}},
    )

    assert response.status_code == 401
    assert finish.call_args.kwargs["user"].id == user.id
    assert finish.call_args.kwargs["response"] == {"rawId": "wrong-account-key"}
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(AuthenticationLog)
            .where(
                AuthenticationLog.user_id == user.id,
                AuthenticationLog.successful.is_(False),
            )
        )
        == 1
    )
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False
        assert CHAT_KEY_SESSION_ID_SESSION_KEY not in session


def test_successful_security_key_login_rotates_session_and_preserves_redirect_and_chat_key(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    credential = _credential(user)
    original_session_id = user.session_id
    protected_target = url_for("settings.profile", _external=False)
    with client.session_transaction() as session:
        session[POST_AUTH_REDIRECT_SESSION_KEY] = protected_target
    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
            "chat_key_payload": json.dumps(_chat_key_payload()),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
        return_value=credential,
    )

    response = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "verified"}},
    )

    assert response.status_code == 200
    assert response.json == {"redirect": protected_target}
    db.session.refresh(user)
    assert user.session_id != original_session_id
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(AuthenticationLog)
            .where(
                AuthenticationLog.user_id == user.id,
                AuthenticationLog.successful.is_(True),
            )
        )
        == 1
    )
    created_key = db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).one()
    assert created_key.public_key == _chat_key_payload()["public_key"]
    with client.session_transaction() as session:
        assert session["is_authenticated"] is True
        assert isinstance(session[CHAT_KEY_SESSION_ID_SESSION_KEY], str)
        assert POST_AUTH_REDIRECT_SESSION_KEY not in session
        assert PENDING_MFA_METHODS_SESSION_KEY not in session
        assert WEBAUTHN_SESSION_BINDING_KEY not in session


def test_security_key_login_applies_password_rehash_only_after_assertion(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = True
    original_hash = scrypt.hash(user_password)
    user._password_hash = original_hash
    credential = _credential(user)

    with patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry:
        _password_login(client, user, user_password)
        db.session.refresh(user)
        assert user.password_hash == original_hash
        telemetry.assert_not_called()
        mocker.patch(
            "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
            return_value=credential,
        )
        response = client.post(
            url_for("verify_security_key_login"),
            json={"credential": {"rawId": "verified"}},
        )

    db.session.refresh(user)
    assert response.status_code == 200
    assert user.password_hash.startswith(f"{PINNED_WERKZEUG_SCRYPT_METHOD}$")
    telemetry.assert_called_once_with(original_hash, success=True)


def test_stale_parallel_tab_cannot_reuse_pending_security_key_session(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    credential = _credential(user)
    _password_login(client, user, user_password)
    with client.session_transaction() as session:
        stale_state = {
            "user_id": session["user_id"],
            "session_id": session["session_id"],
            "username": session["username"],
            "is_authenticated": False,
            PENDING_MFA_METHODS_SESSION_KEY: list(session[PENDING_MFA_METHODS_SESSION_KEY]),
            WEBAUTHN_SESSION_BINDING_KEY: "stale-tab-binding-that-is-long-enough",
        }
    mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
        return_value=credential,
    )
    first = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "first-tab"}},
    )
    assert first.status_code == 200

    with app.test_client() as stale_client:
        with stale_client.session_transaction() as session:
            session.update(stale_state)
        stale = stale_client.post(url_for("security_key_login_options"), json={})

    assert stale.status_code == 401
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(AuthenticationLog)
            .where(
                AuthenticationLog.user_id == user.id,
                AuthenticationLog.successful.is_(True),
            )
        )
        == 1
    )


def test_session_rotation_during_assertion_prevents_parallel_completion(
    client: FlaskClient,
    user: User,
    user_password: str,
    mocker: MockFixture,
) -> None:
    credential = _credential(user)
    _password_login(client, user, user_password)

    def complete_other_tab(**_kwargs: object) -> WebAuthnCredential:
        db.session.execute(
            db.update(User).where(User.id == user.id).values(session_id=User.new_session_id())
        )
        db.session.commit()
        return credential

    mocker.patch(
        "hushline.webauthn.WebAuthnCeremonyService.finish_authentication",
        side_effect=complete_other_tab,
    )

    response = client.post(
        url_for("verify_security_key_login"),
        json={"credential": {"rawId": "parallel-tab"}},
    )

    assert response.status_code == 401
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(AuthenticationLog)
            .where(
                AuthenticationLog.user_id == user.id,
                AuthenticationLog.successful.is_(True),
            )
        )
        == 0
    )
    with client.session_transaction() as session:
        for key in AUTH_SESSION_KEYS:
            assert key not in session


def test_security_key_login_json_routes_require_csrf_without_clearing_pending_login(
    app: Flask,
    client: FlaskClient,
    user: User,
    user_password: str,
) -> None:
    _credential(user)
    _password_login(client, user, user_password)
    app.config["WTF_CSRF_ENABLED"] = True

    response = client.post(url_for("security_key_login_options"), json={})

    assert response.status_code == 400
    page = client.get(url_for("verify_2fa_login"))
    token = BeautifulSoup(page.text, "html.parser").find("meta", attrs={"name": "csrf-token"})
    assert token is not None
    with client.session_transaction() as session:
        assert session["is_authenticated"] is False


def test_security_key_login_browser_flow_is_built_and_keeps_failures_pending() -> None:
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")
    source = (ROOT / "assets/js/security-key-login.js").read_text(encoding="utf-8")

    assert '"security-key-login",' in webpack_config
    assert "navigator.credentials.get" in source
    assert "userHandle: credential.response.userHandle" in source
    assert "You are not logged in." in source
    assert "window.location.assign(result.redirect)" in source

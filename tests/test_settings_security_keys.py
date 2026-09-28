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
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
)
from hushline.db import db
from hushline.model import User, WebAuthnChallenge, WebAuthnCredential, WebAuthnUserHandle
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
    assert "Office USB key" in response.text
    assert "Backup NFC key" in response.text
    assert "Register at least two" in response.text
    assert "keep the backup in a separate safe place" in response.text
    soup = BeautifulSoup(response.text, "html.parser")
    current_tab = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current_tab is not None
    assert current_tab.get_text(strip=True) == "Authentication"


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

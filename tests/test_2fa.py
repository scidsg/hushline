import secrets
from datetime import datetime, timedelta

import pyotp
import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User

TOTP_SECRET = "KBOVHCCELV67CYGOQ2QYU5SCNYVAREMH"


@pytest.fixture()
def _2fa_user(client: FlaskClient, user: User) -> None:
    user.totp_secret = TOTP_SECRET
    db.session.commit()


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_2fa(client: FlaskClient, user: User, user_password: str) -> None:
    enable_2fa_response = client.post(url_for("settings.toggle_2fa"), follow_redirects=True)
    assert enable_2fa_response.status_code == 200
    assert "Scan the QR code with your 2FA app" in enable_2fa_response.text

    with client.session_transaction() as session:
        totp_secret = session["temp_totp_secret"]

    # Verify the 2FA code
    verify_2fa_response = client.post(
        url_for("settings.enable_2fa"),
        data={"verification_code": pyotp.TOTP(totp_secret).now()},
        follow_redirects=True,
    )
    assert verify_2fa_response.status_code == 200

    # Logging in should now require 2FA
    login_response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
        },
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text


@pytest.mark.usefixtures("_2fa_user")
def test_valid_2fa_should_login(client: FlaskClient, user: User, user_password: str) -> None:
    login_response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
        },
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text

    valid_2fa_response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(TOTP_SECRET).now()},
        follow_redirects=True,
    )
    assert valid_2fa_response.status_code == 200


@pytest.mark.usefixtures("_2fa_user")
def test_invalid_2fa_should_not_login(client: FlaskClient, user: User, user_password: str) -> None:
    login_response = client.post(
        "/login",
        data={
            "username": user.primary_username.username,
            "password": user_password,
        },
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    # Make a valid verification code
    totp = pyotp.TOTP(TOTP_SECRET)
    valid_verification_code = totp.now()

    # Change the first character by one digit to make it invalid
    invalid_verification_code = (
        str((int(valid_verification_code[0]) + 1) % 10) + valid_verification_code[1:]
    )

    # Logging in should fail
    invalid_2fa_response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": invalid_verification_code},
        follow_redirects=True,
    )
    assert invalid_2fa_response.status_code == 401
    assert "Invalid 2FA code" in invalid_2fa_response.text


@pytest.mark.usefixtures("_2fa_user")
def test_reuse_of_2fa_code_should_fail(
    client: FlaskClient, user: User, user_password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Keep both verification attempts in the same TOTP interval so replay detection is deterministic.
    current_now = datetime.now().replace(microsecond=0)
    fixed_now = current_now - timedelta(seconds=current_now.second % 30) + timedelta(seconds=5)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is not None:
                return tz.fromutc(fixed_now.replace(tzinfo=tz))
            return fixed_now

    monkeypatch.setattr("hushline.routes.auth.datetime", FrozenDateTime)

    verify_2fa_data = {"verification_code": pyotp.TOTP(TOTP_SECRET).at(fixed_now)}
    login_data = {
        "username": user.primary_username.username,
        "password": user_password,
    }

    # Log in
    login_response = client.post(url_for("login"), data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    valid_2fa_response = client.post(
        url_for("verify_2fa_login"), data=verify_2fa_data, follow_redirects=True
    )
    assert valid_2fa_response.status_code == 200

    # Log out
    logout_response = client.get(url_for("logout"), follow_redirects=True)
    assert logout_response.status_code == 200

    # Log in again with the same 2FA code
    login_response = client.post(url_for("login"), data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    valid_2fa_response = client.post(
        url_for("verify_2fa_login"), data=verify_2fa_data, follow_redirects=True
    )
    # Should be rejected for replaying the same OTP in the same timecode.
    assert valid_2fa_response.status_code == 429


@pytest.mark.usefixtures("_2fa_user")
def test_limit_invalid_2fa_guesses(client: FlaskClient, user: User, user_password: str) -> None:
    # Make sure we have a valid verification code
    totp = pyotp.TOTP(TOTP_SECRET)
    verification_code = totp.now()

    # Log in
    login_response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
        },
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    # Make a random invalid verification code
    def random_verification_code() -> str:
        rand = secrets.SystemRandom()
        while True:
            random_code = str(rand.randint(100000, 999999))
            if random_code != verification_code:
                return random_code

    # Try 5 invalid codes
    for _ in range(5):
        invalid_2fa_response = client.post(
            url_for("verify_2fa_login"),
            data={"verification_code": random_verification_code()},
            follow_redirects=True,
        )
        assert invalid_2fa_response.status_code == 401
        assert "Invalid 2FA code" in invalid_2fa_response.text

    # The 6th guess should give a different error
    invalid_2fa_response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": random_verification_code()},
        follow_redirects=True,
    )
    assert invalid_2fa_response.status_code == 429
    assert "Please wait a moment before trying again" in invalid_2fa_response.text

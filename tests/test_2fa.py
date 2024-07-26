import random
import secrets
import string
from typing import TypeAlias

import pyotp
import pytest
from auth_helper import register_user_2fa
from flask.testing import FlaskClient

LoginData: TypeAlias = dict[str, str]


@pytest.fixture()
def nonce(length: int = 15) -> str:
    return "".join(
        random.choices(  # noqa: S311
            string.ascii_lowercase + string.digits,
            k=length,
        )
    )


@pytest.fixture()
def login_data(nonce: str) -> LoginData:
    return {"username": "test_user_" + nonce, "password": "SecurePassword123!"}


def test_enable_2fa(client: FlaskClient) -> None:
    user, totp_secret = register_user_2fa(client, "test_user", "SecurePassword123!")


def test_valid_2fa_should_login(client: FlaskClient, login_data: LoginData) -> None:
    user, totp_secret = register_user_2fa(client, login_data["username"], login_data["password"])

    # Logging in should now require 2FA
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text

    # Verify 2FA
    totp = pyotp.TOTP(totp_secret)
    verification_code = totp.now()
    verify_2fa_data = {"verification_code": verification_code}
    valid_2fa_response = client.post(
        "/verify-2fa-login", data=verify_2fa_data, follow_redirects=True
    )
    assert valid_2fa_response.status_code == 200


def test_invalid_2fa_should_not_login(client: FlaskClient, login_data: LoginData) -> None:
    user, totp_secret = register_user_2fa(client, login_data["username"], login_data["password"])

    # Start logging in
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200

    # Make a valid verification code
    totp = pyotp.TOTP(totp_secret)
    valid_verification_code = totp.now()

    # Change the first character by one digit to make it invalid
    invalid_verification_code = (
        str((int(valid_verification_code[0]) + 1) % 10) + valid_verification_code[1:]
    )

    # Logging in should fail
    invalid_2fa_data = {"verification_code": invalid_verification_code}
    invalid_2fa_response = client.post(
        "/verify-2fa-login", data=invalid_2fa_data, follow_redirects=True
    )
    assert invalid_2fa_response.status_code == 401
    assert "Invalid 2FA code" in invalid_2fa_response.text


def test_reuse_of_2fa_code_should_fail(client: FlaskClient, login_data: LoginData) -> None:
    user, totp_secret = register_user_2fa(client, login_data["username"], login_data["password"])

    # Make sure we have a valid verification code
    totp = pyotp.TOTP(totp_secret)
    verification_code = totp.now()
    verify_2fa_data = {"verification_code": verification_code}

    # Log in
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    valid_2fa_response = client.post(
        "/verify-2fa-login", data=verify_2fa_data, follow_redirects=True
    )
    assert valid_2fa_response.status_code == 200

    # Log out
    logout_response = client.get("/logout", follow_redirects=True)
    assert logout_response.status_code == 200

    # Log in again with the same 2FA code
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    valid_2fa_response = client.post(
        "/verify-2fa-login", data=verify_2fa_data, follow_redirects=True
    )
    # Should be rejected
    assert valid_2fa_response.status_code == 429


def test_limit_invalid_2fa_guesses(client: FlaskClient, login_data: LoginData) -> None:
    user, totp_secret = register_user_2fa(client, login_data["username"], login_data["password"])

    # Make sure we have a valid verification code
    totp = pyotp.TOTP(totp_secret)
    verification_code = totp.now()

    # Log in
    login_response = client.post("/login", data=login_data, follow_redirects=True)
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
        invalid_2fa_data = {"verification_code": random_verification_code()}
        invalid_2fa_response = client.post(
            "/verify-2fa-login", data=invalid_2fa_data, follow_redirects=True
        )
        assert invalid_2fa_response.status_code == 401
        assert "Invalid 2FA code" in invalid_2fa_response.text

    # The 6th guess should give a different error
    invalid_2fa_data = {"verification_code": random_verification_code()}
    invalid_2fa_response = client.post(
        "/verify-2fa-login", data=invalid_2fa_data, follow_redirects=True
    )
    assert invalid_2fa_response.status_code == 429
    assert "Please wait a moment before trying again" in invalid_2fa_response.text

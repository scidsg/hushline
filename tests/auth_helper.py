import os
from datetime import datetime, timedelta

import bs4
import pyotp
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import AuthenticationLog, User, Username


def register_user(client: FlaskClient, username: str, password: str) -> User:
    # Prepare the environment to not require invite codes
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    user_data = {"username": username, "password": password}

    response = client.post("/register", data=user_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Registration successful!" in response.data

    user = db.session.scalars(
        db.select(User).join(Username).filter(Username._username == username)
    ).one()
    assert user.primary_username.username == username

    return user


def register_user_2fa(client: FlaskClient, username: str, password: str) -> tuple[User, str]:
    user_data = {"username": username, "password": password}
    response = client.post("/register", data=user_data, follow_redirects=True)
    assert response.status_code == 200

    user = db.session.scalars(
        db.select(User).join(Username).filter(Username._username == username)
    ).one()
    assert user.primary_username.username == username

    # And 2FA is disabled
    assert user._totp_secret is None

    # Login
    login_data = {"username": username, "password": password}
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200

    # Enable 2FA
    enable_2fa_response = client.post("/settings/toggle-2fa", follow_redirects=True)
    assert enable_2fa_response.status_code == 200
    assert "Scan the QR code with your 2FA app" in enable_2fa_response.text

    # Get the 2FA code from the HTML
    soup = bs4.BeautifulSoup(enable_2fa_response.data, "html.parser")
    totp_secret = soup.select_one(".totp-secret").text

    # Verify the 2FA code
    totp = pyotp.TOTP(totp_secret)
    verification_code = totp.now()

    # Verify the 2FA code
    verify_2fa_data = {"verification_code": verification_code}
    verify_2fa_response = client.post(
        "/settings/enable-2fa", data=verify_2fa_data, follow_redirects=True
    )
    assert verify_2fa_response.status_code == 200

    # Logging in should now require 2FA
    login_response = client.post("/login", data=login_data, follow_redirects=True)
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text

    # Modify the timestamps on the AuthenticationLog entries to allow for 2FA verification
    for log in db.session.scalars(db.select(AuthenticationLog)).all():
        log.timestamp = datetime.now() - timedelta(minutes=5)

    return (user, totp_secret)


def login_user(client: FlaskClient, username: str, password: str) -> User | None:
    # Login data should match the registration data
    login_data = {"username": username, "password": password}

    # Attempt to log in with the registered user
    response = client.post("/login", data=login_data, follow_redirects=True)

    # Validate login response
    assert response.status_code == 200
    assert b"Inbox" in response.data
    assert (
        f'href="/inbox?username={username}"'.encode() in response.data
    ), f"Inbox link should be present for the user {username}"

    if username := db.session.scalars(
        db.select(Username).filter_by(_username=username)
    ).one_or_none():
        return username.user
    return None


def configure_pgp(client: FlaskClient) -> None:
    # Load the PGP key from a file
    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read()

    # Submit POST request to add the PGP key
    response = client.post(
        "/settings/update-pgp-key",
        data={"pgp_key": new_pgp_key},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Error configuring PGP key"

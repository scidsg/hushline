from secrets import token_urlsafe
from unittest.mock import ANY, MagicMock, patch

from auth_helper import configure_pgp, login_user, register_user
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def test_settings_page_loads(client: FlaskClient) -> None:
    # Register a user
    user = register_user(client, "testuser_settings", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    # Log in the user
    user_logged_in = login_user(client, "testuser_settings", "SecureTestPass123!")
    assert user_logged_in is not None, "User login failed"

    # Access the /settings page
    response = client.get("/settings/", follow_redirects=True)
    assert response.status_code == 200, "Failed to load the settings page"


def test_change_display_name(client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "testuser_settings", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "testuser_settings", "SecureTestPass123!")

    # Define new display name
    new_display_name = "New Display Name"

    # Submit POST request to change display name
    response = client.post(
        "/settings/",
        data={
            "display_name": new_display_name,
            "update_display_name": "Update Display Name",
        },
        follow_redirects=True,
    )

    # Verify update was successful
    assert response.status_code == 200, "Failed to update display name"

    # Fetch updated user info from the database to confirm change
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="testuser_settings").limit(1)
    ).one()
    assert updated_user is not None, "User was not found after update attempt"
    assert updated_user.display_name == new_display_name, "Display name was not updated correctly"

    # Optional: Check for success message in response
    assert (
        b"Display name updated successfully" in response.data
    ), "Success message not found in response"


def test_change_username(client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "original_username", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "original_username", "SecureTestPass123!")

    # Define new username
    new_username = "updated_username"

    # Submit POST request to change the username
    response = client.post(
        "/settings/",
        data={
            "new_username": new_username,
            "change_username": "Update Username",  # This button name must match your HTML form
        },
        follow_redirects=True,
    )

    # Verify update was successful
    assert response.status_code == 200, "Failed to update username"

    # Fetch updated user info from the database to confirm change
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username=new_username).limit(1)
    ).one()
    assert updated_user is not None, "Username was not updated correctly in the database"
    assert (
        updated_user.primary_username == new_username
    ), "Database does not reflect the new username"

    assert (
        not updated_user.is_verified
    ), "User verification status should be reset after username change"

    # Optional: Check for success message in response
    assert (
        b"Username changed successfully" in response.data
    ), "Success message not found in response"


def test_change_password(client: FlaskClient) -> None:
    # Register a new user
    username = "test_change_password"
    original_password = f"{token_urlsafe(16)}!"
    new_password = f"{token_urlsafe(16)}!!!"
    user = register_user(client, username, original_password)
    assert user is not None, "User registration failed"
    assert len(original_password_hash := user.password_hash) > 32
    assert original_password_hash.startswith("$scrypt$")
    assert original_password not in original_password_hash

    # Log in the registered user
    logged_in_user = login_user(client, username, original_password)
    assert logged_in_user is not None
    assert user.id == logged_in_user.id

    # Submit POST request to change the username & verify update was successful
    response = client.post(
        "/settings/change-password",
        data={
            "old_password": original_password,
            "new_password": new_password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, "Failed to update password"
    assert "login" in response.request.url
    assert len(new_password_hash := user.password_hash) > 32
    assert new_password_hash.startswith("$scrypt$")
    assert original_password_hash not in new_password_hash
    assert original_password not in new_password_hash
    assert new_password not in new_password_hash
    assert (
        b"Password successfully changed. Please log in again." in response.data
    ), "Success message not found in response"

    # Attempt to log in with the registered user's old password
    response = client.post(
        "/login", data={"username": username, "password": original_password}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "login" in response.request.url
    assert b"Invalid username or password" in response.data, "Failure message not found in response"

    # Attempt to log in with the registered user's new password
    response = client.post(
        "/login", data={"username": username, "password": new_password}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "inbox" in response.request.url
    assert b"Empty Inbox" in response.data, "Inbox message not found in response"
    assert (
        b"Invalid username or password" not in response.data
    ), "Failure message was found in response"


def test_add_pgp_key(client: FlaskClient) -> None:
    # Setup and login
    user = register_user(client, "user_with_pgp", "SecureTestPass123!")
    assert user is not None, "User registration failed"
    login_user(client, "user_with_pgp", "SecureTestPass123!")

    # Load the PGP key from a file
    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read()

    # Submit POST request to add the PGP key
    response = client.post(
        "/settings/update-pgp-key",
        data={"pgp_key": new_pgp_key},
        follow_redirects=True,
    )

    # Check successful update
    assert response.status_code == 200, "Failed to update PGP key"
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="user_with_pgp").limit(1)
    ).one()
    assert updated_user is not None, "User was not found after update attempt"
    assert updated_user.pgp_key == new_pgp_key, "PGP key was not updated correctly"

    # Check for success message
    assert b"PGP key updated successfully" in response.data, "Success message not found"


def test_add_invalid_pgp_key(client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "user_invalid_pgp", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_invalid_pgp", "SecureTestPass123!")

    # Define an invalid PGP key string
    invalid_pgp_key = "NOT A VALID PGP KEY BLOCK"

    # Submit POST request to add the invalid PGP key
    response = client.post(
        "/settings/update-pgp-key",
        data={"pgp_key": invalid_pgp_key},
        follow_redirects=True,
    )

    # Check that update was not successful
    assert response.status_code == 200, "HTTP status code check"

    # Fetch updated user info from the database to confirm no change
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="user_invalid_pgp")
    ).one()
    assert updated_user is not None, "User was not found after update attempt"
    assert (
        updated_user.pgp_key != invalid_pgp_key
    ), "Invalid PGP key should not have been updated in the database"

    # Optional: Check for error message in response
    assert b"Invalid PGP key format" in response.data, "Error message for invalid PGP key not found"


@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_no_pgp(SMTP: MagicMock, client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "user_smtp_settings_no_pgp", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_smtp_settings_no_pgp", "SecureTestPass123!")

    # Define new SMTP settings
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 587,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "StartTLS",
    }

    # Submit POST request to update SMTP settings
    response = client.post(
        "/settings/update-smtp-settings",
        data=new_smtp_settings,
        follow_redirects=True,
    )

    # Check successful update
    assert response.status_code == 200, "Failed to update SMTP settings"
    assert (
        b"Email forwarding requires a configured PGP key" in response.data
    ), "Expected email forwarding to require PGP key"
    # Fetch updated user info from the database to confirm changes
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="user_smtp_settings_no_pgp")
    ).one()
    assert updated_user is not None, "User was not found after update attempt"
    assert updated_user.email is None, f"Email address should not be set, was {updated_user.email}"
    assert (
        updated_user.smtp_server is None
    ), f"SMTP server should not be set, was {updated_user.smtp_server}"
    assert (
        updated_user.smtp_port is None
    ), f"SMTP port should not be set, was {updated_user.smtp_port}"
    assert (
        updated_user.smtp_username is None
    ), f"SMTP username should not be set, was {updated_user.smtp_username}"
    assert (
        updated_user.smtp_password is None
    ), f"SMTP password should not be set, was {updated_user.smtp_password}"


@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_starttls(SMTP: MagicMock, client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "user_smtp_settings_tls", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_smtp_settings_tls", "SecureTestPass123!")

    configure_pgp(client)

    # Define new SMTP settings
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 587,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "StartTLS",
    }

    # Submit POST request to update SMTP settings
    response = client.post(
        "/settings/update_smtp_settings",  # Adjust to your app's correct endpoint
        data=new_smtp_settings,
        follow_redirects=True,
    )

    SMTP.assert_called_with(user.smtp_server, user.smtp_port, timeout=ANY)
    SMTP.return_value.__enter__.return_value.starttls.assert_called_once_with()
    SMTP.return_value.__enter__.return_value.login.assert_called_once_with(
        user.smtp_username, user.smtp_password
    )
    # Check successful update
    assert response.status_code == 200, "Failed to update SMTP settings"
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="user_smtp_settings_tls")
    ).one()
    assert (
        updated_user.email == new_smtp_settings["email_address"]
    ), "Email address was not updated correctly"
    assert (
        updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    ), "SMTP server was not updated correctly"
    assert (
        updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    ), "SMTP port was not updated correctly"
    assert (
        updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    ), "SMTP username was not updated correctly"
    assert (
        updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    ), "SMTP password was not updated correctly"
    assert (
        updated_user.smtp_encryption == new_smtp_settings["smtp_settings-smtp_encryption"]
    ), "SMTP encryption was not updated correctly"

    # Optional: Check for success message in response
    assert b"SMTP settings updated successfully" in response.data, "Success message not found"


@patch("hushline.utils.smtplib.SMTP_SSL")
def test_update_smtp_settings_ssl(SMTP: MagicMock, client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "user_smtp_settings_ssl", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_smtp_settings_ssl", "SecureTestPass123!")

    configure_pgp(client)

    # Define new SMTP settings
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 465,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "SSL",
    }

    # Submit POST request to update SMTP settings
    response = client.post(
        "/settings/update_smtp_settings",  # Adjust to your app's correct endpoint
        data=new_smtp_settings,
        follow_redirects=True,
    )

    SMTP.assert_called_with(user.smtp_server, user.smtp_port, timeout=ANY)
    SMTP.return_value.__enter__.return_value.starttls.assert_not_called()
    SMTP.return_value.__enter__.return_value.login.assert_called_once_with(
        user.smtp_username, user.smtp_password
    )
    # Check successful update
    assert response.status_code == 200, "Failed to update SMTP settings"
    updated_user = db.session.scalars(
        db.select(User).filter_by(primary_username="user_smtp_settings_ssl")
    ).one()
    assert (
        updated_user.email == new_smtp_settings["email_address"]
    ), "Email address was not updated correctly"
    assert (
        updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    ), "SMTP server was not updated correctly"
    assert (
        updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    ), "SMTP port was not updated correctly"
    assert (
        updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    ), "SMTP username was not updated correctly"
    assert (
        updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    ), "SMTP password was not updated correctly"
    assert (
        updated_user.smtp_encryption == new_smtp_settings["smtp_settings-smtp_encryption"]
    ), "SMTP encryption was not updated correctly"

    # Optional: Check for success message in response
    assert b"SMTP settings updated successfully" in response.data, "Success message not found"

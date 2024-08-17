from secrets import token_urlsafe

from auth_helper import login_user, register_user
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
    ).first()
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
    ).first()
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
    ).first()
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
    updated_user = User.query.filter_by(primary_username="user_invalid_pgp").first()
    assert updated_user is not None, "User was not found after update attempt"
    assert (
        updated_user.pgp_key != invalid_pgp_key
    ), "Invalid PGP key should not have been updated in the database"

    # Optional: Check for error message in response
    assert b"Invalid PGP key format" in response.data, "Error message for invalid PGP key not found"


def test_update_smtp_settings(client: FlaskClient) -> None:
    # Register and log in a user
    user = register_user(client, "user_smtp_settings", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_smtp_settings", "SecureTestPass123!")

    # Define new SMTP settings
    new_smtp_settings = {
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user@example.com",
        "smtp_password": "securepassword123",
    }

    # Submit POST request to update SMTP settings
    response = client.post(
        "/settings/update-smtp-settings",
        data=new_smtp_settings,
        follow_redirects=True,
    )

    # Check successful update
    assert response.status_code == 200, "Failed to update SMTP settings"

    # Fetch updated user info from the database to confirm changes
    updated_user = User.query.filter_by(primary_username="user_smtp_settings").first()
    assert updated_user is not None, "User was not found after update attempt"
    assert (
        updated_user.smtp_server == new_smtp_settings["smtp_server"]
    ), "SMTP server was not updated correctly"
    assert (
        updated_user.smtp_port == new_smtp_settings["smtp_port"]
    ), "SMTP port was not updated correctly"
    assert (
        updated_user.smtp_username == new_smtp_settings["smtp_username"]
    ), "SMTP username was not updated correctly"
    assert (
        updated_user.smtp_password == new_smtp_settings["smtp_password"]
    ), "SMTP password was not updated correctly"

    # Optional: Check for success message in response
    assert b"SMTP settings updated successfully" in response.data, "Success message not found"

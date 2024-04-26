import pytest
from auth_helper import login_user, register_user

from hushline.model import User  # Ensure the User model is imported


@pytest.fixture
def client():
    from hushline import create_app, db

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def test_settings_page_loads(client):
    # Register a user
    user = register_user(client, "testuser_settings", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    # Log in the user
    user_logged_in = login_user(client, "testuser_settings", "SecureTestPass123!")
    assert user_logged_in is not None, "User login failed"

    # Access the /settings page
    response = client.get("/settings/", follow_redirects=True)
    assert response.status_code == 200, "Failed to load the settings page"


def test_change_display_name(client):
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
    updated_user = User.query.filter_by(primary_username="testuser_settings").first()
    assert updated_user.display_name == new_display_name, "Display name was not updated correctly"

    # Optional: Check for success message in response
    assert (
        b"Display name updated successfully" in response.data
    ), "Success message not found in response"


def test_change_username(client):
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
    updated_user = User.query.filter_by(primary_username=new_username).first()
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


def test_add_pgp_key(client):
    # Setup and login
    user = register_user(client, "user_with_pgp", "SecureTestPass123!")
    assert user is not None, "User registration failed"
    login_user(client, "user_with_pgp", "SecureTestPass123!")

    # Define a PGP key string (use a realistic dummy key for actual testing)
    new_pgp_key = """-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: Mailvelope v5.1.2
Comment: https://mailvelope.com

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
eODK+oGDFyTbXtSFsc1yS4dkfDsSSf8=
=Kis6
-----END PGP PUBLIC KEY BLOCK-----
"""

    # Submit POST request to add the PGP key
    response = client.post(
        "/settings/update_pgp_key",
        data={"pgp_key": new_pgp_key},
        follow_redirects=True,
    )

    # Check successful update
    assert response.status_code == 200, "Failed to update PGP key"
    updated_user = User.query.filter_by(primary_username="user_with_pgp").first()
    assert updated_user.pgp_key == new_pgp_key, "PGP key was not updated correctly"

    # Check for success message
    assert b"PGP key updated successfully" in response.data, "Success message not found"


def test_add_invalid_pgp_key(client):
    # Register and log in a user
    user = register_user(client, "user_invalid_pgp", "SecureTestPass123!")
    assert user is not None, "User registration failed"

    login_user(client, "user_invalid_pgp", "SecureTestPass123!")

    # Define an invalid PGP key string
    invalid_pgp_key = "NOT A VALID PGP KEY BLOCK"

    # Submit POST request to add the invalid PGP key
    response = client.post(
        "/settings/update_pgp_key",  # Adjust to your app's correct endpoint
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


def test_update_smtp_settings(client):
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
        "/settings/update_smtp_settings",  # Adjust to your app's correct endpoint
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

from auth_helper import login_user, register_user

from hushline.model import User  # Ensure the User model is imported


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

    # Load the PGP key from a file
    with open("tests/test_pgp_key.txt", "r") as file:
        new_pgp_key = file.read()

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

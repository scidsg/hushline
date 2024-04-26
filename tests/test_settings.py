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

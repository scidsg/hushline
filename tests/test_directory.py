from auth_helper import login_user, register_user
from werkzeug import HTTPStatus

from hushline import db


def test_directory_accessible(client):
    # Get the directory page
    response = client.get("/directory")

    # Check if the page loads successfully
    assert response.status_code == HTTPStatus.OK
    assert "User Directory" in response.get_data(as_text=True)


def test_directory_lists_only_opted_in_users(client):
    """Test that only users who have opted to be shown are listed in the directory."""
    with client.application.app_context():
        # Register and opt-in a user
        user_opted_in = register_user(client, "user_optedin", "SecurePassword123!")
        user_opted_in.show_in_directory = True
        db.session.commit()

        # Register and do not opt-in another user
        user_not_opted_in = register_user(client, "user_not_optedin", "SecurePassword123!")
        user_not_opted_in.show_in_directory = False
        db.session.commit()

        # Access the directory as a logged-in user
        login_user(client, "user_optedin", "SecurePassword123!")
        response = client.get("/directory")
        assert "user_optedin" in response.get_data(as_text=True), "Opted-in user should be listed"
        assert "user_not_optedin" not in response.get_data(
            as_text=True
        ), "Non-opted-in user should not be listed"

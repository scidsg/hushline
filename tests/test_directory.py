from auth_helper import login_user, register_user
from flask.testing import FlaskClient

from hushline import db


def test_directory_accessible(client: FlaskClient) -> None:
    response = client.get("/directory")
    assert response.status_code == 200
    assert "User Directory" in response.text


def test_directory_lists_only_opted_in_users(client: FlaskClient) -> None:
    # Register and opt-in a user
    user_opted_in = register_user(client, "user_optedin", "SecurePassword123!")
    user_opted_in.primary_username.show_in_directory = True
    db.session.commit()

    # Register and do not opt-in another user
    user_not_opted_in = register_user(client, "user_not_optedin", "SecurePassword123!")
    user_not_opted_in.primary_username.show_in_directory = False
    db.session.commit()

    # Access the directory as a logged-in user
    login_user(client, "user_optedin", "SecurePassword123!")
    response = client.get("/directory")
    assert "user_optedin" in response.text
    assert "user_not_optedin" not in response.text

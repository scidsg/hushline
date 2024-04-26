import pytest
from auth_helper import login_user, register_user


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

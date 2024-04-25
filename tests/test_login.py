# test_login.py
import pytest

from hushline import create_app  # Adjust the import according to your application structure


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,  # Disable CSRF tokens for testing purposes
        }
    )
    # Ensure other configurations that might affect your tests are properly set or disabled
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_login_page_loads(client):
    # Just test if the login page returns a 200 status code
    response = client.get("/login")
    assert response.status_code == 200

import pytest
from dotenv import load_dotenv

from hushline import create_app
from hushline.db import db


@pytest.fixture
def client():
    # Load environment variables from env.sh
    load_dotenv("env.sh")

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///:memory:"  # Use in-memory database for testing
    )
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF protection for testing

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def test_register_page_loads(client):
    # Test that the registration page loads successfully
    response = client.get("/register")
    assert response.status_code == 200
    assert b"<h2>Register</h2>" in response.data

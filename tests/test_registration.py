import os
import tempfile

import pytest
from dotenv import load_dotenv

from hushline import create_app
from hushline.db import db


@pytest.fixture
def client():
    # Load environment variables from env.sh
    load_dotenv("env.sh")

    # Create a temporary directory for the SQLite database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "hushline.db")

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF protection for testing

    # Print out the database URI to help diagnose the issue
    print("Database URI:", app.config["SQLALCHEMY_DATABASE_URI"])

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

    # Remove the temporary directory and its contents after the test
    os.rmdir(temp_dir)


def test_register_page_loads(client):
    # Test that the registration page loads successfully
    response = client.get("/register")
    assert response.status_code == 200
    assert b"<h2>Register</h2>" in response.data

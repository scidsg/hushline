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

    # Create the directory if it doesn't exist
    db_dir = os.path.join(os.getcwd(), "instance")
    os.makedirs(db_dir, exist_ok=True)

    # Create a temporary file for the SQLite database
    db_fd, db_path = tempfile.mkstemp(suffix=".db", dir=db_dir)
    os.close(db_fd)

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

    # Remove the temporary database file after the test
    os.remove(db_path)


def test_register_page_loads(client):
    # Test that the registration page loads successfully
    response = client.get("/register")
    assert response.status_code == 200
    assert b"<h2>Register</h2>" in response.data

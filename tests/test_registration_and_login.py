import os
import tempfile

import pytest
from dotenv import load_dotenv

# Import the application and database setup
from hushline import create_app, db
from hushline.generate_invite_codes import create_invite_code

# Import models and other modules
from hushline.model import User


@pytest.fixture
def client():
    # Load environment variables from .env file or the equivalent
    load_dotenv("env.sh")

    # Create a temporary directory for the SQLite database
    db_dir = tempfile.mkdtemp()

    # Use a simple file name without special characters
    db_file = "hushline.db"

    # Get the current working directory using Python's os module
    current_directory = os.getcwd()

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{os.path.join(current_directory, db_dir, db_file)}"
    )
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF protection for testing

    # Setup the app context and database schema
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

    # Clean up the temporary directory after tests are done
    import shutil

    shutil.rmtree(db_dir)


def test_user_registration_with_invite_code_disabled(client):
    # Prepare the environment to not require invite codes
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    # User registration data
    user_data = {"username": "test_user", "password": "SecurePassword123!"}

    # Post request to register a new user
    response = client.post("/register", data=user_data, follow_redirects=True)

    # Validate response
    assert response.status_code == 200
    assert b"Registration successful! Please log in." in response.data

    # Verify user is added to the database
    user = User.query.filter_by(primary_username="test_user").first()
    assert user is not None
    assert user.primary_username == "test_user"


def test_user_registration_with_invite_code_enabled(client):
    # Enable invite codes
    os.environ["REGISTRATION_CODES_REQUIRED"] = "True"

    # Generate a valid invite code using the script
    invite_code_str = create_invite_code()

    # User registration data with valid invite code
    user_data = {
        "username": "newuser",
        "password": "SecurePassword123!",
        "invite_code": invite_code_str,
    }

    # Post request to register a new user
    response = client.post("/register", data=user_data, follow_redirects=True)

    # Validate response
    assert response.status_code == 200
    assert b"Registration successful! Please log in." in response.data

    # Verify user is added to the database
    user = User.query.filter_by(primary_username="newuser").first()
    assert user is not None
    assert user.primary_username == "newuser"


def test_register_page_loads(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"<h2>Register</h2>" in response.data


def test_login_link(client):
    # Get the registration page
    response = client.get("/register")
    assert response.status_code == 200

    # Check if the login link is in the response
    assert (
        b'href="/login"' in response.data
    ), "Login link should be present on the registration page"

    # Simulate clicking the login link
    login_response = client.get("/login")
    assert login_response.status_code == 200
    assert b"<h2>Login</h2>" in login_response.data, "Should be on the login page now"


def test_registration_link(client):
    # Get the login page
    response = client.get("/login")
    assert response.status_code == 200, "Login page should be accessible"

    # Check if the registration link is in the response
    assert (
        b'href="/register"' in response.data
    ), "Registration link should be present on the login page"

    # Simulate clicking the registration link
    register_response = client.get("/register")
    assert register_response.status_code == 200, "Should be on the registration page now"
    assert b"<h2>Register</h2>" in register_response.data, "Should be on the registration page"


def test_user_login_after_registration(client):
    # Prepare the environment to not require invite codes
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    # User registration data
    registration_data = {"username": "newuser", "password": "SecurePassword123!"}

    # Post request to register a new user
    client.post("/register", data=registration_data, follow_redirects=True)

    # Login data should match the registration data
    login_data = {"username": "newuser", "password": "SecurePassword123!"}

    # Attempt to log in with the registered user
    login_response = client.post("/login", data=login_data, follow_redirects=True)

    # Validate login response
    assert login_response.status_code == 200
    assert b"Inbox" in login_response.data, "Should be redirected to the Inbox page"
    assert (
        b'href="/inbox?username=newuser"' in login_response.data
    ), "Inbox link should be present for the user"

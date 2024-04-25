import os

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

    # Use a simple file name without special characters
    db_file = "hushline.db"

    # Construct the database path based on the environment
    if os.environ.get("GITHUB_ACTIONS"):
        # GitHub Actions environment
        db_dir = "/home/runner/work/hushline/hushline"
        os.makedirs(db_dir, exist_ok=True)
    else:
        # Local testing environment
        db_dir = "/tmp/hushline"

    db_path = os.path.join(db_dir, db_file)

    print(f"SQLite database path: {db_path}")  # Print the database path for debugging

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    print("Creating test client...")  # Debug statement

    # Setup the app context and database schema
    with app.app_context():
        print("Creating database tables...")  # Debug statement
        try:
            db.create_all()
            print("Database tables created successfully.")  # Debug statement
        except Exception as e:
            print(f"Error creating database tables: {str(e)}")  # Debug statement
            raise

        yield app.test_client()

        print("Dropping database tables...")  # Debug statement
        try:
            db.drop_all()
            print("Database tables dropped successfully.")  # Debug statement
        except Exception as e:
            print(f"Error dropping database tables: {str(e)}")  # Debug statement
            raise

    # Clean up the temporary directory after tests are done (for local testing)
    if not os.environ.get("GITHUB_ACTIONS"):
        import shutil

        try:
            shutil.rmtree(db_dir)
            print(f"Temporary directory {db_dir} removed.")  # Debug statement
        except OSError as e:
            print(f"Error removing temporary directory: {e}")


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

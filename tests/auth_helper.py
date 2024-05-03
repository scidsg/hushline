import os

from hushline.model import User


def register_user(client, username, password):
    # Prepare the environment to not require invite codes
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"

    # User registration data
    user_data = {"username": username, "password": password}

    # Post request to register a new user
    response = client.post("/register", data=user_data, follow_redirects=True)

    # Validate response
    assert response.status_code == 200
    assert b"Registration successful! Please log in." in response.data

    # Verify user is added to the database
    user = User.query.filter_by(primary_username=username).first()
    assert user is not None
    assert user.primary_username == username

    # Return the registered user
    return user


def login_user(client, username, password):
    # Login data should match the registration data
    login_data = {"username": username, "password": password}

    # Attempt to log in with the registered user
    response = client.post("/login", data=login_data, follow_redirects=True)

    # Validate login response
    assert response.status_code == 200
    assert b"Inbox" in response.data
    assert (
        f'href="/inbox?username={username}"'.encode() in response.data
    ), f"Inbox link should be present for the user {username}"

    # Return the logged-in user
    return User.query.filter_by(primary_username=username).first()

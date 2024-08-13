from auth_helper import login_user, register_user
from flask.testing import FlaskClient

from hushline.model import Message


def get_captcha_from_session(client: FlaskClient, username: str) -> str:
    # Simulate loading the submit message page to generate and retrieve the CAPTCHA from the session
    response = client.get(f"/submit_message/{username}")
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer is not None  # Ensure the CAPTCHA was generated
        return captcha_answer

def test_submit_message_page_loads(client: FlaskClient) -> None:
    # Register a user
    user = register_user(client, "test_username", "Hush-Line-Test-Password9")

    # Verify that the user is registered correctly
    assert user is not None
    assert user.primary_username == "test_username"

    # Log in the user
    logged_in_user = login_user(client, "test_username", "Hush-Line-Test-Password9")

    # Verify that the logged-in user matches the registered user
    assert logged_in_user is not None
    assert logged_in_user.primary_username == "test_username"
    assert logged_in_user == user

    # Send a GET request to the submit_message page with follow_redirects=True
    response = client.get(f"/submit_message/{user.primary_username}")

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200

    # Assert that the page contains the expected content
    assert (
        f'<h2 class="submit">Submit a message to {user.primary_username}</h2>'.encode()
        in response.data
    )


def test_submit_message(client: FlaskClient) -> None:
    # Register a user
    user = register_user(client, "test_user", "Hush-Line-Test-Password9")

    # Log in the user
    login_user(client, "test_user", "Hush-Line-Test-Password9")

    # Get the CAPTCHA answer from the session
    captcha_answer = get_captcha_from_session(client, user.primary_username)

    # Prepare the message data
    message_data = {
        "content": "This is a test message.",
        "client_side_encrypted": "false",
        "captcha_answer": captcha_answer,
    }

    # Send a POST request to submit the message
    response = client.post(
        f"/submit_message/{user.primary_username}",
        data=message_data,
        follow_redirects=True,
    )

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200

    # Assert that the success message is displayed
    assert b"Message submitted successfully." in response.data

    # Verify that the message is saved in the database
    message = Message.query.filter_by(user_id=user.id).first()
    assert message is not None
    assert message.content == "This is a test message."

    # Navigate to the inbox with follow_redirects=True
    response = client.get(f"/inbox?username={user.primary_username}", follow_redirects=True)

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200

    # Assert that the submitted message is displayed in the inbox
    assert b"This is a test message." in response.data


def test_submit_message_with_contact_method(client: FlaskClient) -> None:
    # Register a user
    user = register_user(client, "test_user_concat", "Secure-Test-Pass123")
    assert user is not None

    # Log in the user
    login_success = login_user(client, "test_user_concat", "Secure-Test-Pass123")
    assert login_success

    # Get the CAPTCHA answer from the session
    captcha_answer = get_captcha_from_session(client, user.primary_username)

    # Prepare the message and contact method data
    message_content = "This is a test message."
    contact_method = "email@example.com"
    message_data = {
        "content": message_content,
        "contact_method": contact_method,
        "client_side_encrypted": "false",  # Simulate that this is not client-side encrypted
        "captcha_answer": captcha_answer,
    }

    # Send a POST request to submit the message
    response = client.post(
        f"/submit_message/{user.primary_username}",
        data=message_data,
        follow_redirects=True,
    )

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200
    assert b"Message submitted successfully." in response.data

    # Verify that the message is saved in the database
    message = Message.query.filter_by(user_id=user.id).first()
    assert message is not None

    # Check if the message content includes the concatenated contact method
    expected_content = f"Contact Method: {contact_method}\n\n{message_content}"
    assert message.content == expected_content

    # Navigate to the inbox to check if the message displays correctly
    response = client.get(f"/inbox?username={user.primary_username}", follow_redirects=True)
    assert response.status_code == 200
    assert expected_content.encode() in response.data

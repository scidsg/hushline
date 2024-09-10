from auth_helper import login_user, register_user
from bs4 import BeautifulSoup
from flask import Flask
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message


def get_captcha_from_session(client: FlaskClient, username: str) -> str:
    # Simulate loading the profile page to generate and retrieve the CAPTCHA from the session
    response = client.get(f"/to/{username}")
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer is not None  # Ensure the CAPTCHA was generated
        return captcha_answer


def test_profile_submit_message(client: FlaskClient) -> None:
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
        "captcha_answer": captcha_answer,  # Include the CAPTCHA answer
    }

    # Send a POST request to submit the message
    response = client.post(
        f"/to/{user.primary_username}",
        data=message_data,
        follow_redirects=True,
    )

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200

    # Assert that the success message is displayed
    assert b"Message submitted successfully." in response.data

    # Verify that the message is saved in the database
    message = db.session.scalars(db.select(Message).filter_by(user_id=user.id).limit(1)).first()
    assert message is not None
    assert message.content == "This is a test message."

    # Navigate to the inbox with follow_redirects=True
    response = client.get(f"/inbox?username={user.primary_username}", follow_redirects=True)

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200

    # Assert that the submitted message is displayed in the inbox
    assert b"This is a test message." in response.data


def test_profile_submit_message_with_contact_method(client: FlaskClient) -> None:
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
        "captcha_answer": captcha_answer,  # Include the CAPTCHA answer
    }

    # Send a POST request to submit the message
    response = client.post(
        f"/to/{user.primary_username}",
        data=message_data,
        follow_redirects=True,
    )

    # Assert that the response status code is 200 (OK)
    assert response.status_code == 200
    assert b"Message submitted successfully." in response.data

    # Verify that the message is saved in the database
    message = db.session.scalars(db.select(Message).filter_by(user_id=user.id).limit(1)).first()
    assert message is not None

    # Check if the message content includes the concatenated contact method
    expected_content = f"Contact Method: {contact_method}\n\n{message_content}"
    assert message.content == expected_content

    # Navigate to the inbox to check if the message displays correctly
    response = client.get(f"/inbox?username={user.primary_username}", follow_redirects=True)
    assert response.status_code == 200
    assert expected_content.encode() in response.data


def test_profile_pgp_required(client: FlaskClient, app: Flask) -> None:
    # Require PGP
    app.config["REQUIRE_PGP"] = True

    # Register a user (with no PGP key)
    user = register_user(client, "test_user", "Hush-Line-Test-Password9")

    # Load the profile page
    response = client.get(f"/to/{user.primary_username}")
    assert response.status_code == 200

    # The message form should not be displayed, and the PGP warning should be shown
    assert b"Sending messages is disabled" in response.data

    # Add a PGP key to the user
    user.pgp_key = "test_pgp_key"
    db.session.commit()

    # Load the profile page again
    response = client.get(f"/to/{user.primary_username}")
    assert response.status_code == 200

    # The message form should be displayed now
    assert b'id="messageForm"' in response.data
    assert b"You can't send encrypted messages to this user through Hush Line" not in response.data


def test_profile_extra_fields(client: FlaskClient, app: Flask) -> None:
    # Register a user
    user = register_user(client, "test_user", "Hush-Line-Test-Password9")
    user.extra_field_label1 = "Signal username"
    user.extra_field_value1 = "singleusername.666"
    user.extra_field_label2 = "Arbitrary Link"
    user.extra_field_value2 = "https://scidsg.org/"
    user.extra_field_label3 = "xss should fail"
    user.extra_field_value3 = "<script>alert('xss')</script>"
    db.session.commit()

    # Load the profile page
    response = client.get(f"/to/{user.primary_username}")
    assert response.status_code == 200

    # Check the HTML content using BeautifulSoup
    soup = BeautifulSoup(response.data, "html.parser")

    # Verify the signal username is displayed correctly
    signal_username_span = soup.find("span", class_="extra-field-value")
    assert signal_username_span is not None
    assert signal_username_span.text.strip() == "singleusername.666"

    # Verify the arbitrary link is present with correct attributes
    link = soup.find("a", href="https://scidsg.org/")
    assert link is not None
    assert link.get("target") == "_blank"
    assert "noopener" in link.get("rel", [])
    assert "noreferrer" in link.get("rel", [])

    # Verify that XSS is correctly escaped
    # Search for the XSS string directly in the HTML with both possible escapes
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in str(
        soup
    ) or "&lt;script&gt;alert('xss')&lt;/script&gt;" in str(soup)
    assert "<script>alert('xss')</script>" not in str(soup)


def test_profile_submit_message_with_invalid_captcha(client: FlaskClient) -> None:
    # Register a user
    user = register_user(client, "test_user_concat", "Secure-Test-Pass123")
    assert user is not None

    # Log in the user
    login_success = login_user(client, "test_user_concat", "Secure-Test-Pass123")
    assert login_success

    # Prepare the message and contact method data
    message_content = "This is a test message."
    contact_method = "email@example.com"
    message_data = {
        "content": message_content,
        "contact_method": contact_method,
        "client_side_encrypted": "false",
        "captcha_answer": 0,  # the answer is never 0
    }

    # Send a POST request to submit the message
    response = client.post(
        f"/to/{user.primary_username}",
        data=message_data,
        follow_redirects=True,
    )

    # Make sure there's a CAPTCHA error
    assert response.status_code == 200
    assert b"Incorrect CAPTCHA." in response.data

    # Make sure the contact method and message content are there
    assert contact_method.encode() in response.data
    assert message_content.encode() in response.data

    # Verify that the message is not saved in the database
    message = db.session.scalars(db.select(Message).filter_by(user_id=user.id).limit(1)).first()
    assert message is None

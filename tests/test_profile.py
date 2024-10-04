import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, User, Username


def get_captcha_from_session(client: FlaskClient, username: str) -> str:
    # Simulate loading the profile page to generate and retrieve the CAPTCHA from the session
    response = client.get(url_for("profile", username=username))
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer
        return captcha_answer


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message(client: FlaskClient, user: User) -> None:
    msg_content = "This is a test message."

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "content": msg_content,
            "client_side_encrypted": "false",
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert message.content == msg_content

    response = client.get(
        url_for("inbox", username=user.primary_username.username), follow_redirects=True
    )
    assert response.status_code == 200
    assert msg_content in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message_to_alias(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    msg_content = "This is a test message."

    response = client.post(
        url_for("profile", username=user_alias.username),
        data={
            "content": msg_content,
            "client_side_encrypted": "false",
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(db.select(Message).filter_by(username_id=user_alias.id)).one()
    assert message.content == msg_content

    response = client.get(url_for("inbox", username=user_alias.username), follow_redirects=True)
    assert response.status_code == 200
    assert msg_content in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message_with_contact_method(client: FlaskClient, user: User) -> None:
    message_content = "This is a test message."
    contact_method = "email@example.com"
    expected_content = f"Contact Method: {contact_method}\n\n{message_content}"

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "content": message_content,
            "contact_method": contact_method,
            "client_side_encrypted": "false",  # Simulate that this is not client-side encrypted
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert message.content == expected_content

    response = client.get(
        url_for("inbox", username=user.primary_username.username), follow_redirects=True
    )
    assert response.status_code == 200
    assert expected_content in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_pgp_required(client: FlaskClient, app: Flask, user: User) -> None:
    app.config["REQUIRE_PGP"] = True

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" in response.text

    user.pgp_key = "test_pgp_key"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    assert 'id="messageForm"' in response.text
    assert "You can't send encrypted messages to this user through Hush Line" not in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_extra_fields(client: FlaskClient, app: Flask, user: User) -> None:
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    user.primary_username.extra_field_label2 = "Arbitrary Link"
    user.primary_username.extra_field_value2 = "https://scidsg.org/"
    user.primary_username.extra_field_label3 = "xss should fail"
    user.primary_username.extra_field_value3 = "<script>alert('xss')</script>"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    signal_username_span = soup.find("span", class_="extra-field-value")
    assert signal_username_span is not None
    assert signal_username_span.text.strip() == "singleusername.666"

    link = soup.find("a", href="https://scidsg.org/")
    assert link is not None
    assert link.get("target") == "_blank"
    assert "noopener" in link.get("rel", [])
    assert "noreferrer" in link.get("rel", [])

    # Verify that XSS is correctly escaped
    # Search for the XSS string directly in the HTML with both possible escapes
    html_str = str(soup)
    assert (
        "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html_str
        or "&lt;script&gt;alert('xss')&lt;/script&gt;" in html_str
    )
    assert "<script>alert('xss')</script>" not in html_str


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message_with_invalid_captcha(client: FlaskClient, user: User) -> None:
    message_content = "This is a test message."
    contact_method = "email@example.com"

    # Send a POST request to submit the message
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "content": message_content,
            "contact_method": contact_method,
            "client_side_encrypted": "false",
            "captcha_answer": 0,  # the answer is never 0
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Incorrect CAPTCHA." in response.text

    assert contact_method in response.text
    assert message_content in response.text

    # Verify that the message is not saved in the database
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).one_or_none()
        is None
    )

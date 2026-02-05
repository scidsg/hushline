from unittest.mock import MagicMock, patch

import pytest
from flask import url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session

from hushline.db import db
from hushline.model import Message, User

msg_contact_method = "I prefer Signal."
msg_content = "This is a test message."

pgp_message_sig = "-----BEGIN PGP MESSAGE-----\n\n"
plaintext_new_message_body = "You have a new Hush Line message! Please log in to read it."


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_disabled(
    mock_do_send_email: MagicMock, client: FlaskClient, user: User
) -> None:
    # Disable email notifications
    user.enable_email_notifications = False
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "username_user_id": user.id,
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    # Check if do_send_email was not called
    mock_do_send_email.assert_not_called()

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_enabled_no_content(
    mock_do_send_email: MagicMock, client: FlaskClient, user: User
) -> None:
    # Enable email notifications, with no message content
    user.enable_email_notifications = True
    user.email_include_message_content = False
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "username_user_id": user.id,
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text

    # Check if do_send_email was called
    mock_do_send_email.assert_called_once_with(user, plaintext_new_message_body)

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_enabled_yes_content_no_encrypted_body(
    mock_do_send_email: MagicMock, client: FlaskClient, user: User
) -> None:
    # Enable email notifications, with no message content
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "username_user_id": user.id,
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text

    # Check if do_send_email was called
    mock_do_send_email.assert_called_once()

    # Check if the body contains the message content, mix of plaintext and ciphertext
    args, _ = mock_do_send_email.call_args
    assert "Contact Method" in args[1]
    assert "Message" in args[1]
    assert pgp_message_sig in args[1]

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_enabled_yes_content_yes_encrypted_body(
    mock_do_send_email: MagicMock, client: FlaskClient, user: User
) -> None:
    # Enable email notifications, with no message content
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    encrypted_email_body = (
        "-----BEGIN PGP MESSAGE-----\n\nfake encrypted body\n\n-----END PGP MESSAGE-----"
    )

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "username_user_id": user.id,
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text

    # Check if do_send_email was called with encrypted email body
    mock_do_send_email.assert_called_once_with(user, encrypted_email_body)

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_enabled_yes_content_yes_encrypted_body_failed_client_encryption(
    mock_do_send_email: MagicMock, client: FlaskClient, user: User
) -> None:
    # Enable email notifications, with no message content
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    encrypted_email_body = ""

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "username_user_id": user.id,
            "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text

    # Check if do_send_email was called with plaintext message
    mock_do_send_email.assert_called_once_with(user, plaintext_new_message_body)

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text

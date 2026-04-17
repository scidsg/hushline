from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_profile_submission_data

from hushline.db import db
from hushline.model import Message, NotificationRecipient, User
from hushline.routes.common import format_full_message_email_body

msg_contact_method = "I prefer Signal."
msg_content = "This is a test message."

pgp_message_sig = "-----BEGIN PGP MESSAGE-----\n\n"
plaintext_new_message_body = "You have a new Hush Line message! Please log in to read it."


def _configure_default_smtp(app: Flask) -> None:
    app.config["SMTP_USERNAME"] = "default-user"
    app.config["SMTP_SERVER"] = "smtp.default.example"
    app.config["SMTP_PORT"] = 587
    app.config["SMTP_PASSWORD"] = "default-pass"
    app.config["NOTIFICATIONS_ADDRESS"] = "notify@example.com"
    app.config["NOTIFICATIONS_REPLY_TO"] = "reply@example.com"
    app.config["SMTP_ENCRYPTION"] = "StartTLS"


def _add_secondary_recipient(user: User, pgp_key: str | None = None) -> None:
    user.notification_recipients.append(NotificationRecipient(position=1, enabled=True))
    user.notification_recipients[-1].email = "secondary@example.com"
    user.notification_recipients[-1].pgp_key = pgp_key or Path("tests/test_pgp_key.txt").read_text()


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
            **get_profile_submission_data(client, user.primary_username.username),
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
            **get_profile_submission_data(client, user.primary_username.username),
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
def test_notifications_enabled_no_content_delivers_to_all_enabled_recipients(
    app: Flask,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_default_smtp(app)
    user.enable_email_notifications = True
    user.email_include_message_content = False
    user.email = "primary@example.com"
    _add_secondary_recipient(user)
    db.session.commit()

    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    assert [call.args[0] for call in send_email.call_args_list] == [
        "primary@example.com",
        "secondary@example.com",
    ]
    assert [call.args[2] for call in send_email.call_args_list] == [
        plaintext_new_message_body,
        plaintext_new_message_body,
    ]
    create_smtp_config.assert_called_once()


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
            **get_profile_submission_data(client, user.primary_username.username),
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
def test_notifications_enabled_yes_content_no_encrypted_body_delivers_to_all_enabled_recipients(
    app: Flask,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_default_smtp(app)
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    user.email = "primary@example.com"
    _add_secondary_recipient(user)
    db.session.commit()

    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    assert [call.args[0] for call in send_email.call_args_list] == [
        "primary@example.com",
        "secondary@example.com",
    ]
    bodies = [call.args[2] for call in send_email.call_args_list]
    assert len(set(bodies)) == 1
    assert "Contact Method" in bodies[0]
    assert "Message" in bodies[0]
    assert pgp_message_sig in bodies[0]
    create_smtp_config.assert_called_once()


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_enabled_yes_content_yes_encrypted_body(
    mock_do_send_email: MagicMock,
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
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
            **get_profile_submission_data(client, user.primary_username.username),
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
    # Frontend-provided encrypted body should be sent as-is without server re-encryption.
    mock_encrypt_message.assert_not_called()

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_full_body_encryption_embedded_markers_use_server_fallback(
    mock_do_send_email: MagicMock,
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    encrypted_email_body = (
        "prefix text\n-----BEGIN PGP MESSAGE-----\nnot actually armored\n"
        "-----END PGP MESSAGE-----\nsuffix text"
    )
    server_encrypted_email_body = (
        "-----BEGIN PGP MESSAGE-----\n\nserver encrypted body\n\n-----END PGP MESSAGE-----"
    )
    mock_encrypt_message.return_value = server_encrypted_email_body

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    expected_fallback_body = format_full_message_email_body(
        [("Contact Method", msg_contact_method), ("Message", msg_content)]
    )
    mock_encrypt_message.assert_called_once_with(expected_fallback_body, user.pgp_key)
    mock_do_send_email.assert_called_once_with(user, server_encrypted_email_body)


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message")
def test_notifications_full_body_encryption_prefers_client_body_for_all_enabled_recipients(
    mock_encrypt_message: MagicMock,
    app: Flask,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_default_smtp(app)
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "primary@example.com"
    _add_secondary_recipient(user)
    db.session.commit()

    client_encrypted_email_body = (
        "-----BEGIN PGP MESSAGE-----\n\nclient encrypted body\n\n-----END PGP MESSAGE-----"
    )
    create_smtp_config = MagicMock(return_value=MagicMock())
    send_email = MagicMock()
    monkeypatch.setattr("hushline.routes.common.create_smtp_config", create_smtp_config)
    monkeypatch.setattr("hushline.routes.common.send_email", send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": client_encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    mock_encrypt_message.assert_not_called()
    assert [call.args[0] for call in send_email.call_args_list] == [
        "primary@example.com",
        "secondary@example.com",
    ]
    assert [call.args[2] for call in send_email.call_args_list] == [
        client_encrypted_email_body,
        client_encrypted_email_body,
    ]
    create_smtp_config.assert_called_once()


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_full_body_encryption_server_fallback(
    mock_do_send_email: MagicMock,
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    # Enable email notifications, with no message content
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    encrypted_email_body = ""
    server_encrypted_email_body = (
        "-----BEGIN PGP MESSAGE-----\n\nserver encrypted body\n\n-----END PGP MESSAGE-----"
    )
    mock_encrypt_message.return_value = server_encrypted_email_body

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
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

    expected_fallback_body = format_full_message_email_body(
        [("Contact Method", msg_contact_method), ("Message", msg_content)]
    )
    mock_encrypt_message.assert_called_once_with(expected_fallback_body, user.pgp_key)

    mock_do_send_email.assert_called_once()
    args, _ = mock_do_send_email.call_args
    assert args[0] == user
    assert args[1] == server_encrypted_email_body
    assert plaintext_new_message_body not in args[1]

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.model.field_value.encrypt_message")
@patch("hushline.routes.profile.encrypt_message")
@patch("hushline.routes.profile.do_send_email")
def test_notifications_full_body_encryption_uses_all_enabled_recipient_keys(
    mock_do_send_email: MagicMock,
    mock_encrypt_message: MagicMock,
    mock_field_value_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.notification_recipients.append(NotificationRecipient(position=1, enabled=True))
    user.notification_recipients[-1].email = "secondary@example.com"
    user.notification_recipients[-1].pgp_key = "secondary-key"
    db.session.commit()

    client_encrypted_email_body = (
        "-----BEGIN PGP MESSAGE-----\n\nclient encrypted body\n\n-----END PGP MESSAGE-----"
    )
    mock_field_value_encrypt_message.return_value = (
        "-----BEGIN PGP MESSAGE-----\n\nfield encrypted body\n\n-----END PGP MESSAGE-----"
    )

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": client_encrypted_email_body,
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    mock_encrypt_message.assert_not_called()
    mock_do_send_email.assert_called_once_with(user, client_encrypted_email_body)

import re
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import FieldValue, Message, User


def _csrf_token_from_message_page(client: FlaskClient, public_id: str) -> str | None:
    response = client.get(url_for("message", public_id=public_id))
    assert response.status_code == 200
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text)
    return match.group(1) if match else None


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_sends_per_field(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    user.email = "test@example.com"
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    for field_def in user.primary_username.message_fields[:2]:
        field_def.encrypted = False
        field_value = FieldValue(
            field_def,
            message,
            "test_value",
            field_def.encrypted,
        )
        db.session.add(field_value)
    db.session.commit()

    sent = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    assert len(sent) == 2
    assert all(sent_user_id == user.id for sent_user_id, _ in sent)


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_blocks_other_users_messages(
    client: FlaskClient, user: User, message2: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email = "test@example.com"
    db.session.commit()

    sent = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    owned_message = Message(username_id=user.primary_username.id)
    db.session.add(owned_message)
    db.session.commit()

    csrf_token = _csrf_token_from_message_page(client, owned_message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message2.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message not found" in response.text
    assert sent == []


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_requires_email_notifications(
    client: FlaskClient, user: User, message: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = False
    user.email_include_message_content = True
    user.email = "test@example.com"
    db.session.commit()

    sent = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Email notifications are disabled" in response.text
    assert sent == []


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_requires_csrf_token(
    app: Flask, client: FlaskClient, user: User, message: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email = "test@example.com"
    db.session.commit()

    sent = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    prior_csrf_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("resend_message", public_id=message.public_id),
            data={},
            follow_redirects=True,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_csrf_setting

    assert response.status_code == 200
    assert "Invalid resend request" in response.text
    assert sent == []


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_button_visible_with_required_settings(
    client: FlaskClient, user: User, message: Message
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    db.session.commit()

    response = client.get(url_for("message", public_id=message.public_id))
    assert response.status_code == 200
    assert "Resend to Email" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_button_hidden_without_notifications_or_content(
    client: FlaskClient, user: User, message: Message
) -> None:
    user.enable_email_notifications = False
    user.email_include_message_content = True
    db.session.commit()

    response = client.get(url_for("message", public_id=message.public_id))
    assert response.status_code == 200
    assert "Resend to Email" not in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.message.encrypt_message")
def test_resend_message_full_body_uses_existing_armored_value_without_reencryption(
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "test@example.com"
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    armored_value = "-----BEGIN PGP MESSAGE-----\n\nalready encrypted\n\n-----END PGP MESSAGE-----"
    field_def = user.primary_username.message_fields[0]
    field_def.encrypted = False
    db.session.add(FieldValue(field_def, message, armored_value, field_def.encrypted))
    db.session.commit()

    sent: list[tuple[int, str]] = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    mock_encrypt_message.assert_not_called()
    assert sent == [(user.id, armored_value)]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.message.encrypt_message")
def test_resend_message_full_body_encrypts_plaintext_value(
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "test@example.com"
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    plaintext_value = "plain resend content"
    encrypted_value = (
        "-----BEGIN PGP MESSAGE-----\n\nserver encrypted resend\n\n-----END PGP MESSAGE-----"
    )
    mock_encrypt_message.return_value = encrypted_value

    field_def = user.primary_username.message_fields[0]
    field_def.encrypted = False
    db.session.add(FieldValue(field_def, message, plaintext_value, field_def.encrypted))
    db.session.commit()

    sent: list[tuple[int, str]] = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    mock_encrypt_message.assert_called_once_with(plaintext_value, user.pgp_key)
    assert sent == [(user.id, encrypted_value)]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.message.encrypt_message", side_effect=ValueError("encryption failed"))
def test_resend_message_full_body_encryption_failure_falls_back_to_generic(
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "test@example.com"
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    field_def = user.primary_username.message_fields[0]
    field_def.encrypted = False
    db.session.add(FieldValue(field_def, message, "plain resend content", field_def.encrypted))
    db.session.commit()

    sent: list[tuple[int, str]] = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    mock_encrypt_message.assert_called_once()
    assert sent == [(user.id, "You have a new Hush Line message! Please log in to read it.")]

    user.enable_email_notifications = True
    user.email_include_message_content = False
    db.session.commit()

    response = client.get(url_for("message", public_id=message.public_id))
    assert response.status_code == 200
    assert "Resend to Email" not in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_include_content_false_sends_generic(
    client: FlaskClient, user: User, message: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = False
    user.email = "test@example.com"
    db.session.commit()

    sent: list[tuple[int, str]] = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    assert sent == [(user.id, "You have a new Hush Line message! Please log in to read it.")]


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_include_content_true_with_empty_values_sends_generic(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    user.email = "test@example.com"
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    field_def = user.primary_username.message_fields[0]
    field_def.encrypted = False
    db.session.add(FieldValue(field_def, message, "", field_def.encrypted))
    db.session.commit()

    sent: list[tuple[int, str]] = []

    def fake_send_email(sent_user: User, body: str) -> None:
        sent.append((sent_user.id, body))

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    csrf_token = _csrf_token_from_message_page(client, message.public_id)
    post_data = {"csrf_token": csrf_token} if csrf_token else {}
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        data=post_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message resent to your email inbox" in response.text
    assert sent == [(user.id, "You have a new Hush Line message! Please log in to read it.")]

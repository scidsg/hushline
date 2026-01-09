import re

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

    user.enable_email_notifications = True
    user.email_include_message_content = False
    db.session.commit()

    response = client.get(url_for("message", public_id=message.public_id))
    assert response.status_code == 200
    assert "Resend to Email" not in response.text

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import FieldValue, Message, User
from hushline.routes.common import PLAINTEXT_NEW_MESSAGE_BODY


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_sends_email_with_field_values(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.email = "test@example.com"
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    # Limit the field list so the expected email body stays readable in the assertion below.
    selected_fields = user.primary_username.message_fields[:2]
    extracted_fields = []
    for index, field_def in enumerate(selected_fields):
        value = f"value-{index}"
        field_value = FieldValue(field_def, message, value, field_def.encrypted)
        db.session.add(field_value)
        extracted_fields.append((field_def.label, value))
    db.session.commit()

    sent = {}

    def fake_send_email(user_arg: User, body: str) -> None:
        sent["user"] = user_arg
        sent["body"] = body

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    # CSRF is disabled for tests by default in conftest, so we can post directly.
    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        follow_redirects=True,
    )

    expected_body = "".join(
        f"\n\n{name}\n\n{value}\n\n==============" for name, value in extracted_fields
    ).strip()
    assert response.status_code == 200
    assert "Email resent successfully" in response.text
    assert sent["user"] == user
    assert sent["body"] == expected_body


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_blocks_other_users_messages(
    client: FlaskClient, user: User, user2: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Prevent users from using the resend endpoint to spam or access other users' messages.
    message = Message(username_id=user2.primary_username.id)
    db.session.add(message)
    db.session.flush()

    field_def = user2.primary_username.message_fields[0]
    db.session.add(FieldValue(field_def, message, "value", field_def.encrypted))
    db.session.commit()

    def fake_send_email(*_: object, **__: object) -> None:
        raise AssertionError("Email should not be sent for other users' messages.")

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message not found" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_resend_message_falls_back_to_generic_body_when_encrypted(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.email = "test@example.com"
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    field_def = user.primary_username.message_fields[0]
    db.session.add(FieldValue(field_def, message, "value", field_def.encrypted))
    db.session.commit()

    sent = {}

    def fake_send_email(user_arg: User, body: str) -> None:
        sent["user"] = user_arg
        sent["body"] = body

    monkeypatch.setattr("hushline.routes.message.do_send_email", fake_send_email)

    response = client.post(
        url_for("resend_message", public_id=message.public_id),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Email resent successfully" in response.text
    assert sent["user"] == user
    assert sent["body"] == PLAINTEXT_NEW_MESSAGE_BODY

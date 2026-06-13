import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from flask import url_for
from flask.testing import FlaskClient
from helpers import get_profile_submission_data

from hushline import auth
from hushline.db import db
from hushline.model import ChatKey, FieldValue, Message, MessageStatus, User, Username

MSG_CONTACT_METHOD = "I prefer Signal."
MSG_CONTENT = "This is a test message."


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True


def _set_pgp_key(user: User) -> None:
    user.pgp_key = Path("tests/test_pgp_key.txt").read_text()


def _add_chat_key(user: User, public_key: str) -> None:
    db.session.add(
        ChatKey(
            user=user,
            key_version=1,
            public_key=public_key,
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000, "hash": "SHA-256"},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )


def _chat_ciphertext(label: str) -> str:
    return json.dumps(
        {
            "algorithm": "ECDH-P256-AES-GCM",
            "ephemeral_public_key": '{"kty":"EC","crv":"P-256","x":"ephemeral","y":"key"}',
            "iv": f"iv-{label}",
            "ciphertext": f"ciphertext-{label}",
        }
    )


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_delete_own_message(client: FlaskClient, user: User) -> None:
    # Create a message for the authenticated user
    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.flush()

    for field_def in user.primary_username.message_fields:
        field_value = FieldValue(
            field_def,
            message,
            "test_value",
            field_def.encrypted,
        )
        db.session.add(field_value)
        db.session.commit()

    # Attempt to delete the user's own message
    response = client.post(
        url_for("delete_message", public_id=message.public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message deleted successfully" in response.text
    assert db.session.get(Message, message.id) is None  # Ensure message was deleted


@pytest.mark.usefixtures("_authenticated_user")
def test_cannot_delete_other_user_message(
    client: FlaskClient, user: User, user_password: str
) -> None:
    # Create another user within the test
    other_user = User(password=user_password)
    db.session.add(other_user)
    db.session.flush()

    other_username = Username(user_id=other_user.id, _username="otheruser", is_primary=True)
    db.session.add(other_username)
    db.session.commit()

    # Create a message for the other user
    other_user_message = Message(username_id=other_username.id)
    db.session.add(other_user_message)
    db.session.commit()

    for field_def in other_username.message_fields:
        field_value = FieldValue(
            field_def,
            other_user_message,
            "test_value",
            field_def.encrypted,
        )
        db.session.add(field_value)
        db.session.commit()

    # Attempt to delete the other user's message
    response = client.post(
        url_for("delete_message", public_id=other_user_message.public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message not found" in response.text
    assert (
        db.session.get(Message, other_user_message.id) is not None
    )  # Ensure message was not deleted


@pytest.mark.usefixtures("_authenticated_user")
def test_filter_on_status(client: FlaskClient, user: User, user_alias: Username) -> None:
    messages = []
    for status in MessageStatus:
        message = Message(username_id=user.primary_username.id)
        message.status = status
        db.session.add(message)
        db.session.flush()
        messages.append(message)

        for field_def in user.primary_username.message_fields:
            field_def.encrypted = False

        for field_def in user.primary_username.message_fields:
            field_value = FieldValue(
                field_def,
                message,
                "test_value",
                field_def.encrypted,
            )
            db.session.add(field_value)
            db.session.flush()
    db.session.commit()

    # no filter
    resp = client.get(url_for("inbox"))
    for msg in messages:
        assert resp.status_code == 200
        assert f'href="{url_for("message", public_id=msg.public_id)}"' in resp.text
        assert f"To: @{user.primary_username.username}" in resp.text

    # status filter
    for msg in messages:
        resp = client.get(url_for("inbox", status=msg.status.value))

        # find match
        assert resp.status_code == 200
        assert f'href="{url_for("message", public_id=msg.public_id)}"' in resp.text

        # don't find the other matches
        for other_msg in messages:
            if other_msg.public_id != msg.public_id:
                assert (
                    f'href="{url_for("message", public_id=other_msg.public_id)}"' not in resp.text
                )


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_lists_conversation_for_sender_and_recipient_after_submission(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _set_pgp_key(user2)
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    db.session.commit()

    response = client.post(
        url_for("profile", username=user2.primary_username.username),
        data={
            "field_0": MSG_CONTACT_METHOD,
            "field_1": MSG_CONTENT,
            "encrypted_conversation_copies": json.dumps(
                {
                    "sender": _chat_ciphertext("sender-initial"),
                    "recipient": _chat_ciphertext("recipient-initial"),
                }
            ),
            **get_profile_submission_data(client, user2.primary_username.username),
        },
        follow_redirects=False,
    )

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user2.primary_username.id)
    ).one()
    assert message.conversation is not None
    initial_conversation_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    newer_tip_at = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
    message.created_at = initial_conversation_at
    message.conversation.messages[0].created_at = initial_conversation_at
    newer_tip = Message(username_id=user2.primary_username.id)
    newer_tip.status = MessageStatus.ARCHIVED
    newer_tip.created_at = newer_tip_at
    db.session.add(newer_tip)
    db.session.commit()

    conversation_url = url_for("conversation", conversation_id=message.conversation.id)
    message_url = url_for("message", public_id=message.public_id)
    newer_tip_url = url_for("message", public_id=newer_tip.public_id)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(conversation_url)

    sender_response = client.get(url_for("inbox"))
    assert sender_response.status_code == 200
    assert conversation_url in sender_response.text
    assert f"From: @{user2.primary_username.username}" in sender_response.text
    assert f"To: @{user.primary_username.username}" in sender_response.text
    assert MSG_CONTACT_METHOD not in sender_response.text
    assert MSG_CONTENT not in sender_response.text
    assert "Proton" not in sender_response.text
    assert "PGP" not in sender_response.text

    message.status = MessageStatus.ARCHIVED
    db.session.commit()
    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("inbox"))
    assert recipient_response.status_code == 200
    assert recipient_response.text.index(newer_tip_url) < recipient_response.text.index(
        conversation_url
    )
    assert conversation_url in recipient_response.text
    assert f"From: @{user.primary_username.username}" in recipient_response.text
    assert f"To: @{user2.primary_username.username}" in recipient_response.text
    assert MSG_CONTACT_METHOD not in recipient_response.text
    assert MSG_CONTENT not in recipient_response.text

    tips_response = client.get(url_for("inbox", type="tips"))
    assert tips_response.status_code == 200
    assert newer_tip_url in tips_response.text
    assert conversation_url not in tips_response.text
    assert "Go to conversation" not in tips_response.text

    conversations_response = client.get(url_for("inbox", type="conversations"))
    assert conversations_response.status_code == 200
    assert conversation_url in conversations_response.text
    assert newer_tip_url not in conversations_response.text
    assert "Go to message" not in conversations_response.text

    pending_response = client.get(url_for("inbox", status=MessageStatus.PENDING.value))
    assert pending_response.status_code == 200
    assert conversation_url not in pending_response.text
    assert f'href="{message_url}"' not in pending_response.text

    archived_response = client.get(url_for("inbox", status=MessageStatus.ARCHIVED.value))
    assert archived_response.status_code == 200
    assert conversation_url not in archived_response.text
    assert f'href="{newer_tip_url}"' in archived_response.text
    assert f'href="{message_url}"' not in archived_response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_invalid_status_returns_bad_request(client: FlaskClient) -> None:
    response = client.get(url_for("inbox", status="not-a-status"), follow_redirects=False)
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_invalid_type_filter_returns_bad_request(client: FlaskClient) -> None:
    response = client.get(url_for("inbox", type="not-a-type"), follow_redirects=False)
    assert response.status_code == 400


def test_inbox_missing_user_row_returns_not_found(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth, "get_session_user", lambda: object())

    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess["user_id"] = 999999
        sess["session_id"] = "invalid-session-id"
        sess["username"] = "ghost"

    response = client.get(url_for("inbox"), follow_redirects=False)
    assert response.status_code == 404

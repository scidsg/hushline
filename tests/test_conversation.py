import json
from datetime import datetime, timedelta, timezone

from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    ChatKey,
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    User,
)


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True


def _add_chat_key(user: User, public_key: str) -> None:
    db.session.add(
        ChatKey(
            user=user,
            key_version=1,
            public_key=public_key,
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )


def _ciphertext(label: str) -> str:
    return json.dumps(
        {
            "algorithm": "ECDH-P256-AES-GCM",
            "ephemeral_public_key": '{"kty":"EC","crv":"P-256","x":"ephemeral","y":"key"}',
            "iv": f"iv-{label}",
            "ciphertext": f"ciphertext-{label}",
        }
    )


def _make_conversation(
    sender: User,
    recipient: User,
    *,
    include_initial_copy: bool = True,
) -> Conversation:
    conversation = Conversation()
    sender_participant = ConversationParticipant()
    sender_participant.conversation = conversation
    sender_participant.user = sender
    sender_participant.has_usable_public_key = True
    recipient_participant = ConversationParticipant()
    recipient_participant.conversation = conversation
    recipient_participant.user = recipient
    recipient_participant.has_usable_public_key = True
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = sender_participant
    if include_initial_copy:
        sender_copy = ConversationMessageCopy()
        sender_copy.recipient_participant = sender_participant
        sender_copy.encrypted_payload = _ciphertext("sender-initial")
        recipient_copy = ConversationMessageCopy()
        recipient_copy.recipient_participant = recipient_participant
        recipient_copy.encrypted_payload = _ciphertext("recipient-initial")
        conversation_message.encrypted_copies.extend(
            [
                sender_copy,
                recipient_copy,
            ]
        )
    db.session.add(conversation)
    db.session.commit()
    return conversation


def _copies_for(conversation: Conversation, label: str) -> dict[str, str]:
    return {
        str(participant.id): _ciphertext(f"{label}-{participant.id}")
        for participant in conversation.participants
    }


def _participant_for(conversation: Conversation, user: User) -> ConversationParticipant:
    participant = conversation.participant_for_user_id(user.id)
    assert participant is not None
    return participant


def _set_initial_message_created_at(conversation: Conversation, created_at: datetime) -> None:
    conversation.messages[0].created_at = created_at
    db.session.commit()


def _add_conversation_message(
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    *,
    created_at: datetime,
    label: str,
) -> ConversationMessage:
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = sender_participant
    conversation_message.created_at = created_at
    for recipient_participant in conversation.participants:
        encrypted_copy = ConversationMessageCopy()
        encrypted_copy.recipient_participant = recipient_participant
        encrypted_copy.encrypted_payload = _ciphertext(f"{label}-{recipient_participant.id}")
        conversation_message.encrypted_copies.append(encrypted_copy)
    db.session.add(conversation_message)
    db.session.commit()
    return conversation_message


def test_conversation_route_authorizes_only_participants(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    conversation = _make_conversation(user, user2)

    _authenticate_as(client, user)
    sender_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert sender_response.status_code == 200
    assert "Unlock your Hush Line chat key" in sender_response.text

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert recipient_response.status_code == 200
    assert "Unlock your Hush Line chat key" in recipient_response.text

    _authenticate_as(client, admin_user)
    unrelated_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert unrelated_response.status_code == 404

    with client.session_transaction() as session:
        session.clear()
    unauthenticated_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert unauthenticated_response.status_code == 302
    assert unauthenticated_response.headers["Location"].endswith(url_for("login"))


def test_conversation_view_shows_locked_chat_key_state(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.get(url_for("conversation", conversation_id=conversation.id))

    assert response.status_code == 200
    assert "Transcript content is hidden until your chat key is unlocked" in response.text
    assert (
        "Replies are unavailable until every participant has an active Hush Line chat key."
        in response.text
    )
    assert "Do not upload or paste any external private key." in response.text
    assert "Proton" not in response.text
    assert "PGP" not in response.text


def test_participant_can_append_encrypted_conversation_message(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    conversation = _make_conversation(user, user2)
    plaintext = "plaintext follow-up must not be stored"
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", conversation_id=conversation.id),
        json={"encrypted_copies": _copies_for(conversation, "follow-up")},
    )

    assert response.status_code == 201
    messages = db.session.scalars(
        db.select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.asc())
    ).all()
    assert len(messages) == 2
    assert messages[-1].sender_participant.user_id == user.id
    assert len(messages[-1].encrypted_copies) == 2
    for encrypted_copy in messages[-1].encrypted_copies:
        assert "ECDH-P256-AES-GCM" in encrypted_copy.encrypted_payload
        assert plaintext not in encrypted_copy.encrypted_payload


def test_append_conversation_message_rejects_invalid_payload_without_leaking_content(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    leaked_content = "plaintext disclosure"

    response = client.post(
        url_for("append_conversation_message", conversation_id=conversation.id),
        json={
            "encrypted_copies": {
                str(participant.id): leaked_content for participant in conversation.participants
            }
        },
    )

    assert response.status_code == 400
    assert "Invalid encrypted message payload." in response.text
    assert leaked_content not in response.text
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_requires_csrf_when_enabled(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("append_conversation_message", conversation_id=conversation.id),
            json={"encrypted_copies": _copies_for(conversation, "csrf")},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_rejects_non_participant(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, admin_user)

    response = client.post(
        url_for("append_conversation_message", conversation_id=conversation.id),
        json={"encrypted_copies": _copies_for(conversation, "unrelated")},
    )

    assert response.status_code == 404
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_redirects_unauthenticated_user(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    conversation = _make_conversation(user, user2)

    response = client.post(
        url_for("append_conversation_message", conversation_id=conversation.id),
        json={"encrypted_copies": _copies_for(conversation, "unauthenticated")},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_recipient_unread_indicator_clears_when_locked_thread_loads(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    initial_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _set_initial_message_created_at(conversation, initial_created_at)
    recipient_participant.last_read_at = initial_created_at
    db.session.commit()
    latest_message = _add_conversation_message(
        conversation,
        sender_participant,
        created_at=initial_created_at + timedelta(minutes=5),
        label="recipient-unread",
    )
    _authenticate_as(client, user2)

    unread_response = client.get(url_for("inbox"))

    assert unread_response.status_code == 200
    assert 'aria-label="Unread conversation"' in unread_response.text

    thread_response = client.get(url_for("conversation", conversation_id=conversation.id))

    assert thread_response.status_code == 200
    assert "Transcript content is hidden until your chat key is unlocked" in thread_response.text
    db.session.refresh(recipient_participant)
    assert recipient_participant.last_read_at == latest_message.created_at

    read_response = client.get(url_for("inbox"))
    assert read_response.status_code == 200
    assert 'aria-label="Unread conversation"' not in read_response.text


def test_inbox_unread_indicator_uses_latest_message_for_each_participant(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    user_participant = _participant_for(conversation, user)
    user2_participant = _participant_for(conversation, user2)
    initial_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _set_initial_message_created_at(conversation, initial_created_at)
    user_participant.last_read_at = initial_created_at
    user2_participant.last_read_at = initial_created_at
    db.session.commit()
    _add_conversation_message(
        conversation,
        user2_participant,
        created_at=initial_created_at + timedelta(minutes=5),
        label="incoming",
    )
    _add_conversation_message(
        conversation,
        user_participant,
        created_at=initial_created_at + timedelta(minutes=10),
        label="own-latest",
    )

    _authenticate_as(client, user)
    sender_response = client.get(url_for("inbox"))

    assert sender_response.status_code == 200
    assert 'aria-label="Unread conversation"' not in sender_response.text

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("inbox"))

    assert recipient_response.status_code == 200
    assert 'aria-label="Unread conversation"' in recipient_response.text

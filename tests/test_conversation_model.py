from datetime import datetime, timezone

from flask import Flask

from hushline.db import db
from hushline.model import (
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    Message,
    User,
)


def _make_conversation(
    user: User, user2: User
) -> tuple[
    Conversation,
    ConversationParticipant,
    ConversationParticipant,
]:
    conversation = Conversation()
    participant = ConversationParticipant()
    participant.conversation = conversation
    participant.user = user
    participant.has_usable_public_key = True
    participant2 = ConversationParticipant()
    participant2.conversation = conversation
    participant2.user = user2
    db.session.add(conversation)
    db.session.commit()
    return conversation, participant, participant2


def test_conversation_membership_is_user_id_based(app: Flask, user: User, user2: User) -> None:
    conversation, participant, participant2 = _make_conversation(user, user2)

    user_conversations = db.session.scalars(Conversation.for_user_id(user.id)).all()
    user2_conversations = db.session.scalars(Conversation.for_user_id(user2.id)).all()
    missing_conversations = db.session.scalars(Conversation.for_user_id(999_999)).all()

    assert user_conversations == [conversation]
    assert user2_conversations == [conversation]
    assert missing_conversations == []
    assert conversation.participant_for_user_id(user.id) == participant
    assert conversation.participant_for_user_id(user2.id) == participant2
    assert conversation.participant_for_user_id(999_999) is None


def test_conversation_message_has_encrypted_copies(
    app: Flask,
    user: User,
    user2: User,
) -> None:
    conversation, participant, participant2 = _make_conversation(user, user2)
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = participant
    copy = ConversationMessageCopy()
    copy.message = conversation_message
    copy.recipient_participant = participant
    copy.encrypted_payload = "encrypted-for-sender"
    copy2 = ConversationMessageCopy()
    copy2.message = conversation_message
    copy2.recipient_participant = participant2
    copy2.encrypted_payload = "encrypted-for-recipient"
    db.session.add(conversation_message)
    db.session.commit()

    assert conversation.messages == [conversation_message]
    assert conversation_message.sender_participant == participant
    assert conversation_message.encrypted_copies == [copy, copy2]
    assert participant.encrypted_copies == [copy]
    assert participant2.encrypted_copies == [copy2]
    assert {
        column.name for column in db.metadata.tables["conversation_messages"].columns
    }.isdisjoint({"body", "content", "plaintext", "message_body"})
    assert {
        column.name for column in db.metadata.tables["conversation_message_copies"].columns
    }.isdisjoint({"body", "content", "plaintext", "message_body"})


def test_participant_read_state_and_key_defaults(app: Flask, user: User, user2: User) -> None:
    conversation, participant, participant2 = _make_conversation(user, user2)

    assert participant.has_usable_public_key is True
    assert participant.last_read_at is None
    assert participant.last_active_at is None
    assert participant2.has_usable_public_key is False
    assert participant2.last_read_at is None
    assert participant2.last_active_at is None

    read_at = datetime.now(timezone.utc)
    active_at = datetime.now(timezone.utc)
    participant2.last_read_at = read_at
    participant2.last_active_at = active_at
    db.session.add(conversation)
    db.session.commit()

    assert participant2.last_read_at == read_at
    assert participant2.last_active_at == active_at


def test_initial_message_can_link_to_conversation(
    app: Flask,
    user: User,
    user2: User,
    message: Message,
) -> None:
    conversation, _, _ = _make_conversation(user, user2)

    message.conversation = conversation
    db.session.add(message)
    db.session.commit()

    assert message.conversation == conversation
    assert conversation.initial_message == message

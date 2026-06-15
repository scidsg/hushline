from dataclasses import dataclass
from datetime import datetime

from flask import (
    Flask,
    abort,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    Conversation,
    ConversationMessage,
    ConversationParticipant,
    Message,
    MessageStatus,
    User,
    Username,
)

VALID_INBOX_TYPE_FILTERS = {"tips", "conversations"}


@dataclass(frozen=True)
class InboxConversation:
    conversation: Conversation
    other_participant_names: list[str]
    latest_at: datetime
    message_count: int
    has_unread: bool
    has_available_copy: bool


@dataclass(frozen=True)
class InboxItem:
    kind: str
    sort_at: datetime
    conversation: InboxConversation | None = None
    message: Message | None = None


def _conversation_latest_message(conversation: Conversation) -> ConversationMessage | None:
    if not conversation.messages:
        return None

    return max(
        conversation.messages,
        key=lambda message: (message.created_at, message.id),
    )


def _conversation_latest_at(conversation: Conversation) -> datetime:
    latest_message = _conversation_latest_message(conversation)
    return latest_message.created_at if latest_message else conversation.created_at


def _participant_has_available_copies(
    conversation: Conversation,
    participant: ConversationParticipant,
) -> bool:
    return all(
        any(
            encrypted_copy.recipient_participant_id == participant.id
            for encrypted_copy in message.encrypted_copies
        )
        for message in conversation.messages
    )


def _conversation_has_unread(
    conversation: Conversation,
    participant: ConversationParticipant,
) -> bool:
    latest_message = _conversation_latest_message(conversation)
    last_read_message = participant.last_read_message
    if not latest_message or latest_message.sender_participant_id == participant.id:
        return False
    if last_read_message is not None:
        return (latest_message.created_at, latest_message.id) > (
            last_read_message.created_at,
            last_read_message.id,
        )
    return participant.last_read_at is None or latest_message.created_at > participant.last_read_at


def _inbox_conversation_summary(
    conversation: Conversation,
    user: User,
) -> InboxConversation | None:
    participant = conversation.participant_for_user_id(user.id)
    if participant is None:
        return None

    other_participant_names = []
    for thread_participant in conversation.participants:
        if thread_participant.user_id == user.id:
            continue
        username = thread_participant.user.primary_username
        other_participant_names.append(f"@{username.username}")

    return InboxConversation(
        conversation=conversation,
        other_participant_names=other_participant_names,
        latest_at=_conversation_latest_at(conversation),
        message_count=len(conversation.messages),
        has_unread=_conversation_has_unread(conversation, participant),
        has_available_copy=(
            participant.has_usable_public_key
            and _participant_has_available_copies(conversation, participant)
        ),
    )


def register_inbox_routes(app: Flask) -> None:
    @app.route("/inbox")
    @authentication_required
    def inbox() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:  # silence, mypy
            abort(404)

        user_alias_count = db.session.scalar(
            db.select(db.func.count(Username.id).filter(Username.user_id == user.id))
        )

        status_filter = None
        if status_str := request.args.get("status"):
            try:
                status_filter = MessageStatus.parse_str(status_str)
            except ValueError:
                abort(400)
        type_filter = request.args.get("type")
        if type_filter and type_filter not in VALID_INBOX_TYPE_FILTERS:
            abort(400)

        query = (
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == user.id)
            .filter(Message.conversation_id.is_(None))
            .order_by(Message.created_at.desc())
        )
        if status_filter:
            query = query.filter(Message.status == status_filter)
        messages = list(db.session.scalars(query))

        status_count_results = db.session.execute(
            db.select(Message.status, db.func.count())
            .join(Username)
            .filter(Username.user_id == user.id)
            .filter(Message.conversation_id.is_(None))
            .group_by(Message.status)
        ).all()
        status_counts_map = {x[0]: x[1] for x in status_count_results}
        message_statuses = [(x, status_counts_map.get(x, 0)) for x in MessageStatus]

        conversations = [
            summary
            for conversation in db.session.scalars(Conversation.for_user_id(user.id))
            if (summary := _inbox_conversation_summary(conversation, user)) is not None
        ]
        conversations.sort(key=lambda conversation: conversation.latest_at, reverse=True)
        filtered_conversations = (
            conversations
            if type_filter in (None, "conversations") and status_filter is None
            else []
        )
        filtered_messages = messages if type_filter in (None, "tips") else []
        inbox_items = [
            *[
                InboxItem(
                    kind="conversation",
                    sort_at=conversation.latest_at,
                    conversation=conversation,
                )
                for conversation in filtered_conversations
            ],
            *[
                InboxItem(
                    kind="message",
                    sort_at=message.created_at,
                    message=message,
                )
                for message in filtered_messages
            ],
        ]
        inbox_items.sort(key=lambda item: item.sort_at, reverse=True)
        total_tips = sum(x[1] for x in message_statuses)
        total_conversations = len(conversations)

        return render_template(
            "inbox.html",
            user=user,
            inbox_items=inbox_items,
            status_filter=status_filter,
            type_filter=type_filter,
            total_messages=total_tips,
            total_conversations=total_conversations,
            total_inbox_items=total_tips + total_conversations,
            message_statuses=message_statuses,
            user_has_aliases=user_alias_count > 1,
        )

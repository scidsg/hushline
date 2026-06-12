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


@dataclass(frozen=True)
class InboxConversation:
    conversation: Conversation
    other_participant_names: list[str]
    latest_at: datetime
    message_count: int
    has_unread: bool
    has_available_copy: bool


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
    return bool(
        latest_message
        and latest_message.sender_participant_id != participant.id
        and (
            participant.last_read_at is None or latest_message.created_at > participant.last_read_at
        )
    )


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

        query = (
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == user.id)
            .order_by(Message.created_at.desc())
        )
        if status_filter:
            query = query.filter(Message.status == status_filter)
        messages = list(db.session.scalars(query))

        status_count_results = db.session.execute(
            db.select(Message.status, db.func.count())
            .join(Username)
            .filter(Username.user_id == user.id)
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

        return render_template(
            "inbox.html",
            user=user,
            messages=messages,
            conversations=conversations,
            status_filter=status_filter,
            total_messages=sum(x[1] for x in message_statuses),
            message_statuses=message_statuses,
            user_has_aliases=user_alias_count > 1,
        )

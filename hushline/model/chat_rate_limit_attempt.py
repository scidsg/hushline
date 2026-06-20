from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class ChatRateLimitAttempt(Model):
    __tablename__ = "chat_rate_limit_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_participant_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, nullable=False)

    __table_args__ = (
        Index(
            "idx_chat_rate_limit_attempts_sender_conversation_created",
            "sender_participant_id",
            "conversation_id",
            "created_at",
        ),
        Index(
            "idx_chat_rate_limit_attempts_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "idx_chat_rate_limit_attempts_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index("idx_chat_rate_limit_attempts_created", "created_at"),
    )

    def __init__(
        self,
        *,
        conversation_id: int,
        sender_participant_id: int,
        user_id: int,
        created_at: datetime,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            conversation_id=conversation_id,  # type: ignore[call-arg]
            sender_participant_id=sender_participant_id,  # type: ignore[call-arg]
            user_id=user_id,  # type: ignore[call-arg]
            created_at=created_at,  # type: ignore[call-arg]
            **kwargs,
        )

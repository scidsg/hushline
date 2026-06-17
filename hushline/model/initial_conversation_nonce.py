from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class InitialConversationNonce(Model):
    __tablename__ = "initial_conversation_nonces"
    __table_args__ = (
        UniqueConstraint("nonce_hash"),
        Index(
            "ix_initial_conversation_nonces_sender_recipient_created",
            "sender_user_id",
            "recipient_user_id",
            "created_at",
        ),
        Index("ix_initial_conversation_nonces_consumed_at", "consumed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    nonce_hash: Mapped[str] = mapped_column(db.String(64), nullable=False)
    sender_user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

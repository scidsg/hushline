from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.message import Message
    from hushline.model.user import User
else:
    Model = db.Model


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AdminBroadcast(Model):
    __tablename__ = "admin_broadcasts"
    __table_args__ = (Index("ix_admin_broadcasts_status_created_at", "status", "created_at"),)

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        db.String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        db.String(32),
        nullable=False,
        default=STATUS_IN_PROGRESS,
        server_default=STATUS_IN_PROGRESS,
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        default=_utc_now,
        server_default=text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        default=_utc_now,
        server_default=text("NOW()"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))

    admin_user: Mapped["User | None"] = relationship()
    recipients: Mapped[list["AdminBroadcastRecipient"]] = relationship(
        back_populates="broadcast",
        cascade="all, delete-orphan",
        order_by="AdminBroadcastRecipient.user_id.asc()",
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @property
    def pending_count(self) -> int:
        return sum(
            recipient.status == AdminBroadcastRecipient.STATUS_PENDING
            for recipient in self.recipients
        )

    @property
    def submitted_count(self) -> int:
        return sum(
            recipient.status == AdminBroadcastRecipient.STATUS_SUBMITTED
            for recipient in self.recipients
        )

    @property
    def skipped_count(self) -> int:
        return sum(
            recipient.status == AdminBroadcastRecipient.STATUS_SKIPPED
            for recipient in self.recipients
        )

    def mark_updated(self) -> None:
        self.updated_at = _utc_now()

    def mark_completed_if_done(self) -> None:
        if self.pending_count == 0:
            now = _utc_now()
            self.status = self.STATUS_COMPLETED
            self.updated_at = now
            self.completed_at = self.completed_at or now


class AdminBroadcastRecipient(Model):
    __tablename__ = "admin_broadcast_recipients"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id"),
        UniqueConstraint("message_id"),
        Index(
            "ix_admin_broadcast_recipients_broadcast_status",
            "broadcast_id",
            "status",
        ),
    )

    STATUS_PENDING = "pending"
    STATUS_SUBMITTED = "submitted"
    STATUS_SKIPPED = "skipped"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(
        db.ForeignKey("admin_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        db.String(32),
        nullable=False,
        default=STATUS_PENDING,
        server_default=STATUS_PENDING,
    )
    message_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        default=_utc_now,
        server_default=text("NOW()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        default=_utc_now,
        server_default=text("NOW()"),
        nullable=False,
    )

    broadcast: Mapped["AdminBroadcast"] = relationship(back_populates="recipients")
    user: Mapped["User"] = relationship()
    message: Mapped["Message | None"] = relationship()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def mark_submitted(self, message: "Message") -> None:
        self.status = self.STATUS_SUBMITTED
        self.message = message
        self.failure_reason = None
        self.updated_at = _utc_now()

    def mark_skipped(self, failure_reason: str = "encryption_failed") -> None:
        self.status = self.STATUS_SKIPPED
        self.failure_reason = failure_reason
        self.updated_at = _utc_now()

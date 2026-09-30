from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
    from sqlalchemy import Select

    from hushline.model.chat_key import ChatArchiveEpoch, ChatDevice
    from hushline.model.message import Message
    from hushline.model.user import User
else:
    Model = db.Model


class Conversation(Model):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("minimum_protocol_version >= 0", name="minimum_protocol_version"),
        CheckConstraint("version >= 0", name="version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        db.String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    minimum_protocol_version: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    version: Mapped[int] = mapped_column(
        db.BigInteger, nullable=False, default=0, server_default=text("0")
    )

    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationParticipant.id.asc()",
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.id.asc()",
    )
    initial_message: Mapped["Message | None"] = relationship(
        "Message",
        back_populates="conversation",
        uselist=False,
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @classmethod
    def for_user_id(cls, user_id: int) -> "Select[tuple[Conversation]]":
        return (
            db.select(cls)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user_id)
            .where(ConversationParticipant.deleted_at.is_(None))
        )

    def participant_for_user_id(self, user_id: int) -> "ConversationParticipant | None":
        return next(
            (participant for participant in self.participants if participant.user_id == user_id),
            None,
        )


class ConversationParticipant(Model):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id"),
        Index("ix_conversation_participants_user_id_conversation_id", "user_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    last_read_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    last_read_message_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        index=True,
    )
    last_active_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    has_usable_public_key: Mapped[bool] = mapped_column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(back_populates="conversation_participants")
    sent_messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="sender_participant",
        passive_deletes=True,
        foreign_keys="ConversationMessage.sender_participant_id",
    )
    last_read_message: Mapped["ConversationMessage | None"] = relationship(
        "ConversationMessage",
        foreign_keys=[last_read_message_id],
        post_update=True,
    )
    encrypted_copies: Mapped[list["ConversationMessageCopy"]] = relationship(
        back_populates="recipient_participant",
        passive_deletes=True,
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ConversationMessage(Model):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "conversation_version"),
        CheckConstraint("protocol_version >= 0", name="protocol_version"),
        CheckConstraint(
            "conversation_version IS NULL OR conversation_version > 0",
            name="conversation_version",
        ),
        Index(
            "ix_conversation_messages_conversation_id_created_at",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        db.String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4())
    )
    conversation_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_participant_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    protocol_version: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    conversation_version: Mapped[int | None] = mapped_column(db.BigInteger)
    idempotency_key: Mapped[str | None] = mapped_column(db.String(64), unique=True, index=True)
    request_sha256: Mapped[str | None] = mapped_column(db.String(64))
    manifest: Mapped[dict[str, object] | None] = mapped_column(db.JSON)
    manifest_signature: Mapped[str | None] = mapped_column(db.Text)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender_participant: Mapped["ConversationParticipant"] = relationship(
        back_populates="sent_messages",
        foreign_keys=[sender_participant_id],
    )
    encrypted_copies: Mapped[list["ConversationMessageCopy"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ConversationMessageCopy.id.asc()",
    )
    transport_copies: Mapped[list["ConversationMessageTransportCopy"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ConversationMessageTransportCopy.id.asc()",
    )
    archive_copies: Mapped[list["ConversationMessageArchiveCopy"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ConversationMessageArchiveCopy.id.asc()",
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ConversationMessageCopy(Model):
    __tablename__ = "conversation_message_copies"
    __table_args__ = (
        UniqueConstraint("conversation_message_id", "recipient_participant_id"),
        Index(
            "ix_conversation_message_copies_participant_message",
            "recipient_participant_id",
            "conversation_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    conversation_message_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_participant_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encrypted_payload: Mapped[str] = mapped_column(db.Text, nullable=False)

    message: Mapped["ConversationMessage"] = relationship(back_populates="encrypted_copies")
    recipient_participant: Mapped["ConversationParticipant"] = relationship(
        back_populates="encrypted_copies"
    )


class ConversationMessageTransportCopy(Model):
    __tablename__ = "conversation_message_transport_copies"
    __table_args__ = (
        UniqueConstraint("conversation_message_id", "recipient_device_id"),
        Index(
            "ix_conversation_transport_copies_participant_message",
            "recipient_participant_id",
            "conversation_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    conversation_message_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_participant_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_device_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_version: Mapped[int] = mapped_column(db.BigInteger, nullable=False)
    context: Mapped[dict[str, object]] = mapped_column(db.JSON, nullable=False)
    context_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    ciphertext_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(db.Text, nullable=False)

    message: Mapped["ConversationMessage"] = relationship(back_populates="transport_copies")
    recipient_participant: Mapped["ConversationParticipant"] = relationship()
    recipient_device: Mapped["ChatDevice"] = relationship()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class ConversationMessageArchiveCopy(Model):
    __tablename__ = "conversation_message_archive_copies"
    __table_args__ = (
        UniqueConstraint("conversation_message_id", "recipient_participant_id"),
        Index(
            "ix_conversation_archive_copies_participant_message",
            "recipient_participant_id",
            "conversation_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    conversation_message_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_participant_id: Mapped[int] = mapped_column(
        db.ForeignKey("conversation_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    archive_epoch_id: Mapped[int] = mapped_column(
        db.ForeignKey("chat_archive_epochs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context: Mapped[dict[str, object]] = mapped_column(db.JSON, nullable=False)
    context_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    ciphertext_sha256: Mapped[str] = mapped_column(db.String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(db.Text, nullable=False)

    message: Mapped["ConversationMessage"] = relationship(back_populates="archive_copies")
    recipient_participant: Mapped["ConversationParticipant"] = relationship()
    archive_epoch: Mapped["ChatArchiveEpoch"] = relationship()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

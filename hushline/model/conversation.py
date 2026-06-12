from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
    from sqlalchemy import Select

    from hushline.model.message import Message
    from hushline.model.user import User
else:
    Model = db.Model


class Conversation(Model):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
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

    @classmethod
    def for_user_id(cls, user_id: int) -> "Select[tuple[Conversation]]":
        return (
            db.select(cls)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user_id)
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
    last_active_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
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
    )
    encrypted_copies: Mapped[list["ConversationMessageCopy"]] = relationship(
        back_populates="recipient_participant",
        passive_deletes=True,
    )


class ConversationMessage(Model):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index(
            "ix_conversation_messages_conversation_id_created_at",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
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

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    sender_participant: Mapped["ConversationParticipant"] = relationship(
        back_populates="sent_messages"
    )
    encrypted_copies: Mapped[list["ConversationMessageCopy"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ConversationMessageCopy.id.asc()",
    )


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

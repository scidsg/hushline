from datetime import datetime
from uuid import uuid4
from typing import TYPE_CHECKING

from markupsafe import Markup
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import and_, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import gen_reply_slug
from hushline.db import db
from hushline.model.enums import MessageStatus
from hushline.model.message_status_text import MessageStatusText

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model import FieldValue, Username
else:
    Model = db.Model


class Message(Model):
    __tablename__ = "messages"

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
    username_id: Mapped[int] = mapped_column(db.ForeignKey("usernames.id"), nullable=False)
    username: Mapped["Username"] = relationship(uselist=False)
    reply_slug: Mapped[str] = mapped_column(index=True, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        SQLAlchemyEnum(MessageStatus), default=MessageStatus.PENDING, nullable=False
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    field_values: Mapped[list["FieldValue"]] = relationship(
        "FieldValue", back_populates="message", cascade="all, delete-orphan"
    )

    def __init__(self, username_id: int) -> None:
        super().__init__(
            username_id=username_id,  # type: ignore[call-arg]
            reply_slug=gen_reply_slug(),  # type: ignore[call-arg]
            public_id=str(uuid4()),  # type: ignore[call-arg]
        )

    # using a plain property because the mapper/join was too complicated.
    # a better coder than me should properly configure this in the future.
    @property
    def status_text(self) -> str | Markup:
        # Import here to avoid circular imports
        from hushline.model import User, Username

        if status_text := db.session.scalars(
            db.select(MessageStatusText)
            .join(User, User.id == MessageStatusText.user_id)
            .join(Username, and_(Username.user_id == User.id, Username.id == self.username_id))
            .join(Message, and_(Message.username_id == Username.id, Message.id == self.id))
            .filter(MessageStatusText.status == Message.status)
        ).one_or_none():
            return status_text.markdown
        else:
            return self.status.default_text

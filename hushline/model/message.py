from datetime import datetime
from typing import TYPE_CHECKING

from markupsafe import Markup
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import and_, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import decrypt_field, encrypt_field, gen_reply_slug
from hushline.db import db
from hushline.model.enums import MessageStatus
from hushline.model.message_status_text import MessageStatusText
from hushline.model.user import User
from hushline.model.username import Username

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class Message(Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    _content: Mapped[str] = mapped_column("content", db.Text)  # Encrypted content stored here
    created_at: Mapped[datetime] = mapped_column(server_default=text("NOW()"))
    username_id: Mapped[int] = mapped_column(db.ForeignKey("usernames.id"))
    username: Mapped["Username"] = relationship(uselist=False)
    reply_slug: Mapped[str] = mapped_column(index=True)
    status: Mapped[MessageStatus] = mapped_column(
        SQLAlchemyEnum(MessageStatus), default=MessageStatus.PENDING
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()")
    )

    def __init__(self, content: str, username_id: int) -> None:
        super().__init__(
            content=content,  # type: ignore[call-arg]
            username_id=username_id,  # type: ignore[call-arg]
            reply_slug=gen_reply_slug(),  # type: ignore[call-arg]
        )

    @property
    def content(self) -> str | None:
        return decrypt_field(self._content)

    @content.setter
    def content(self, value: str) -> None:
        val = encrypt_field(value)
        if val is not None:
            self._content = val
        else:
            self._content = ""

    # using a plain property because the mapper/join was too complicated.
    # a better coder than me should properly configure this in the future.
    @property
    def status_text(self) -> str | Markup:
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

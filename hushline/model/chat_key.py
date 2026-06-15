from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


class ChatKey(Model):
    __tablename__ = "chat_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key_version"),
        Index("ix_chat_keys_user_id_disabled_at", "user_id", "disabled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_version: Mapped[int] = mapped_column(nullable=False)
    public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    public_signing_key: Mapped[str | None] = mapped_column(db.Text)
    encrypted_private_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    kdf_algorithm: Mapped[str] = mapped_column(db.String(128), nullable=False)
    kdf_params: Mapped[dict[str, Any]] = mapped_column(db.JSON, nullable=False)
    kdf_salt: Mapped[str] = mapped_column(db.Text, nullable=False)
    wrapping_algorithm: Mapped[str] = mapped_column(db.String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    rotated_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    recovery_state: Mapped[str | None] = mapped_column(db.String(64))

    user: Mapped["User"] = relationship(back_populates="chat_keys")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @classmethod
    def active_for_user_id(cls, user_id: int) -> "ChatKey | None":
        return db.session.scalars(
            db.select(cls)
            .where(cls.user_id == user_id, cls.disabled_at.is_(None))
            .order_by(cls.key_version.desc())
            .limit(1)
        ).one_or_none()

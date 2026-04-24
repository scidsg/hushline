import secrets
from datetime import datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


def hash_password_reset_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class PasswordResetToken(Model):
    __tablename__ = "password_reset_tokens"

    TOKEN_HASH_LENGTH = 64

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        db.String(TOKEN_HASH_LENGTH),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None]

    user: Mapped["User"] = relationship(back_populates="password_reset_tokens")

    __table_args__ = (
        Index("idx_password_reset_tokens_user_used_expires", "user_id", "used_at", "expires_at"),
    )

    @staticmethod
    def hash_password_reset_token(token: str) -> str:
        return hash_password_reset_token(token)

    def __init__(self, user_id: int, token_hash: str, expires_at: datetime, **kwargs: Any) -> None:
        super().__init__(
            user_id=user_id,  # type: ignore[call-arg]
            token_hash=token_hash,  # type: ignore[call-arg]
            expires_at=expires_at,  # type: ignore[call-arg]
            **kwargs,
        )

    @classmethod
    def create_for_user(cls, user_id: int, *, ttl: timedelta) -> tuple["PasswordResetToken", str]:
        raw_token = secrets.token_urlsafe(32)
        row = cls(
            user_id=user_id,
            token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now() + ttl,
        )
        return row, raw_token

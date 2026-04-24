from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class PasswordResetAttempt(Model):
    __tablename__ = "password_reset_attempts"

    DIGEST_LENGTH = 64

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    identifier_hash: Mapped[str] = mapped_column(db.String(DIGEST_LENGTH), nullable=False)
    ip_hash: Mapped[str] = mapped_column(db.String(DIGEST_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now, nullable=False)

    __table_args__ = (
        Index("idx_password_reset_attempts_identifier_created", "identifier_hash", "created_at"),
        Index("idx_password_reset_attempts_ip_created", "ip_hash", "created_at"),
    )

    def __init__(self, identifier_hash: str, ip_hash: str, **kwargs: Any) -> None:
        super().__init__(
            identifier_hash=identifier_hash,  # type: ignore[call-arg]
            ip_hash=ip_hash,  # type: ignore[call-arg]
            **kwargs,
        )

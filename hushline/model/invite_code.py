import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class InviteCode(Model):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    code: Mapped[str] = mapped_column(db.String(255), unique=True)
    expiration_date: Mapped[datetime]

    def __init__(self) -> None:
        super().__init__(
            code=secrets.token_urlsafe(16),  # type: ignore[call-arg]
            expiration_date=datetime.now(timezone.utc) + timedelta(days=365),  # type: ignore[call-arg]
        )

    def __repr__(self) -> str:
        return f"<InviteCode {self.code}>"

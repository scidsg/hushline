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

    CODE_MIN_LENGTH = 6
    CODE_MAX_LENGTH = 25

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    code: Mapped[str] = mapped_column(db.String(CODE_MAX_LENGTH), unique=True)
    expiration_date: Mapped[datetime]

    @staticmethod
    def _generate_code() -> str:
        # Avoid leading "-" so CLI arguments cannot be misparsed as options.
        code = secrets.token_urlsafe(16)
        while code.startswith("-"):
            code = secrets.token_urlsafe(16)
        return code

    def __init__(self) -> None:
        super().__init__(
            code=self._generate_code(),  # type: ignore[call-arg]
            expiration_date=datetime.now(timezone.utc) + timedelta(days=365),  # type: ignore[call-arg]
        )

    def __repr__(self) -> str:
        return f"<InviteCode {self.code}>"

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


class AuthenticationLog(Model):
    __tablename__ = "authentication_logs"

    OTP_CODE_LENGTH = 6

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"))
    user: Mapped["User"] = relationship(backref=db.backref("authentication_logs", lazy=True))
    successful: Mapped[bool]
    timestamp: Mapped[datetime] = mapped_column(default=datetime.now)
    otp_code: Mapped[Optional[str]] = mapped_column(db.String(OTP_CODE_LENGTH))
    timecode: Mapped[Optional[int]]

    __table_args__ = (
        Index(
            "idx_authentication_logs_user_id_timestamp_successful",
            "user_id",
            "timestamp",
            "successful",
        ),
    )

    # Open question: should we store the IP address and user agent?
    # It's useful for auditing, but it's identifable
    # ip_address = db.Column(db.String(45), nullable=False)
    # user_agent = db.Column(db.String(255), nullable=False)

    def __init__(
        self,
        user_id: int,
        successful: bool,
        otp_code: str | None = None,
        timecode: int | None = None,
    ) -> None:
        super().__init__(
            user_id=user_id,  # type: ignore[call-arg]
            successful=successful,  # type: ignore[call-arg]
            otp_code=otp_code,  # type: ignore[call-arg]
            timecode=timecode,  # type: ignore[call-arg]
        )

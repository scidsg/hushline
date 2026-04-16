from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import decrypt_field, encrypt_field
from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.user import User
else:
    Model = db.Model


class NotificationRecipient(Model):
    __tablename__ = "notification_recipients"

    EMAIL_MAX_LENGTH = 255

    id: Mapped[int] = mapped_column(primary_key=True, nullable=False, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    position: Mapped[int] = mapped_column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    _email: Mapped[Optional[str]] = mapped_column("email", db.String(EMAIL_MAX_LENGTH))
    _pgp_key: Mapped[Optional[str]] = mapped_column("pgp_key", db.Text)

    user: Mapped["User"] = relationship(back_populates="notification_recipients")

    def __init__(
        self,
        user: "User | None" = None,
        enabled: bool = True,
        position: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            enabled=enabled,  # type: ignore[call-arg]
            position=position,  # type: ignore[call-arg]
            **kwargs,
        )
        if user is not None:
            self.user = user

    @property
    def email(self) -> str | None:
        return decrypt_field(self._email)

    @email.setter
    def email(self, value: str | None) -> None:
        self._email = encrypt_field(value) if value is not None else None

    @property
    def pgp_key(self) -> str | None:
        return decrypt_field(self._pgp_key)

    @pgp_key.setter
    def pgp_key(self, value: str | None) -> None:
        self._pgp_key = encrypt_field(value) if value is not None else None

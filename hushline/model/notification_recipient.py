from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.config import EncryptedFieldWriteFormat
from hushline.crypto import (
    ENCRYPTED_FIELD_CONTRACT_BY_ID,
    decrypt_field,
    encrypt_field,
    encrypted_field_write_format,
    is_encrypted_field_aead_envelope,
)
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
    _email: Mapped[Optional[str]] = mapped_column("email", db.Text)
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

    def _encrypted_field_aad_values(self) -> dict[str, int]:
        if (
            self.id is None
            and encrypted_field_write_format() == EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
        ):
            db.session.add(self)
            db.session.flush()
        if self.id is None or self.user_id is None:
            raise ValueError(
                "Notification recipient encrypted-field AAD requires persisted row ids"
            )
        return {"notification_recipient_id": self.id, "user_id": self.user_id}

    def _encrypt_encrypted_field(self, contract_id: str, value: str | None) -> str | None:
        if encrypted_field_write_format() != EncryptedFieldWriteFormat.ENVELOPE_AES_GCM:
            return encrypt_field(value)

        contract = ENCRYPTED_FIELD_CONTRACT_BY_ID[contract_id]
        return encrypt_field(
            value,
            contract=contract,
            aad_values=self._encrypted_field_aad_values(),
        )

    def _decrypt_encrypted_field(self, contract_id: str, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_encrypted_field_aead_envelope(value):
            return decrypt_field(value)

        contract = ENCRYPTED_FIELD_CONTRACT_BY_ID[contract_id]
        return decrypt_field(
            value,
            contract=contract,
            aad_values=self._encrypted_field_aad_values(),
        )

    @property
    def email(self) -> str | None:
        return self._decrypt_encrypted_field("NotificationRecipient.email", self._email)

    @email.setter
    def email(self, value: str | None) -> None:
        self._email = (
            self._encrypt_encrypted_field("NotificationRecipient.email", value)
            if value is not None
            else None
        )

    @property
    def pgp_key(self) -> str | None:
        return self._decrypt_encrypted_field("NotificationRecipient.pgp_key", self._pgp_key)

    @pgp_key.setter
    def pgp_key(self, value: str | None) -> None:
        self._pgp_key = (
            self._encrypt_encrypted_field("NotificationRecipient.pgp_key", value)
            if value is not None
            else None
        )

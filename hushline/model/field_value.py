from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import padding
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.model import FieldDefinition, Message

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class FieldValue(Model):
    __tablename__ = "field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(db.ForeignKey("field_definitions.id"))
    field_definition: Mapped["FieldDefinition"] = relationship(uselist=False)
    message_id: Mapped[int] = mapped_column(db.ForeignKey("messages.id"))
    message: Mapped["Message"] = relationship(uselist=False)
    value: Mapped[str] = mapped_column(db.String(1024))
    encrypted: Mapped[bool] = mapped_column(default=False)

    # Block size for padding
    BLOCK_SIZE = 1024

    def __init__(
        self,
        field_definition: "FieldDefinition",
        message: "Message",
        value: str,
        encrypted: bool,
    ) -> None:
        self.field_definition = field_definition
        self.message = message
        self.encrypted = encrypted
        self.set_value(value)

    def set_value(self, value: str) -> None:
        if self.encrypted:
            # TODO: consider how this padding will work, and how to go about
            # displaying it when decrypted...

            # Pad the value to the block size, to avoid leaking the length of the original data
            padder = padding.PKCS7(self.BLOCK_SIZE).padder()
            padded_data = padder.update(value.encode()) + padder.finalize()

            # Encrypt the value
            pgp_key = self.message.username.user.pgp_key
            if not pgp_key:
                raise ValueError("User does not have a PGP key")
            encrypted_value = encrypt_message(padded_data.decode(), pgp_key)
            if encrypted_value:
                self.value = encrypted_value
        else:
            self.value = value

    def __repr__(self) -> str:
        return f"<FieldValue {self.field_definition.label}>"

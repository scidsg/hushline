import json
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import decrypt_field, encrypt_field, encrypt_message
from hushline.db import db
from hushline.model import FieldDefinition, Message

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class PaddedFieldValue:
    """
    To hide what field is being encrypted, we need to pad the value to a fixed block size.
    This class is used to create a padded version of the field, return as a JSON string in
    format: {"v": "value", "p": "padding"}
    """

    def __init__(self, value: str) -> None:
        self.value = value
        self.padding = ""

    def json(self) -> str:
        return json.dumps({"v": self.value, "p": self.padding})

    def pad(self) -> str:
        BLOCK_SIZE = 1024

        # Add padding
        self.padding = ""
        current_len = len(self.json())
        padding_len = BLOCK_SIZE - (current_len % BLOCK_SIZE)
        self.padding = " " * padding_len

        # Return the padded value
        return json.dumps(self.__dict__)


class FieldValue(Model):
    __tablename__ = "field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(db.ForeignKey("field_definitions.id"))
    field_definition: Mapped["FieldDefinition"] = relationship(uselist=False)
    message_id: Mapped[int] = mapped_column(db.ForeignKey("messages.id"))
    message: Mapped["Message"] = relationship(uselist=False)
    _value: Mapped[str] = mapped_column(db.String(1024))
    encrypted: Mapped[bool] = mapped_column(default=False)

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
        # set the value AFTER setting the encrypted flag
        self.value = value

    @property
    def value(self) -> str | None:
        """
        This value is either a string with the actual value, PGP-encrypted data. If it's
        PGP-encrypted, the plaintext is a JSON string in format: {"v": "value", "p": "padding"}.
        """
        return decrypt_field(self._value)

    @value.setter
    def value(self, value: str) -> None:
        if self.encrypted:
            # Encrypt with PGP

            # Pad the value to hide the length of the plaintext
            padded_value = PaddedFieldValue(value).pad()

            # Encrypt the padded value
            pgp_key = self.message.username.user.pgp_key
            if not pgp_key:
                raise ValueError("User does not have a PGP key")
            encrypted_value = encrypt_message(padded_value, pgp_key)
            if encrypted_value:
                self.value = encrypted_value
            else:
                raise ValueError("Failed to encrypt value")
        else:
            # Do not encrypt with PGP, and instead only encrypt with db key
            val_to_save = value

        # Encrypt the field
        val = encrypt_field(val_to_save)
        if val is not None:
            self._value = val
        else:
            self._value = ""

    def __repr__(self) -> str:
        return f"<FieldValue {self.field_definition.label}>"

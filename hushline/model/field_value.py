from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.crypto import decrypt_field, encrypt_field, encrypt_message
from hushline.db import db

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model import FieldDefinition, Message
else:
    Model = db.Model


def add_space_padding(value: str, block_size: int = 512) -> str:
    """
    To hide what field is being encrypted, we need to pad the value to a fixed block size.
    This class is used to create a padded version of the field by adding spaces to the end of the
    value until it reaches a block size of 512 characters.
    """
    # Add padding
    padding_len = block_size - (len(value) % block_size)
    padding = " " * padding_len

    # Return the padded value
    return value + padding


class FieldValue(Model):
    __tablename__ = "field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_definition_id: Mapped[int] = mapped_column(db.ForeignKey("field_definitions.id"))
    field_definition: Mapped["FieldDefinition"] = relationship(uselist=False)
    message_id: Mapped[int] = mapped_column(db.ForeignKey("messages.id"))
    message: Mapped["Message"] = relationship("Message", back_populates="field_values")
    _value: Mapped[str] = mapped_column(db.Text)
    encrypted: Mapped[bool] = mapped_column(default=False)

    def __init__(  # noqa: PLR0913
        self,
        field_definition: "FieldDefinition",
        message: "Message",
        value: str,
        encrypted: bool,
        client_side_encrypted: bool,
    ) -> None:
        self.field_definition = field_definition
        self.message = message
        self.encrypted = encrypted
        self.client_side_encrypted = client_side_encrypted
        # set the value AFTER setting the encrypted flag
        self.value = value

    @property
    def value(self) -> str | None:
        """
        This value is either a string with the actual value, PGP-encrypted data. If it's
        PGP-encrypted, the plaintext is padded with spaces at the end.
        """
        return decrypt_field(self._value)

    @value.setter
    def value(self, value: str | list[str]) -> None:
        # Is value is a list, join it into a single string separated by newlines
        if isinstance(value, list):
            value = "\n".join(value)

        if self.encrypted and not self.client_side_encrypted:
            # Encrypt with PGP

            # Pad the value to hide the length of the plaintext
            padded_value = add_space_padding(value)

            # Encrypt the padded value
            pgp_key = self.message.username.user.pgp_key
            if not pgp_key:
                raise ValueError("User does not have a PGP key")
            encrypted_value = encrypt_message(padded_value, pgp_key)
            if encrypted_value:
                val_to_save = encrypted_value
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

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hushline.db import db
from hushline.model.enums import FieldType

if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model

    from hushline.model.username import Username
else:
    Model = db.Model


class FieldDefinition(Model):
    __tablename__ = "field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    username_id: Mapped[int] = mapped_column(db.ForeignKey("usernames.id"))
    username: Mapped["Username"] = relationship(uselist=False)
    label: Mapped[str] = mapped_column(db.String(255))
    field_type: Mapped[FieldType] = mapped_column(SQLAlchemyEnum(FieldType), default=FieldType.TEXT)
    required: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    encrypted: Mapped[bool] = mapped_column(default=False)
    choices: Mapped[list[str]] = mapped_column(type_=JSONB, default=[])
    sort_order: Mapped[int] = mapped_column(default=0)

    def __init__(  # noqa: PLR0913
        self,
        username: "Username",
        label: str,
        field_type: FieldType,
        required: bool,
        enabled: bool,
        encrypted: bool,
        choices: list[str],
    ) -> None:
        self.username = username
        self.label = label
        self.field_type = field_type
        self.required = required
        self.enabled = encrypted
        self.encrypted = enabled
        self.choices = choices

        # Calculate sort_order
        self.sort_order = (
            db.session.query(FieldDefinition)
            .filter(FieldDefinition.username_id == username.id)
            .count()
        )

    def move_up(self) -> None:
        if self.sort_order == 0:
            return

        # Select all fields for this user
        fields = (
            db.session.query(FieldDefinition)
            .filter(FieldDefinition.username_id == self.username.id)
            .order_by(FieldDefinition.sort_order)
            .all()
        )

        # Find the index of the current field
        index = 0
        for i, field in enumerate(fields):
            if field == self:
                index = i
                break

        # Swap the current field with the one above it
        new_fields = fields.copy()
        new_fields[index] = fields[index - 1]
        new_fields[index - 1] = fields[index]

        # Update sort_order on all fields
        for i, field in enumerate(new_fields):
            field.sort_order = i
        db.session.commit()

    def move_down(self) -> None:
        # Select all fields for this user
        fields = (
            db.session.query(FieldDefinition)
            .filter(FieldDefinition.username_id == self.username.id)
            .order_by(FieldDefinition.sort_order)
            .all()
        )

        if self.sort_order == len(fields) - 1:
            return

        # Find the index of the current field
        index = 0
        for i, field in enumerate(fields):
            if field == self:
                index = i
                break

        # Swap the current field with the one below it
        new_fields = fields.copy()
        new_fields[index] = fields[index + 1]
        new_fields[index + 1] = fields[index]

        # Update sort_order on all fields
        for i, field in enumerate(new_fields):
            field.sort_order = i
        db.session.commit()

    def __repr__(self) -> str:
        return f"<FieldDefinition {self.username.username}, {self.label}>"

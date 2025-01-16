from typing import List

import pytest

from hushline.db import db
from hushline.model import FieldDefinition, FieldType, User, Username


@pytest.fixture()
def username() -> Username:
    user = User(password="Test-testtesttesttest-1")  # noqa: S106
    username = Username(user_id=user.id, _username="testuser", is_primary=True)
    db.session.add(user)
    db.session.add(username)
    db.session.commit()
    return username


def test_add_fields_and_move_up(username: Username) -> None:
    # Add 5 fields
    fields: List[FieldDefinition] = []
    for label in ["A", "B", "C", "D", "E"]:
        field = FieldDefinition(
            username=username,
            label=label,
            field_type=FieldType.TEXT,
            required=False,
            enabled=True,
            encrypted=False,
            choices=[],
        )
        db.session.add(field)
        fields.append(field)
    db.session.commit()

    # Verify the order
    ordered_fields = db.session.scalars(
        db.select(FieldDefinition).order_by(FieldDefinition.sort_order)
    ).all()
    assert [field.label for field in ordered_fields] == ["A", "B", "C", "D", "E"]

    # Move field "D" up
    ordered_fields[3].move_up()

    # Verify the order
    ordered_fields = db.session.scalars(
        db.select(FieldDefinition).order_by(FieldDefinition.sort_order)
    ).all()
    assert [field.label for field in ordered_fields] == ["A", "B", "D", "C", "E"]


def test_add_fields_and_move_down(username: Username) -> None:
    # Add 5 fields
    fields: List[FieldDefinition] = []
    for label in ["A", "B", "C", "D", "E"]:
        field = FieldDefinition(
            username=username,
            label=label,
            field_type=FieldType.TEXT,
            required=False,
            enabled=True,
            encrypted=False,
            choices=[],
        )
        db.session.add(field)
        fields.append(field)
    db.session.commit()

    # Verify the order
    ordered_fields = db.session.scalars(
        db.select(FieldDefinition).order_by(FieldDefinition.sort_order)
    ).all()
    assert [field.label for field in ordered_fields] == ["A", "B", "C", "D", "E"]

    # Move field "B" down
    ordered_fields[1].move_down()

    # Verify the order
    ordered_fields = db.session.scalars(
        db.select(FieldDefinition).order_by(FieldDefinition.sort_order)
    ).all()
    assert [field.label for field in ordered_fields] == ["A", "C", "B", "D", "E"]

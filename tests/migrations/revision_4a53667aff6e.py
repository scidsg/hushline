from dataclasses import dataclass
from typing import Dict, List

from hushline.db import db

from ..helpers import (  # type: ignore[misc]
    format_param_dict,
    random_string,
)


@dataclass(frozen=True)
class OldMessage:
    id: int
    username_id: int
    content: str


@dataclass(frozen=True)
class OldUsername:
    id: int


@dataclass(frozen=True)
class NewFieldDefinition:
    id: int
    username_id: int
    label: str


@dataclass(frozen=True)
class NewFieldValue:
    id: int
    field_definition_id: int
    message_id: int
    _value: str


@dataclass(frozen=True)
class NewMessage:
    id: int
    username_id: int


@dataclass(frozen=True)
class NewUsername:
    id: int


class UpgradeTester:
    def __init__(self) -> None:
        self.old_usernames: List[OldUsername] = []
        self.old_messages: List[OldMessage] = []

    def load_data(self) -> None:
        for _ in range(10):
            user_params = {
                "is_admin": False,
                "password_hash": random_string(10),
                "smtp_encryption": "StartTLS",
            }
            columns, param_args = format_param_dict(user_params)
            result = db.session.execute(
                db.text(f"INSERT INTO users ({columns}) VALUES ({param_args}) RETURNING id"),
                user_params,
            )
            user_id = result.fetchone()[0]

            username_params = {
                "user_id": user_id,
                "username": random_string(10),
                "is_primary": True,
                "is_verified": False,
                "show_in_directory": False,
            }
            columns, param_args = format_param_dict(username_params)
            result = db.session.execute(
                db.text(f"INSERT INTO usernames ({columns}) VALUES ({param_args}) RETURNING id"),
                username_params,
            )
            username_id = result.fetchone()[0]

            self.old_usernames.append(OldUsername(id=username_id))

            for _ in range(5):
                msg_params = {
                    "username_id": username_id,
                    "content": random_string(20),
                }
                columns, param_args = format_param_dict(msg_params)
                result = db.session.execute(
                    db.text(f"INSERT INTO messages ({columns}) VALUES ({param_args}) RETURNING id"),
                    msg_params,
                )
                message_id = result.fetchone()[0]
                self.old_messages.append(
                    OldMessage(
                        id=message_id, username_id=username_id, content=msg_params["content"]
                    )
                )

        db.session.commit()

    def check_upgrade(self) -> None:
        new_field_definitions: Dict[int, NewFieldDefinition] = {}
        new_field_values: List[NewFieldValue] = []

        result = db.session.execute(db.text("SELECT * FROM field_definitions"))
        for row in result:
            fd = NewFieldDefinition(id=row.id, username_id=row.username_id, label=row.label)
            new_field_definitions[fd.id] = fd

        result = db.session.execute(db.text("SELECT * FROM field_values"))
        for row in result:
            fv = NewFieldValue(
                id=row.id,
                field_definition_id=row.field_definition_id,
                message_id=row.message_id,
                _value=row._value,
            )
            new_field_values.append(fv)

        assert len(new_field_definitions) == len(self.old_usernames) * 2
        assert len(new_field_values) == len(self.old_messages)

        for old_message in self.old_messages:
            message_field_definitions = [
                fd for fd in new_field_definitions.values() if fd.label == "Message"
            ]
            assert len(message_field_definitions) == len(self.old_usernames)

            for fd in message_field_definitions:
                field_value = next(fv for fv in new_field_values if fv.message_id == old_message.id)
                assert field_value._value == old_message.content


class DowngradeTester:
    """
    Downgrade is not implemented.
    """
    def load_data(self) -> None:
        pass

    def check_downgrade(self) -> None:
        pass

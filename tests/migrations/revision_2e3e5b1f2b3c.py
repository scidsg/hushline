from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.user_id = 1
        self.username_id = 1
        self.field_definition_id = 1

    def load_data(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, false, '$scrypt$')
            """
            ),
            {"id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames (id, user_id, username, is_primary, is_verified, show_in_directory)
            VALUES (:id, :user_id, 'testuser', true, false, false)
            """
            ),
            {"id": self.username_id, "user_id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO field_definitions (
                id, username_id, label, field_type, required, enabled, encrypted, choices, sort_order
            )
            VALUES (:id, :username_id, 'Field', NULL, NULL, NULL, NULL, '[]', 0)
            """
            ),
            {"id": self.field_definition_id, "username_id": self.username_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO field_values (id, field_definition_id, message_id, _value, encrypted)
            VALUES (1, :field_definition_id, NULL, 'value', false)
            """
            ),
            {"field_definition_id": self.field_definition_id},
        )
        db.session.commit()

    def check_upgrade(self) -> None:
        row = db.session.execute(
            text(
                """
            SELECT field_type, required, enabled, encrypted
            FROM field_definitions
            WHERE id = :id
            """
            ),
            {"id": self.field_definition_id},
        ).one()

        assert row.field_type == "TEXT"
        assert row.required is False
        assert row.enabled is True
        assert row.encrypted is False


class DowngradeTester:
    def __init__(self) -> None:
        self.user_id = 1
        self.username_id = 1
        self.field_definition_id = 1

    def load_data(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, false, '$scrypt$')
            """
            ),
            {"id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames (id, user_id, username, is_primary, is_verified, show_in_directory)
            VALUES (:id, :user_id, 'testuser', true, false, false)
            """
            ),
            {"id": self.username_id, "user_id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO field_definitions (
                id, username_id, label, field_type, required, enabled, encrypted, choices, sort_order
            )
            VALUES (:id, :username_id, 'Field', 'TEXT', false, true, false, '[]', 0)
            """
            ),
            {"id": self.field_definition_id, "username_id": self.username_id},
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM field_definitions WHERE id = :id"),
                {"id": self.field_definition_id},
            )
            == 1
        )

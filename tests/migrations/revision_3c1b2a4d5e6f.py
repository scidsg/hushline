from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.user_id = 1
        self.username_id = 1

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
            INSERT INTO usernames (
                id,
                user_id,
                username,
                is_primary,
                is_verified,
                show_in_directory
            )
            VALUES (:id, :user_id, 'Admin', true, false, false)
            """
            ),
            {"id": self.username_id, "user_id": self.user_id},
        )
        db.session.commit()

    def check_upgrade(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, false, '$scrypt$')
            """
            ),
            {"id": 2},
        )
        db.session.commit()

        try:
            db.session.execute(
                text(
                    """
                INSERT INTO usernames (
                    id,
                    user_id,
                    username,
                    is_primary,
                    is_verified,
                    show_in_directory
                )
                VALUES (:id, :user_id, 'admin', true, false, false)
                """
                ),
                {"id": 2, "user_id": 2},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("Expected case-insensitive username index to block duplicate.")


class DowngradeTester:
    def __init__(self) -> None:
        self.user_id = 1
        self.username_id = 1

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
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, false, '$scrypt$')
            """
            ),
            {"id": 2},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames (
                id,
                user_id,
                username,
                is_primary,
                is_verified,
                show_in_directory
            )
            VALUES (:id, :user_id, 'Admin', true, false, false)
            """
            ),
            {"id": self.username_id, "user_id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames (
                id,
                user_id,
                username,
                is_primary,
                is_verified,
                show_in_directory
            )
            VALUES (:id, :user_id, 'Other', true, false, false)
            """
            ),
            {"id": 2, "user_id": 2},
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, false, '$scrypt$')
            """
            ),
            {"id": 3},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames (
                id,
                user_id,
                username,
                is_primary,
                is_verified,
                show_in_directory
            )
            VALUES (:id, :user_id, 'admin', true, false, false)
            """
            ),
            {"id": 3, "user_id": 3},
        )
        db.session.commit()

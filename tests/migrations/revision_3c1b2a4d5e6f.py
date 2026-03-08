from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.user_id = 1

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
                    user_id, username, is_primary, is_verified, show_in_directory
                )
                VALUES (:user_id, 'CaseUser', true, false, false)
                """
            ),
            {"user_id": self.user_id},
        )
        db.session.commit()

    def check_upgrade(self) -> None:
        try:
            with db.session.begin():
                db.session.execute(
                    text(
                        """
                        INSERT INTO usernames (
                            user_id,
                            username,
                            is_primary,
                            is_verified,
                            show_in_directory
                        )
                        VALUES (:user_id, 'caseuser', false, false, false)
                        """
                    ),
                    {"user_id": self.user_id},
                )
        except IntegrityError:
            db.session.rollback()
            return

        raise AssertionError("Expected case-insensitive duplicate username to violate unique index")


class DowngradeTester:
    def __init__(self) -> None:
        self.user_id = 1

    def load_data(self) -> None:
        db.session.execute(
            text(
                """
                INSERT INTO users (id, is_admin, password_hash, session_id)
                VALUES (:id, false, '$scrypt$', :session_id)
                """
            ),
            {"id": self.user_id, "session_id": f"session-{self.user_id}"},
        )
        db.session.execute(
            text(
                """
                INSERT INTO usernames (
                    user_id, username, is_primary, is_verified, show_in_directory
                )
                VALUES (:user_id, 'CaseUser', true, false, false)
                """
            ),
            {"user_id": self.user_id},
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        db.session.execute(
            text(
                """
                INSERT INTO usernames (
                    user_id, username, is_primary, is_verified, show_in_directory
                )
                VALUES (:user_id, 'caseuser', false, false, false)
                """
            ),
            {"user_id": self.user_id},
        )
        db.session.commit()

        assert (
            db.session.scalar(
                text("SELECT count(*) FROM usernames WHERE lower(username) = lower('caseuser')")
            )
            == 2
        )

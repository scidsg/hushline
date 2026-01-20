from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.user_id = 1

    def load_data(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, true, '$scrypt$')
            """
            ),
            {"id": self.user_id},
        )
        db.session.commit()

    def check_upgrade(self) -> None:
        assert (
            db.session.scalar(
                text("SELECT onboarding_complete FROM users WHERE id = :id"),
                {"id": self.user_id},
            )
            is True
        )


class DowngradeTester:
    def __init__(self) -> None:
        self.user_id = 1

    def load_data(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash, onboarding_complete)
            VALUES (:id, true, '$scrypt$', true)
            """
            ),
            {"id": self.user_id},
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM users WHERE id = :id"),
                {"id": self.user_id},
            )
            == 1
        )

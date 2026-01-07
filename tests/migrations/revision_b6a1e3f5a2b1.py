from uuid import uuid4

from sqlalchemy import text

from hushline.db import db


class LoadUser:
    def __init__(self) -> None:
        self.user_id = 1
        self.username_id = 1

    def load_user(self) -> None:
        db.session.execute(
            text(
                """
            INSERT INTO users (id, is_admin, password_hash)
            VALUES (:id, true, '$scrypt$')
            """
            ),
            {"id": self.user_id},
        )
        db.session.execute(
            text(
                """
            INSERT INTO usernames
            (id, user_id, username, is_primary, is_verified, show_in_directory)
            VALUES (:id, :user_id, :username, true, true, true)
            """
            ),
            {
                "id": self.username_id,
                "user_id": self.user_id,
                "username": f"user__{self.username_id}",
            },
        )
        db.session.commit()


class UpgradeTester(LoadUser):
    def __init__(self) -> None:
        super().__init__()
        self.message_count = 5

    def load_data(self) -> None:
        self.load_user()

        for _ in range(self.message_count):
            db.session.execute(
                text(
                    """
                INSERT INTO messages
                (username_id, created_at, reply_slug, status, status_changed_at)
                VALUES (:username_id, NOW(), :reply_slug, 'PENDING', NOW())
                """
                ),
                {
                    "username_id": self.username_id,
                    "reply_slug": str(uuid4()),
                },
            )
            db.session.commit()

    def check_upgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM messages")) == self.message_count
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM messages WHERE public_id IS NULL")
            )
            == 0
        )


class DowngradeTester(LoadUser):
    def __init__(self) -> None:
        super().__init__()
        self.message_count = 3

    def load_data(self) -> None:
        self.load_user()

        for _ in range(self.message_count):
            db.session.execute(
                text(
                    """
                INSERT INTO messages
                (username_id, created_at, reply_slug, status, status_changed_at, public_id)
                VALUES (:username_id, NOW(), :reply_slug, 'PENDING', NOW(), :public_id)
                """
                ),
                {
                    "username_id": self.username_id,
                    "reply_slug": str(uuid4()),
                    "public_id": str(uuid4()),
                },
            )
            db.session.commit()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM messages")) == self.message_count

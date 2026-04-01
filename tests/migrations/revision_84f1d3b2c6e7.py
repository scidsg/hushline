from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def __init__(self) -> None:
        self.user_count = 5

    def load_data(self) -> None:
        for user_id in range(1, self.user_count + 1):
            db.session.execute(
                text(
                    """
                INSERT INTO users (id, is_admin, password_hash, session_id)
                VALUES (:id, false, '$scrypt$', :session_id)
                """
                ),
                {"id": user_id, "session_id": f"session-{user_id}"},
            )
        db.session.commit()

    def check_upgrade(self) -> None:
        rows = db.session.execute(
            text(
                """
                SELECT id, is_suspended
                FROM users
                ORDER BY id ASC
                """
            )
        ).all()
        assert len(rows) == self.user_count
        assert all(is_suspended is False for _, is_suspended in rows)


class DowngradeTester:
    def __init__(self) -> None:
        self.user_count = 5

    def load_data(self) -> None:
        for user_id in range(1, self.user_count + 1):
            db.session.execute(
                text(
                    """
                INSERT INTO users (
                    id,
                    is_admin,
                    is_cautious,
                    is_suspended,
                    password_hash,
                    session_id
                )
                VALUES (:id, false, false, :is_suspended, '$scrypt$', :session_id)
                """
                ),
                {
                    "id": user_id,
                    "is_suspended": user_id % 2 == 0,
                    "session_id": f"session-{user_id}",
                },
            )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM users")) == self.user_count
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'is_suspended'
                    """
                )
            )
            == 0
        )

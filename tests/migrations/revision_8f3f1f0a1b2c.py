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
            text("SELECT id, account_category FROM users ORDER BY id ASC")
        ).all()
        assert len(rows) == self.user_count
        assert all(account_category is None for _, account_category in rows)


class DowngradeTester:
    def __init__(self) -> None:
        self.user_count = 5

    def load_data(self) -> None:
        for user_id in range(1, self.user_count + 1):
            db.session.execute(
                text(
                    """
                INSERT INTO users (id, is_admin, password_hash, session_id, account_category)
                VALUES (:id, false, '$scrypt$', :session_id, :account_category)
                """
                ),
                {
                    "id": user_id,
                    "session_id": f"session-{user_id}",
                    "account_category": "nonprofit",
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
                  AND column_name = 'account_category'
                """
                )
            )
            == 0
        )

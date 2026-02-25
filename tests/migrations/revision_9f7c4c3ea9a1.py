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
                INSERT INTO users (id, is_admin, password_hash)
                VALUES (:id, false, '$scrypt$')
                """
                ),
                {"id": user_id},
            )
        db.session.commit()

    def check_upgrade(self) -> None:
        session_ids = [
            row[0]
            for row in db.session.execute(
                text("SELECT session_id FROM users ORDER BY id ASC")
            ).all()
        ]
        assert len(session_ids) == self.user_count
        assert all(session_ids)
        assert len(set(session_ids)) == self.user_count


class DowngradeTester:
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
                  AND column_name = 'session_id'
                """
                )
            )
            == 0
        )

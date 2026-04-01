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
                SELECT id, country, city, subdivision
                FROM users
                ORDER BY id ASC
                """
            )
        ).all()
        assert len(rows) == self.user_count
        assert all(
            country is None and city is None and subdivision is None
            for _, country, city, subdivision in rows
        )


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
                    password_hash,
                    session_id,
                    account_category,
                    country,
                    city,
                    subdivision
                )
                VALUES (
                    :id,
                    false,
                    '$scrypt$',
                    :session_id,
                    :account_category,
                    :country,
                    :city,
                    :subdivision
                )
                """
                ),
                {
                    "id": user_id,
                    "session_id": f"session-{user_id}",
                    "account_category": "nonprofit",
                    "country": "United States",
                    "city": "Chicago",
                    "subdivision": "Illinois",
                },
            )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM users")) == self.user_count
        for column_name in ("country", "city", "subdivision"):
            assert (
                db.session.scalar(
                    text(
                        """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = :column_name
                    """
                    ),
                    {"column_name": column_name},
                )
                == 0
            )

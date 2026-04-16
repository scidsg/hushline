from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def load_data(self) -> None:
        rows = [
            {
                "id": 1,
                "session_id": "session-1",
                "email": "primary@example.com",
                "pgp_key": "pgp-key-1",
            },
            {
                "id": 2,
                "session_id": "session-2",
                "email": "secondary@example.com",
                "pgp_key": None,
            },
            {
                "id": 3,
                "session_id": "session-3",
                "email": None,
                "pgp_key": "pgp-key-3",
            },
            {
                "id": 4,
                "session_id": "session-4",
                "email": None,
                "pgp_key": None,
            },
        ]
        for row in rows:
            db.session.execute(
                text(
                    """
                    INSERT INTO users (
                        id,
                        is_admin,
                        password_hash,
                        session_id,
                        email,
                        pgp_key
                    )
                    VALUES (
                        :id,
                        false,
                        '$scrypt$',
                        :session_id,
                        :email,
                        :pgp_key
                    )
                    """
                ),
                row,
            )
        db.session.commit()

    def check_upgrade(self) -> None:
        rows = db.session.execute(
            text(
                """
                SELECT user_id, enabled, position, email, pgp_key
                FROM notification_recipients
                ORDER BY user_id ASC
                """
            )
        ).all()

        assert rows == [
            (1, True, 0, "primary@example.com", "pgp-key-1"),
            (2, True, 0, "secondary@example.com", None),
            (3, True, 0, None, "pgp-key-3"),
        ]

        legacy_rows = db.session.execute(
            text(
                """
                SELECT id, email, pgp_key
                FROM users
                ORDER BY id ASC
                """
            )
        ).all()
        assert legacy_rows == [
            (1, "primary@example.com", "pgp-key-1"),
            (2, "secondary@example.com", None),
            (3, None, "pgp-key-3"),
            (4, None, None),
        ]


class DowngradeTester:
    def load_data(self) -> None:
        rows = [
            {
                "id": 1,
                "session_id": "session-1",
                "email": "primary@example.com",
                "pgp_key": "pgp-key-1",
            },
            {
                "id": 2,
                "session_id": "session-2",
                "email": None,
                "pgp_key": None,
            },
        ]
        for row in rows:
            db.session.execute(
                text(
                    """
                    INSERT INTO users (
                        id,
                        is_admin,
                        is_suspended,
                        password_hash,
                        session_id,
                        email,
                        pgp_key
                    )
                    VALUES (
                        :id,
                        false,
                        false,
                        '$scrypt$',
                        :session_id,
                        :email,
                        :pgp_key
                    )
                    """
                ),
                row,
            )

        db.session.execute(
            text(
                """
                INSERT INTO notification_recipients (
                    user_id,
                    enabled,
                    position,
                    email,
                    pgp_key
                )
                VALUES
                    (1, true, 0, 'primary@example.com', 'pgp-key-1'),
                    (1, false, 1, 'backup@example.com', 'pgp-key-2')
                """
            )
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM users")) == 2
        assert db.session.execute(
            text(
                """
                SELECT email, pgp_key
                FROM users
                WHERE id = 1
                """
            )
        ).one() == ("primary@example.com", "pgp-key-1")
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'notification_recipients'
                    """
                )
            )
            == 0
        )

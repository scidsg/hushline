from sqlalchemy import text

from hushline.db import db


class UpgradeTester:
    def load_data(self) -> None:
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
                    1,
                    false,
                    false,
                    '$scrypt$',
                    'session-1',
                    'primary@example.com',
                    NULL
                )
                """
            )
        )
        db.session.commit()

    def check_upgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM users")) == 1
        assert db.session.execute(
            text(
                """
                SELECT user_id, enabled, position, email
                FROM notification_recipients
                """
            )
        ).one() == (1, True, 0, "primary@example.com")

        for table_name in ("password_reset_attempts", "password_reset_tokens"):
            assert (
                db.session.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table_name},
                )
                == 1
            )


class DowngradeTester:
    def load_data(self) -> None:
        db.session.execute(
            text(
                """
                INSERT INTO users (
                    id,
                    is_admin,
                    is_suspended,
                    password_hash,
                    session_id
                )
                VALUES (1, false, false, '$scrypt$', 'session-1')
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO password_reset_attempts (
                    identifier_hash,
                    ip_hash,
                    created_at
                )
                VALUES (
                    repeat('a', 64),
                    repeat('b', 64),
                    timestamp '2026-04-24 00:00:00'
                )
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO password_reset_tokens (
                    user_id,
                    token_hash,
                    created_at,
                    expires_at,
                    used_at
                )
                VALUES (
                    1,
                    repeat('c', 64),
                    timestamp '2026-04-24 00:00:00',
                    timestamp '2026-04-24 01:00:00',
                    NULL
                )
                """
            )
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM users")) == 1

        for table_name in ("password_reset_attempts", "password_reset_tokens"):
            assert (
                db.session.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table_name},
                )
                == 0
            )

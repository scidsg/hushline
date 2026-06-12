from sqlalchemy import text

from hushline.db import db


def _insert_conversation_participant(include_activity: bool = False) -> None:
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
    db.session.execute(text("INSERT INTO conversations (id) VALUES (1)"))

    if include_activity:
        db.session.execute(
            text(
                """
                INSERT INTO conversation_participants (
                    id,
                    conversation_id,
                    user_id,
                    last_active_at
                )
                VALUES (1, 1, 1, timestamp '2026-06-12 00:00:00')
                """
            )
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO conversation_participants (
                    id,
                    conversation_id,
                    user_id
                )
                VALUES (1, 1, 1)
                """
            )
        )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_conversation_participant()

    def check_upgrade(self) -> None:
        assert db.session.execute(
            text(
                """
                SELECT id, last_active_at
                FROM conversation_participants
                """
            )
        ).one() == (1, None)

        column = db.session.execute(
            text(
                """
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'conversation_participants'
                  AND column_name = 'last_active_at'
                """
            )
        ).one()
        assert column == ("timestamp with time zone", "YES")


class DowngradeTester:
    def load_data(self) -> None:
        _insert_conversation_participant(include_activity=True)

    def check_downgrade(self) -> None:
        assert db.session.scalar(text("SELECT count(*) FROM conversation_participants")) == 1
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'conversation_participants'
                      AND column_name = 'last_active_at'
                    """
                )
            )
            == 0
        )

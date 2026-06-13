from sqlalchemy import text

from hushline.db import db


def _insert_conversation_data(include_read_cursor: bool = False) -> None:
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
    db.session.execute(
        text(
            """
            INSERT INTO conversation_messages (
                id,
                conversation_id,
                sender_participant_id
            )
            VALUES (1, 1, 1)
            """
        )
    )
    if include_read_cursor:
        db.session.execute(
            text(
                """
                UPDATE conversation_participants
                SET last_read_message_id = 1
                WHERE id = 1
                """
            )
        )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_conversation_data()

    def check_upgrade(self) -> None:
        assert db.session.execute(
            text(
                """
                SELECT id, last_read_message_id
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
                  AND column_name = 'last_read_message_id'
                """
            )
        ).one()
        assert column == ("integer", "YES")


class DowngradeTester:
    def load_data(self) -> None:
        _insert_conversation_data(include_read_cursor=True)

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
                      AND column_name = 'last_read_message_id'
                    """
                )
            )
            == 0
        )

from sqlalchemy import text

from hushline.db import db

USER_ID = 9701
CONVERSATION_ID = 9701
PARTICIPANT_ID = 9701
ATTEMPT_ID = 9701


def _chat_rate_limit_attempt_table_count() -> int:
    return db.session.scalar(
        text(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'chat_rate_limit_attempts'
            """
        )
    )


def _insert_conversation_participant() -> None:
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
            VALUES (:user_id, false, false, '$scrypt$', 'session-9701')
            """
        ),
        {"user_id": USER_ID},
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversations (id, public_id)
            VALUES (:conversation_id, '00000000-0000-0000-0000-000000009701')
            """
        ),
        {"conversation_id": CONVERSATION_ID},
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversation_participants (
                id,
                conversation_id,
                user_id
            )
            VALUES (:participant_id, :conversation_id, :user_id)
            """
        ),
        {
            "participant_id": PARTICIPANT_ID,
            "conversation_id": CONVERSATION_ID,
            "user_id": USER_ID,
        },
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_conversation_participant()

    def check_upgrade(self) -> None:
        assert _chat_rate_limit_attempt_table_count() == 1
        columns = db.session.execute(
            text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'chat_rate_limit_attempts'
                ORDER BY column_name
                """
            )
        ).all()
        assert columns == [
            ("conversation_id", "NO"),
            ("created_at", "NO"),
            ("id", "NO"),
            ("sender_participant_id", "NO"),
            ("user_id", "NO"),
        ]

        db.session.execute(
            text(
                """
                INSERT INTO chat_rate_limit_attempts (
                    id,
                    conversation_id,
                    sender_participant_id,
                    user_id,
                    created_at
                )
                VALUES (
                    :attempt_id,
                    :conversation_id,
                    :participant_id,
                    :user_id,
                    timestamp with time zone '2026-06-19 12:00:00+00'
                )
                """
            ),
            {
                "attempt_id": ATTEMPT_ID,
                "conversation_id": CONVERSATION_ID,
                "participant_id": PARTICIPANT_ID,
                "user_id": USER_ID,
            },
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM chat_rate_limit_attempts
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": ATTEMPT_ID},
            )
            == 1
        )


class DowngradeTester:
    def load_data(self) -> None:
        _insert_conversation_participant()
        db.session.execute(
            text(
                """
                INSERT INTO chat_rate_limit_attempts (
                    id,
                    conversation_id,
                    sender_participant_id,
                    user_id,
                    created_at
                )
                VALUES (
                    :attempt_id,
                    :conversation_id,
                    :participant_id,
                    :user_id,
                    timestamp with time zone '2026-06-19 12:00:00+00'
                )
                """
            ),
            {
                "attempt_id": ATTEMPT_ID,
                "conversation_id": CONVERSATION_ID,
                "participant_id": PARTICIPANT_ID,
                "user_id": USER_ID,
            },
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert _chat_rate_limit_attempt_table_count() == 0
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM conversation_participants
                    WHERE id = :participant_id
                    """
                ),
                {"participant_id": PARTICIPANT_ID},
            )
            == 1
        )

from sqlalchemy import text

from hushline.db import db

USER_ID = 9601
CONVERSATION_ID = 9601
PARTICIPANT_ID = 9601


def _deleted_at_column_count() -> int:
    return db.session.scalar(
        text(
            """
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'conversation_participants'
              AND column_name = 'deleted_at'
            """
        )
    )


def _insert_conversation_participant(*, include_deleted_at: bool = False) -> None:
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
            VALUES (:user_id, false, false, '$scrypt$', 'session-9601')
            """
        ),
        {"user_id": USER_ID},
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversations (id, public_id)
            VALUES (:conversation_id, '00000000-0000-0000-0000-000000009601')
            """
        ),
        {"conversation_id": CONVERSATION_ID},
    )

    if include_deleted_at:
        db.session.execute(
            text(
                """
                INSERT INTO conversation_participants (
                    id,
                    conversation_id,
                    user_id,
                    deleted_at
                )
                VALUES (
                    :participant_id,
                    :conversation_id,
                    :user_id,
                    timestamp with time zone '2026-06-18 12:00:00+00'
                )
                """
            ),
            {
                "participant_id": PARTICIPANT_ID,
                "conversation_id": CONVERSATION_ID,
                "user_id": USER_ID,
            },
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
        assert db.session.execute(
            text(
                """
                SELECT id, deleted_at
                FROM conversation_participants
                WHERE id = :participant_id
                """
            ),
            {"participant_id": PARTICIPANT_ID},
        ).one() == (PARTICIPANT_ID, None)

        column = db.session.execute(
            text(
                """
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'conversation_participants'
                  AND column_name = 'deleted_at'
                """
            )
        ).one()
        assert column == ("timestamp with time zone", "YES")


class DowngradeTester:
    def load_data(self) -> None:
        _insert_conversation_participant(include_deleted_at=True)

    def check_downgrade(self) -> None:
        assert _deleted_at_column_count() == 0
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

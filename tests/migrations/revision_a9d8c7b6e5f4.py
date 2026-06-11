from sqlalchemy import text

from hushline.db import db

NEW_TABLES = [
    "conversations",
    "conversation_participants",
    "conversation_messages",
    "conversation_message_copies",
]

NEW_INDEXES = [
    "ix_conversation_participants_user_id_conversation_id",
    "ix_conversation_messages_conversation_id_created_at",
    "ix_conversation_message_copies_participant_message",
]


class UpgradeTester:
    def load_data(self) -> None:
        pass

    def check_upgrade(self) -> None:
        table_names = db.session.scalars(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(:table_names)
                """
            ),
            {"table_names": NEW_TABLES},
        ).all()
        assert sorted(table_names) == sorted(NEW_TABLES)

        indexes = db.session.scalars(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = ANY(:index_names)
                """
            ),
            {"index_names": NEW_INDEXES},
        ).all()
        assert sorted(indexes) == sorted(NEW_INDEXES)

        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'messages'
                      AND column_name = 'conversation_id'
                    """
                )
            )
            == 1
        )

        plaintext_columns = db.session.scalars(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN ('conversation_messages', 'conversation_message_copies')
                  AND column_name = ANY(:column_names)
                """
            ),
            {"column_names": ["body", "content", "plaintext", "message_body"]},
        ).all()
        assert plaintext_columns == []


class DowngradeTester:
    def load_data(self) -> None:
        pass

    def check_downgrade(self) -> None:
        table_count = db.session.scalar(
            text(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(:table_names)
                """
            ),
            {"table_names": NEW_TABLES},
        )
        assert table_count == 0

        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'messages'
                      AND column_name = 'conversation_id'
                    """
                )
            )
            == 0
        )

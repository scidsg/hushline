from sqlalchemy import text

from hushline.db import db

NEW_TABLES = ["chat_keys"]
NEW_INDEXES = ["ix_chat_keys_user_id_disabled_at"]
FORBIDDEN_COLUMNS = [
    "private_key",
    "plaintext_private_key",
    "derived_key",
    "unlock_key",
    "decrypted_message_text",
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
        assert table_names == NEW_TABLES

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
        assert indexes == NEW_INDEXES

        plaintext_columns = db.session.scalars(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'chat_keys'
                  AND column_name = ANY(:column_names)
                """
            ),
            {"column_names": FORBIDDEN_COLUMNS},
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

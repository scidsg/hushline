from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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


def _expect_integrity_error(statement: str, params: dict[str, object]) -> None:
    try:
        db.session.execute(text(statement), params)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    else:
        raise AssertionError("Expected database integrity constraint to reject invalid chat key")


def _insert_user(user_id: int = 8601) -> None:
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
            VALUES (:user_id, false, false, '$scrypt$', :session_id)
            """
        ),
        {"user_id": user_id, "session_id": f"session-{user_id}"},
    )
    db.session.commit()


def _insert_chat_key(user_id: int = 8601, key_version: int = 1) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO chat_keys (
                user_id,
                key_version,
                public_key,
                encrypted_private_key,
                kdf_algorithm,
                kdf_params,
                kdf_salt,
                wrapping_algorithm
            )
            VALUES (
                :user_id,
                :key_version,
                :public_key,
                :encrypted_private_key,
                'PBKDF2-SHA-256',
                '{"iterations": 310000}'::json,
                'salt',
                'AES-GCM'
            )
            """
        ),
        {
            "user_id": user_id,
            "key_version": key_version,
            "public_key": f"public-{key_version}",
            "encrypted_private_key": f"wrapped-private-{key_version}",
        },
    )
    db.session.commit()


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

        storage_columns = db.session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'chat_keys'
                  AND column_name = ANY(:column_names)
                ORDER BY column_name
                """
            ),
            {
                "column_names": [
                    "public_key",
                    "encrypted_private_key",
                    "kdf_algorithm",
                    "kdf_params",
                    "kdf_salt",
                    "wrapping_algorithm",
                ]
            },
        ).all()
        assert storage_columns == [
            ("encrypted_private_key", "text", "NO"),
            ("kdf_algorithm", "character varying", "NO"),
            ("kdf_params", "json", "NO"),
            ("kdf_salt", "text", "NO"),
            ("public_key", "text", "NO"),
            ("wrapping_algorithm", "character varying", "NO"),
        ]

        fk_delete_rule = db.session.scalar(
            text(
                """
                SELECT delete_rule
                FROM information_schema.referential_constraints
                WHERE constraint_schema = 'public'
                  AND constraint_name = 'fk_chat_keys_user_id_users'
                """
            )
        )
        assert fk_delete_rule == "CASCADE"

        _insert_user()
        _insert_chat_key()

        _expect_integrity_error(
            """
            INSERT INTO chat_keys (
                user_id,
                key_version,
                public_key,
                encrypted_private_key,
                kdf_algorithm,
                kdf_params,
                kdf_salt,
                wrapping_algorithm
            )
            VALUES (
                :user_id,
                1,
                'duplicate-public',
                'duplicate-private',
                'PBKDF2-SHA-256',
                '{"iterations": 310000}'::json,
                'salt',
                'AES-GCM'
            )
            """,
            {"user_id": 8601},
        )
        _expect_integrity_error(
            """
            INSERT INTO chat_keys (
                user_id,
                key_version,
                public_key,
                encrypted_private_key,
                kdf_algorithm,
                kdf_params,
                kdf_salt,
                wrapping_algorithm
            )
            VALUES (
                :user_id,
                2,
                'missing-private',
                NULL,
                'PBKDF2-SHA-256',
                '{"iterations": 310000}'::json,
                'salt',
                'AES-GCM'
            )
            """,
            {"user_id": 8601},
        )

        db.session.execute(text("DELETE FROM users WHERE id = 8601"))
        db.session.commit()
        assert db.session.scalar(text("SELECT count(*) FROM chat_keys WHERE user_id = 8601")) == 0


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

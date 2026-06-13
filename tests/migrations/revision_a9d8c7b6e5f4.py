from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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


def _expect_integrity_error(statement: str, params: dict[str, object] | None = None) -> None:
    try:
        db.session.execute(text(statement), params or {})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    else:
        raise AssertionError(
            "Expected database integrity constraint to reject invalid conversation"
        )


def _insert_user(user_id: int, session_id: str) -> None:
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
        {"user_id": user_id, "session_id": session_id},
    )


def _table_columns(table_name: str) -> set[str]:
    return set(
        db.session.scalars(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()
    )


def _insert_username(username_id: int, user_id: int, username: str) -> None:
    values: dict[str, object] = {
        "id": username_id,
        "user_id": user_id,
        "username": username,
        "is_primary": True,
        "is_verified": False,
        "show_in_directory": False,
        "is_featured": False,
    }
    columns = [column for column in values if column in _table_columns("usernames")]
    db.session.execute(
        text(
            f"""
            INSERT INTO usernames ({", ".join(columns)})
            VALUES ({", ".join(f":{column}" for column in columns)})
            """
        ),
        {column: values[column] for column in columns},
    )


def _insert_message(message_id: int, username_id: int, conversation_id: int) -> None:
    values: dict[str, object] = {
        "id": message_id,
        "username_id": username_id,
        "public_id": f"00000000-0000-0000-0000-00000000{message_id}",
        "reply_slug": f"reply-{message_id}",
        "status": "PENDING",
        "conversation_id": conversation_id,
    }
    columns = [column for column in values if column in _table_columns("messages")]
    db.session.execute(
        text(
            f"""
            INSERT INTO messages ({", ".join(columns)})
            VALUES ({", ".join(f":{column}" for column in columns)})
            """
        ),
        {column: values[column] for column in columns},
    )


def _seed_conversation_graph() -> None:
    _insert_user(9701, "session-9701")
    _insert_user(9702, "session-9702")
    _insert_username(9701, 9701, "sender9701")
    db.session.execute(text("INSERT INTO conversations (id) VALUES (9701)"))
    db.session.execute(
        text(
            """
            INSERT INTO conversation_participants (
                id,
                conversation_id,
                user_id
            )
            VALUES
                (97011, 9701, 9701),
                (97012, 9701, 9702)
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
            VALUES (970101, 9701, 97011)
            """
        )
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversation_message_copies (
                id,
                conversation_message_id,
                recipient_participant_id,
                encrypted_payload
            )
            VALUES
                (9701001, 970101, 97011, 'ciphertext-for-sender'),
                (9701002, 970101, 97012, 'ciphertext-for-recipient')
            """
        )
    )
    _insert_message(9701, 9701, 9701)
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

        required_columns = db.session.execute(
            text(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(:table_names)
                  AND column_name = ANY(:column_names)
                ORDER BY table_name, column_name
                """
            ),
            {
                "table_names": [
                    "conversation_participants",
                    "conversation_messages",
                    "conversation_message_copies",
                    "messages",
                ],
                "column_names": [
                    "conversation_id",
                    "encrypted_payload",
                    "has_usable_public_key",
                    "recipient_participant_id",
                    "sender_participant_id",
                ],
            },
        ).all()
        assert required_columns == [
            ("conversation_message_copies", "encrypted_payload", "text", "NO"),
            ("conversation_message_copies", "recipient_participant_id", "integer", "NO"),
            ("conversation_messages", "conversation_id", "integer", "NO"),
            ("conversation_messages", "sender_participant_id", "integer", "NO"),
            ("conversation_participants", "conversation_id", "integer", "NO"),
            ("conversation_participants", "has_usable_public_key", "boolean", "NO"),
            ("messages", "conversation_id", "integer", "YES"),
        ]

        delete_rules = {
            (
                source_table,
                source_column,
                target_table,
                target_column,
            ): delete_rule
            for (
                source_table,
                source_column,
                target_table,
                target_column,
                delete_rule,
            ) in db.session.execute(
                text(
                    """
                    SELECT
                        tc.table_name AS source_table,
                        kcu.column_name AS source_column,
                        ccu.table_name AS target_table,
                        ccu.column_name AS target_column,
                        rc.delete_rule
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_schema = kcu.constraint_schema
                     AND tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                      ON tc.constraint_schema = ccu.constraint_schema
                     AND tc.constraint_name = ccu.constraint_name
                    JOIN information_schema.referential_constraints rc
                      ON tc.constraint_schema = rc.constraint_schema
                     AND tc.constraint_name = rc.constraint_name
                    WHERE tc.constraint_schema = 'public'
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_name = ANY(:table_names)
                    """
                ),
                {
                    "table_names": [
                        "conversation_participants",
                        "conversation_messages",
                        "conversation_message_copies",
                        "messages",
                    ]
                },
            ).all()
        }
        expected_delete_rules = {
            ("conversation_participants", "conversation_id", "conversations", "id"): "CASCADE",
            ("conversation_participants", "user_id", "users", "id"): "CASCADE",
            ("conversation_messages", "conversation_id", "conversations", "id"): "CASCADE",
            (
                "conversation_messages",
                "sender_participant_id",
                "conversation_participants",
                "id",
            ): "CASCADE",
            (
                "conversation_message_copies",
                "conversation_message_id",
                "conversation_messages",
                "id",
            ): "CASCADE",
            (
                "conversation_message_copies",
                "recipient_participant_id",
                "conversation_participants",
                "id",
            ): "CASCADE",
            ("messages", "conversation_id", "conversations", "id"): "SET NULL",
        }
        assert expected_delete_rules.items() <= delete_rules.items()

        _seed_conversation_graph()
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT has_usable_public_key
                    FROM conversation_participants
                    WHERE id = 97011
                    """
                )
            )
            is False
        )

        _expect_integrity_error(
            """
            INSERT INTO conversation_participants (
                conversation_id,
                user_id
            )
            VALUES (9701, 9701)
            """
        )
        _expect_integrity_error(
            """
            INSERT INTO conversation_message_copies (
                conversation_message_id,
                recipient_participant_id,
                encrypted_payload
            )
            VALUES (970101, 97011, 'duplicate-copy')
            """
        )
        _expect_integrity_error(
            """
            INSERT INTO conversation_message_copies (
                conversation_message_id,
                recipient_participant_id,
                encrypted_payload
            )
            VALUES (970101, 97012, NULL)
            """
        )
        _expect_integrity_error(
            """
            INSERT INTO messages (
                username_id,
                public_id,
                reply_slug,
                status,
                conversation_id
            )
            VALUES (
                9701,
                '00000000-0000-0000-0000-000000009702',
                'reply-9702',
                'PENDING',
                9701
            )
            """
        )

        db.session.execute(text("DELETE FROM conversations WHERE id = 9701"))
        db.session.commit()
        assert db.session.scalar(text("SELECT count(*) FROM conversation_participants")) == 0
        assert db.session.scalar(text("SELECT count(*) FROM conversation_messages")) == 0
        assert db.session.scalar(text("SELECT count(*) FROM conversation_message_copies")) == 0
        assert (
            db.session.scalar(text("SELECT conversation_id FROM messages WHERE id = 9701")) is None
        )


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

from sqlalchemy import text

from hushline.db import db


def _insert_user(user_id: int) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO users (id, is_admin, is_cautious, is_suspended, password_hash, session_id)
            VALUES (:id, false, false, false, '$scrypt$', :session_id)
            """
        ),
        {"id": user_id, "session_id": f"session-{user_id}"},
    )


def _insert_legacy_conversation(*, include_versioned_columns: bool) -> None:
    _insert_user(9901)
    _insert_user(9902)
    conversation_columns = (
        ", minimum_protocol_version, version" if include_versioned_columns else ""
    )
    conversation_values = ", 0, 0" if include_versioned_columns else ""
    db.session.execute(
        text(
            f"""
            INSERT INTO conversations (id, public_id{conversation_columns})
            VALUES (9901, '99999999-9999-4999-8999-999999999901'{conversation_values})
            """
        )
    )
    for participant_id, user_id in ((9901, 9901), (9902, 9902)):
        db.session.execute(
            text(
                """
                INSERT INTO conversation_participants (
                    id, conversation_id, user_id, has_usable_public_key
                )
                VALUES (:id, 9901, :user_id, true)
                """
            ),
            {"id": participant_id, "user_id": user_id},
        )
    if include_versioned_columns:
        db.session.execute(
            text(
                """
                INSERT INTO conversation_messages (
                    id,
                    public_id,
                    conversation_id,
                    sender_participant_id,
                    protocol_version
                )
                VALUES (
                    9901,
                    '99999999-9999-4999-8999-999999999902',
                    9901,
                    9901,
                    0
                )
                """
            )
        )
    else:
        db.session.execute(
            text(
                """
                INSERT INTO conversation_messages (id, conversation_id, sender_participant_id)
                VALUES (9901, 9901, 9901)
                """
            )
        )
    db.session.execute(
        text(
            """
            INSERT INTO conversation_message_copies (
                conversation_message_id,
                recipient_participant_id,
                encrypted_payload
            )
            VALUES (9901, 9902, 'legacy-ciphertext')
            """
        )
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_legacy_conversation(include_versioned_columns=False)

    def check_upgrade(self) -> None:
        row = db.session.execute(
            text(
                """
                SELECT protocol_version, conversation_version, idempotency_key
                FROM conversation_messages
                WHERE id = 9901
                """
            )
        ).one()
        assert row == (0, None, None)
        public_id = db.session.scalar(
            text("SELECT public_id FROM conversation_messages WHERE id = 9901")
        )
        assert public_id is not None
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT encrypted_payload
                    FROM conversation_message_copies
                    WHERE conversation_message_id = 9901
                    """
                )
            )
            == "legacy-ciphertext"
        )
        assert db.session.scalar(text("SELECT count(*) FROM chat_accounts")) == 2


class DowngradeTester:
    def load_data(self) -> None:
        _insert_legacy_conversation(include_versioned_columns=True)

    def check_downgrade(self) -> None:
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT encrypted_payload
                    FROM conversation_message_copies
                    WHERE conversation_message_id = 9901
                    """
                )
            )
            == "legacy-ciphertext"
        )
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'conversation_messages'
                      AND column_name = 'protocol_version'
                    """
                )
            )
            == 0
        )

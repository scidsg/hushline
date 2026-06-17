from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db

SENDER_USER_ID = 9901
RECIPIENT_USER_ID = 9902
NONCE_HASH = "a" * 64


def _insert_users() -> None:
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
            VALUES
                (:sender_user_id, false, false, '$scrypt$', 'session-sender-9901'),
                (:recipient_user_id, false, false, '$scrypt$', 'session-recipient-9902')
            """
        ),
        {
            "sender_user_id": SENDER_USER_ID,
            "recipient_user_id": RECIPIENT_USER_ID,
        },
    )
    db.session.commit()


def _table_exists() -> int:
    return db.session.scalar(
        text(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'initial_conversation_nonces'
            """
        )
    )


class UpgradeTester:
    def load_data(self) -> None:
        _insert_users()

    def check_upgrade(self) -> None:
        assert _table_exists() == 1
        columns = db.session.execute(
            text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'initial_conversation_nonces'
                ORDER BY ordinal_position
                """
            )
        ).all()
        assert columns == [
            ("id", "NO"),
            ("nonce_hash", "NO"),
            ("sender_user_id", "NO"),
            ("recipient_user_id", "NO"),
            ("created_at", "NO"),
            ("consumed_at", "YES"),
        ]

        db.session.execute(
            text(
                """
                INSERT INTO initial_conversation_nonces (
                    nonce_hash,
                    sender_user_id,
                    recipient_user_id
                )
                VALUES (:nonce_hash, :sender_user_id, :recipient_user_id)
                """
            ),
            {
                "nonce_hash": NONCE_HASH,
                "sender_user_id": SENDER_USER_ID,
                "recipient_user_id": RECIPIENT_USER_ID,
            },
        )
        db.session.commit()

        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM initial_conversation_nonces
                    WHERE nonce_hash = :nonce_hash
                      AND created_at IS NOT NULL
                      AND consumed_at IS NULL
                    """
                ),
                {"nonce_hash": NONCE_HASH},
            )
            == 1
        )

        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO initial_conversation_nonces (
                        nonce_hash,
                        sender_user_id,
                        recipient_user_id
                    )
                    VALUES (:nonce_hash, :sender_user_id, :recipient_user_id)
                    """
                ),
                {
                    "nonce_hash": NONCE_HASH,
                    "sender_user_id": SENDER_USER_ID,
                    "recipient_user_id": RECIPIENT_USER_ID,
                },
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("duplicate initial conversation nonce hash was accepted")


class DowngradeTester:
    def load_data(self) -> None:
        _insert_users()
        db.session.execute(
            text(
                """
                INSERT INTO initial_conversation_nonces (
                    nonce_hash,
                    sender_user_id,
                    recipient_user_id,
                    consumed_at
                )
                VALUES (:nonce_hash, :sender_user_id, :recipient_user_id, NOW())
                """
            ),
            {
                "nonce_hash": NONCE_HASH,
                "sender_user_id": SENDER_USER_ID,
                "recipient_user_id": RECIPIENT_USER_ID,
            },
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert _table_exists() == 0
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM users
                    WHERE id IN (:sender_user_id, :recipient_user_id)
                    """
                ),
                {
                    "sender_user_id": SENDER_USER_ID,
                    "recipient_user_id": RECIPIENT_USER_ID,
                },
            )
            == 2
        )

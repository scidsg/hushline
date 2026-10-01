import json

from sqlalchemy import text

from hushline.db import db

DEVICE_USER_ID = 9941
PARTICIPANT_USER_ID = 9942
ACCOUNT_ID = 9941
DEVICE_ID = 9941
CONVERSATION_ID = 9941
PARTICIPANT_ID = 9941
IDENTITY_KEY = "historical-account-identity"


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


def _load_data(*, identity_snapshot_column: bool) -> None:
    _insert_user(DEVICE_USER_ID)
    _insert_user(PARTICIPANT_USER_ID)
    db.session.execute(
        text(
            """
            INSERT INTO chat_accounts (
                id, user_id, public_id, identity_version,
                membership_sequence, identity_public_key
            )
            VALUES (
                :id, :user_id, :public_id, 1, 1, :identity_public_key
            )
            """
        ),
        {
            "id": ACCOUNT_ID,
            "user_id": DEVICE_USER_ID,
            "public_id": "99999999-9999-4999-8999-999999999941",
            "identity_public_key": IDENTITY_KEY,
        },
    )
    device_insert = (
        """
        INSERT INTO chat_devices (
            id, account_id, public_id, session_id_hash,
            membership_sequence, key_version, membership_sha256,
            signing_public_key, protocol_identity_public_key,
            membership, membership_signature, expires_at,
            account_identity_public_key
        )
        VALUES (
            :id, :account_id, :public_id, :session_id_hash,
            1, 1, :membership_sha256,
            :signing_public_key, :protocol_identity_public_key,
            CAST(:membership AS JSON), :membership_signature,
            NOW() + INTERVAL '30 days', :identity_public_key
        )
        """
        if identity_snapshot_column
        else """
        INSERT INTO chat_devices (
            id, account_id, public_id, session_id_hash,
            membership_sequence, key_version, membership_sha256,
            signing_public_key, protocol_identity_public_key,
            membership, membership_signature, expires_at
        )
        VALUES (
            :id, :account_id, :public_id, :session_id_hash,
            1, 1, :membership_sha256,
            :signing_public_key, :protocol_identity_public_key,
            CAST(:membership AS JSON), :membership_signature,
            NOW() + INTERVAL '30 days'
        )
        """
    )
    db.session.execute(
        text(device_insert),
        {
            "id": DEVICE_ID,
            "account_id": ACCOUNT_ID,
            "public_id": "99999999-9999-4999-8999-999999999942",
            "session_id_hash": "a" * 64,
            "membership_sha256": "b" * 64,
            "signing_public_key": "device-signing-key",
            "protocol_identity_public_key": "protocol-identity-key",
            "membership": json.dumps({"device_id": "historical-device"}),
            "membership_signature": "membership-signature",
            "identity_public_key": IDENTITY_KEY,
        },
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversations (id, public_id, minimum_protocol_version, version)
            VALUES (:id, :public_id, 1, 1)
            """
        ),
        {
            "id": CONVERSATION_ID,
            "public_id": "99999999-9999-4999-8999-999999999943",
        },
    )
    db.session.execute(
        text(
            """
            INSERT INTO conversation_participants (
                id, conversation_id, user_id, has_usable_public_key
            )
            VALUES (:id, :conversation_id, :user_id, true)
            """
        ),
        {
            "id": PARTICIPANT_ID,
            "conversation_id": CONVERSATION_ID,
            "user_id": PARTICIPANT_USER_ID,
        },
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _load_data(identity_snapshot_column=False)

    def check_upgrade(self) -> None:
        assert (
            db.session.scalar(
                text("SELECT account_identity_public_key FROM chat_devices WHERE id = :id"),
                {"id": DEVICE_ID},
            )
            == IDENTITY_KEY
        )

        db.session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": PARTICIPANT_USER_ID},
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text("SELECT user_id FROM conversation_participants WHERE id = :id"),
                {"id": PARTICIPANT_ID},
            )
            is None
        )


class DowngradeTester:
    def load_data(self) -> None:
        _load_data(identity_snapshot_column=True)
        db.session.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": PARTICIPANT_USER_ID},
        )
        db.session.commit()

    def check_downgrade(self) -> None:
        assert (
            db.session.scalar(
                text(
                    """
                SELECT count(*)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'chat_devices'
                  AND column_name = 'account_identity_public_key'
                """
                )
            )
            == 0
        )
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM conversation_participants WHERE id = :id"),
                {"id": PARTICIPANT_ID},
            )
            == 0
        )
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM conversations WHERE id = :id"),
                {"id": CONVERSATION_ID},
            )
            == 0
        )
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM chat_devices WHERE id = :id"),
                {"id": DEVICE_ID},
            )
            == 1
        )

from cryptography.fernet import Fernet
from sqlalchemy import text

from hushline.crypto import serialize_encrypted_field_envelope
from hushline.db import db

REVISION = "b2039e7c0a1d"
LEGACY_FERNET_KEY = "jY0gDbATEOQolx2SGj46YnkkbN6HQBB4YCABzwl1H1A="

USER_COLUMNS = (
    "totp_secret",
    "email",
    "smtp_server",
    "smtp_username",
    "smtp_password",
)
ENCRYPTED_COLUMNS = (
    ("users", "totp_secret"),
    ("users", "email"),
    ("users", "smtp_server"),
    ("users", "smtp_username"),
    ("users", "smtp_password"),
    ("notification_recipients", "email"),
)


def _legacy_fernet_token(plaintext: str) -> str:
    return (
        Fernet(LEGACY_FERNET_KEY.encode())
        .encrypt_at_time(plaintext.encode(), current_time=0)
        .decode()
    )


LEGACY_CIPHERTEXT_BY_COLUMN = {
    "totp_secret": _legacy_fernet_token("legacy-totp-secret"),
    "email": _legacy_fernet_token("legacy@example.com"),
    "smtp_server": _legacy_fernet_token("smtp.legacy.example"),
    "smtp_username": _legacy_fernet_token("legacy-smtp-user"),
    "smtp_password": _legacy_fernet_token("legacy-smtp-password"),
    "notification_recipient_email": _legacy_fernet_token("recipient@example.com"),
}
OVERSIZED_ENVELOPE_CIPHERTEXT = serialize_encrypted_field_envelope(_legacy_fernet_token("x" * 180))
assert len(OVERSIZED_ENVELOPE_CIPHERTEXT) > 255


def _column_metadata(table_name: str, column_name: str) -> tuple[str, int | None]:
    row = db.session.execute(
        text(
            """
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).one()
    return row[0], row[1]


def _assert_text_columns() -> None:
    for table_name, column_name in ENCRYPTED_COLUMNS:
        assert _column_metadata(table_name, column_name) == ("text", None)


def _assert_legacy_varchar_columns() -> None:
    for table_name, column_name in ENCRYPTED_COLUMNS:
        assert _column_metadata(table_name, column_name) == ("character varying", 255)


def _insert_user_with_legacy_ciphertext() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO users (
                id,
                is_admin,
                is_suspended,
                password_hash,
                session_id,
                totp_secret,
                email,
                smtp_server,
                smtp_username,
                smtp_password
            )
            VALUES (
                1,
                false,
                false,
                '$scrypt$',
                'session-1',
                :totp_secret,
                :email,
                :smtp_server,
                :smtp_username,
                :smtp_password
            )
            """
        ),
        {column: LEGACY_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS},
    )


def _insert_notification_recipient_with_legacy_ciphertext() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO notification_recipients (
                user_id,
                enabled,
                position,
                email
            )
            VALUES (
                1,
                true,
                0,
                :email
            )
            """
        ),
        {"email": LEGACY_CIPHERTEXT_BY_COLUMN["notification_recipient_email"]},
    )


def _assert_legacy_ciphertext_preserved() -> None:
    user_row = db.session.execute(
        text(
            """
            SELECT totp_secret, email, smtp_server, smtp_username, smtp_password
            FROM users
            WHERE id = 1
            """
        )
    ).one()
    assert user_row == tuple(LEGACY_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS)

    recipient_email = db.session.scalar(
        text(
            """
            SELECT email
            FROM notification_recipients
            WHERE user_id = 1
            """
        )
    )
    assert recipient_email == LEGACY_CIPHERTEXT_BY_COLUMN["notification_recipient_email"]


class UpgradeTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        db.session.commit()

    def check_upgrade(self) -> None:
        _assert_text_columns()
        _assert_legacy_ciphertext_preserved()


class DowngradeTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        db.session.commit()

    def check_downgrade(self) -> None:
        _assert_legacy_varchar_columns()
        _assert_legacy_ciphertext_preserved()


class DowngradeGuardTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        db.session.execute(
            text(
                """
                UPDATE users
                SET email = :email
                WHERE id = 1
                """
            ),
            {"email": OVERSIZED_ENVELOPE_CIPHERTEXT},
        )
        db.session.commit()

    def check_value_preserved(self) -> None:
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT email
                    FROM users
                    WHERE id = 1
                    """
                )
            )
            == OVERSIZED_ENVELOPE_CIPHERTEXT
        )

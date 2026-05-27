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
SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN = {
    column: serialize_encrypted_field_envelope(_legacy_fernet_token(f"safe-{column}"))
    for column in USER_COLUMNS
}
SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN["notification_recipient_email"] = (
    serialize_encrypted_field_envelope(_legacy_fernet_token("safe-notification-recipient-email"))
)
assert all(len(value) <= 255 for value in SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN.values())
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


def _insert_user(id_: int, ciphertext_by_column: dict[str, str | None]) -> None:
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
                :id,
                false,
                false,
                :password_hash,
                :session_id,
                :totp_secret,
                :email,
                :smtp_server,
                :smtp_username,
                :smtp_password
            )
            """
        ),
        {
            "id": id_,
            "password_hash": f"$scrypt${id_}",
            "session_id": f"session-{id_}",
            **ciphertext_by_column,
        },
    )


def _insert_notification_recipient(id_: int, user_id: int, email: str | None) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO notification_recipients (
                id,
                user_id,
                enabled,
                position,
                email
            )
            VALUES (
                :id,
                :user_id,
                true,
                0,
                :email
            )
            """
        ),
        {"id": id_, "user_id": user_id, "email": email},
    )


def _insert_user_with_legacy_ciphertext() -> None:
    _insert_user(1, {column: LEGACY_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS})


def _insert_notification_recipient_with_legacy_ciphertext() -> None:
    _insert_notification_recipient(
        1,
        1,
        LEGACY_CIPHERTEXT_BY_COLUMN["notification_recipient_email"],
    )


def _insert_null_empty_and_safe_envelope_ciphertext() -> None:
    _insert_user(2, {column: None for column in USER_COLUMNS})
    _insert_user(3, {column: "" for column in USER_COLUMNS})
    _insert_user(
        4,
        {column: SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS},
    )
    _insert_notification_recipient(2, 2, None)
    _insert_notification_recipient(3, 3, "")
    _insert_notification_recipient(
        4,
        4,
        SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN["notification_recipient_email"],
    )


def _user_ciphertext_values(id_: int) -> tuple[str | None, ...]:
    user_row = db.session.execute(
        text(
            """
            SELECT totp_secret, email, smtp_server, smtp_username, smtp_password
            FROM users
            WHERE id = :id
            """
        ),
        {"id": id_},
    ).one()
    return tuple(user_row)


def _notification_recipient_email(id_: int) -> str | None:
    return db.session.scalar(
        text(
            """
            SELECT email
            FROM notification_recipients
            WHERE id = :id
            """
        ),
        {"id": id_},
    )


def _assert_legacy_ciphertext_preserved() -> None:
    assert _user_ciphertext_values(1) == tuple(
        LEGACY_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS
    )
    recipient_email = _notification_recipient_email(1)
    assert recipient_email == LEGACY_CIPHERTEXT_BY_COLUMN["notification_recipient_email"]


def _assert_null_empty_and_safe_envelope_ciphertext_preserved() -> None:
    assert _user_ciphertext_values(2) == tuple(None for _ in USER_COLUMNS)
    assert _user_ciphertext_values(3) == tuple("" for _ in USER_COLUMNS)
    assert _user_ciphertext_values(4) == tuple(
        SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN[column] for column in USER_COLUMNS
    )
    assert _notification_recipient_email(2) is None
    assert _notification_recipient_email(3) == ""
    assert (
        _notification_recipient_email(4)
        == SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN["notification_recipient_email"]
    )


class UpgradeTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        _insert_null_empty_and_safe_envelope_ciphertext()
        db.session.commit()

    def check_upgrade(self) -> None:
        _assert_text_columns()
        _assert_legacy_ciphertext_preserved()
        _assert_null_empty_and_safe_envelope_ciphertext_preserved()


class DowngradeTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        _insert_null_empty_and_safe_envelope_ciphertext()
        db.session.commit()

    def check_downgrade(self) -> None:
        _assert_legacy_varchar_columns()
        _assert_legacy_ciphertext_preserved()
        _assert_null_empty_and_safe_envelope_ciphertext_preserved()


class DowngradeGuardTester:
    def __init__(self, table_name: str, column_name: str) -> None:
        if (table_name, column_name) not in ENCRYPTED_COLUMNS:
            raise ValueError(f"Unexpected encrypted column: {table_name}.{column_name}")
        self.table_name = table_name
        self.column_name = column_name
        self.expected_user_values: tuple[str | None, ...] | None = None
        self.expected_recipient_email: str | None = None

    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        db.session.execute(
            text(f"UPDATE {self.table_name} SET {self.column_name} = :value WHERE id = 1"),
            {"value": OVERSIZED_ENVELOPE_CIPHERTEXT},
        )
        db.session.commit()
        self.expected_user_values = _user_ciphertext_values(1)
        self.expected_recipient_email = _notification_recipient_email(1)

    def check_value_preserved(self) -> None:
        assert (
            db.session.scalar(
                text(
                    f"""
                    SELECT {self.column_name}
                    FROM {self.table_name}
                    WHERE id = 1
                    """
                )
            )
            == OVERSIZED_ENVELOPE_CIPHERTEXT
        )
        assert self.expected_user_values is not None
        assert _user_ciphertext_values(1) == self.expected_user_values
        assert _notification_recipient_email(1) == self.expected_recipient_email


class RollbackReadabilityTester:
    def load_data(self) -> None:
        _insert_user_with_legacy_ciphertext()
        _insert_notification_recipient_with_legacy_ciphertext()
        _insert_null_empty_and_safe_envelope_ciphertext()
        db.session.commit()

    def encrypted_values(self) -> tuple[str, ...]:
        return (
            *(value for value in _user_ciphertext_values(1) if isinstance(value, str) and value),
            *(value for value in _user_ciphertext_values(4) if isinstance(value, str) and value),
            LEGACY_CIPHERTEXT_BY_COLUMN["notification_recipient_email"],
            SAFE_ENVELOPE_CIPHERTEXT_BY_COLUMN["notification_recipient_email"],
        )

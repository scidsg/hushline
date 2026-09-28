from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db

USER_ID = 2416001
OTHER_USER_ID = 2416002
TABLES = ["webauthn_challenges", "webauthn_credentials", "webauthn_user_handles"]


def _insert_user(user_id: int) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO users (id, is_admin, is_suspended, password_hash, session_id)
            VALUES (:user_id, false, false, '$scrypt$', :session_id)
            """
        ),
        {"user_id": user_id, "session_id": f"session-{user_id}"},
    )
    db.session.commit()


def _insert_webauthn_rows() -> None:
    now = datetime.now(UTC)
    db.session.execute(
        text(
            """
            INSERT INTO webauthn_user_handles (user_id, handle)
            VALUES (:user_id, :handle)
            """
        ),
        {"user_id": USER_ID, "handle": b"h" * 64},
    )
    db.session.execute(
        text(
            """
            INSERT INTO webauthn_credentials (
                user_id, credential_id, public_key, algorithm, sign_count,
                transports, device_type, backed_up
            )
            VALUES (
                :user_id, :credential_id, :public_key, -7, 0,
                CAST(:transports AS JSON), 'single_device', false
            )
            """
        ),
        {
            "user_id": USER_ID,
            "credential_id": b"credential-id",
            "public_key": b"public-key",
            "transports": '["usb"]',
        },
    )
    db.session.execute(
        text(
            """
            INSERT INTO webauthn_challenges (
                user_id, purpose, challenge_hash, session_binding_hash,
                created_at, expires_at
            )
            VALUES (
                :user_id, 'registration', :challenge_hash, :session_hash,
                :created_at, :expires_at
            )
            """
        ),
        {
            "user_id": USER_ID,
            "challenge_hash": b"c" * 32,
            "session_hash": b"s" * 32,
            "created_at": now,
            "expires_at": now + timedelta(minutes=5),
        },
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_user(USER_ID)
        _insert_user(OTHER_USER_ID)

    def check_upgrade(self) -> None:
        tables = set(
            db.session.scalars(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = ANY(:tables)
                    """
                ),
                {"tables": TABLES},
            ).all()
        )
        assert tables == set(TABLES)
        _insert_webauthn_rows()

        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO webauthn_credentials (
                        user_id, credential_id, public_key, algorithm, sign_count,
                        transports, device_type, backed_up
                    )
                    VALUES (
                        :user_id, :credential_id, :public_key, -7, 0,
                        CAST(:transports AS JSON), 'single_device', false
                    )
                    """
                ),
                {
                    "user_id": OTHER_USER_ID,
                    "credential_id": b"credential-id",
                    "public_key": b"other-key",
                    "transports": "[]",
                },
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("credential IDs must be globally unique")

        db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": USER_ID})
        db.session.commit()
        for table in TABLES:
            assert db.session.scalar(text(f"SELECT count(*) FROM {table}")) == 0


class DowngradeTester:
    def load_data(self) -> None:
        _insert_user(USER_ID)
        _insert_webauthn_rows()

    def check_downgrade(self) -> None:
        table_count = db.session.scalar(
            text(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = ANY(:tables)
                """
            ),
            {"tables": TABLES},
        )
        assert table_count == 0
        assert (
            db.session.scalar(
                text("SELECT count(*) FROM users WHERE id = :user_id"), {"user_id": USER_ID}
            )
            == 1
        )

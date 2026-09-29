from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db

USER_ID = 2419001
TABLES = ["recovery_code_batches", "recovery_codes"]


def _insert_user() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO users (id, is_admin, is_suspended, password_hash, session_id)
            VALUES (:user_id, false, false, '$scrypt$', :session_id)
            """
        ),
        {"user_id": USER_ID, "session_id": f"session-{USER_ID}"},
    )
    db.session.commit()


def _insert_recovery_rows() -> None:
    batch_id = db.session.scalar(
        text(
            """
            INSERT INTO recovery_code_batches (user_id, acknowledged_at)
            VALUES (:user_id, :acknowledged_at)
            RETURNING id
            """
        ),
        {"user_id": USER_ID, "acknowledged_at": datetime.now(UTC)},
    )
    db.session.execute(
        text(
            """
            INSERT INTO recovery_codes (batch_id, code_hash)
            VALUES (:batch_id, :code_hash)
            """
        ),
        {"batch_id": batch_id, "code_hash": b"r" * 32},
    )
    db.session.commit()


class UpgradeTester:
    def load_data(self) -> None:
        _insert_user()

    def check_upgrade(self) -> None:
        _insert_recovery_rows()
        try:
            db.session.execute(
                text(
                    """
                    INSERT INTO recovery_codes (batch_id, code_hash)
                    SELECT id, :code_hash FROM recovery_code_batches WHERE user_id = :user_id
                    """
                ),
                {"user_id": USER_ID, "code_hash": b"r" * 32},
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        else:
            raise AssertionError("recovery code hashes must be unique")

        db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": USER_ID})
        db.session.commit()
        for table in TABLES:
            assert db.session.scalar(text(f"SELECT count(*) FROM {table}")) == 0


class DowngradeTester:
    def load_data(self) -> None:
        _insert_user()
        _insert_recovery_rows()

    def check_downgrade(self) -> None:
        table_count = db.session.scalar(
            text(
                """
                SELECT count(*) FROM information_schema.tables
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

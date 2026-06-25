from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hushline.db import db

ADMIN_USER_ID = 9801
RECIPIENT_USER_ID = 9802
BROADCAST_ID = 9801
RECIPIENT_ID = 9801

NEW_TABLES = ["admin_broadcasts", "admin_broadcast_recipients"]
NEW_INDEXES = [
    "ix_admin_broadcasts_admin_user_id",
    "ix_admin_broadcasts_public_id",
    "ix_admin_broadcasts_status_created_at",
    "ix_admin_broadcast_recipients_broadcast_id",
    "ix_admin_broadcast_recipients_broadcast_status",
    "ix_admin_broadcast_recipients_user_id",
]


def _insert_user(user_id: int, *, is_admin: bool = False) -> None:
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
            VALUES (:user_id, :is_admin, false, '$scrypt$', :session_id)
            """
        ),
        {
            "user_id": user_id,
            "is_admin": is_admin,
            "session_id": f"session-{user_id}",
        },
    )
    db.session.commit()


def _insert_users() -> None:
    _insert_user(ADMIN_USER_ID, is_admin=True)
    _insert_user(RECIPIENT_USER_ID)


def _insert_broadcast() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO admin_broadcasts (
                id,
                public_id,
                admin_user_id
            )
            VALUES (
                :broadcast_id,
                '00000000-0000-0000-0000-000000009801',
                :admin_user_id
            )
            """
        ),
        {
            "broadcast_id": BROADCAST_ID,
            "admin_user_id": ADMIN_USER_ID,
        },
    )
    db.session.commit()


def _insert_recipient() -> None:
    db.session.execute(
        text(
            """
            INSERT INTO admin_broadcast_recipients (
                id,
                broadcast_id,
                user_id
            )
            VALUES (
                :recipient_id,
                :broadcast_id,
                :user_id
            )
            """
        ),
        {
            "recipient_id": RECIPIENT_ID,
            "broadcast_id": BROADCAST_ID,
            "user_id": RECIPIENT_USER_ID,
        },
    )
    db.session.commit()


def _expect_integrity_error(statement: str, params: dict[str, object]) -> None:
    try:
        db.session.execute(text(statement), params)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    else:
        raise AssertionError("Expected database integrity constraint to reject invalid row")


class UpgradeTester:
    def load_data(self) -> None:
        _insert_users()

    def check_upgrade(self) -> None:
        table_names = set(
            db.session.scalars(
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
        )
        assert table_names == set(NEW_TABLES)

        indexes = set(
            db.session.scalars(
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
        )
        assert indexes == set(NEW_INDEXES)

        columns = db.session.execute(
            text(
                """
                SELECT table_name, column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(:table_names)
                ORDER BY table_name, ordinal_position
                """
            ),
            {"table_names": NEW_TABLES},
        ).all()
        assert columns == [
            ("admin_broadcast_recipients", "id", "NO"),
            ("admin_broadcast_recipients", "broadcast_id", "NO"),
            ("admin_broadcast_recipients", "user_id", "NO"),
            ("admin_broadcast_recipients", "status", "NO"),
            ("admin_broadcast_recipients", "message_id", "YES"),
            ("admin_broadcast_recipients", "failure_reason", "YES"),
            ("admin_broadcast_recipients", "created_at", "NO"),
            ("admin_broadcast_recipients", "updated_at", "NO"),
            ("admin_broadcasts", "id", "NO"),
            ("admin_broadcasts", "public_id", "NO"),
            ("admin_broadcasts", "admin_user_id", "YES"),
            ("admin_broadcasts", "status", "NO"),
            ("admin_broadcasts", "created_at", "NO"),
            ("admin_broadcasts", "updated_at", "NO"),
            ("admin_broadcasts", "completed_at", "YES"),
        ]

        _insert_broadcast()
        _insert_recipient()

        status_values = db.session.execute(
            text(
                """
                SELECT
                    b.status AS broadcast_status,
                    r.status AS recipient_status
                FROM admin_broadcasts b
                JOIN admin_broadcast_recipients r ON r.broadcast_id = b.id
                WHERE b.id = :broadcast_id
                """
            ),
            {"broadcast_id": BROADCAST_ID},
        ).one()
        assert status_values == ("in_progress", "pending")

        _expect_integrity_error(
            """
            INSERT INTO admin_broadcast_recipients (
                broadcast_id,
                user_id
            )
            VALUES (
                :broadcast_id,
                :user_id
            )
            """,
            {
                "broadcast_id": BROADCAST_ID,
                "user_id": RECIPIENT_USER_ID,
            },
        )

        db.session.execute(
            text("DELETE FROM admin_broadcasts WHERE id = :broadcast_id"),
            {"broadcast_id": BROADCAST_ID},
        )
        db.session.commit()
        assert (
            db.session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM admin_broadcast_recipients
                    WHERE broadcast_id = :broadcast_id
                    """
                ),
                {"broadcast_id": BROADCAST_ID},
            )
            == 0
        )


class DowngradeTester:
    def load_data(self) -> None:
        _insert_users()
        _insert_broadcast()
        _insert_recipient()

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
                    FROM users
                    WHERE id = ANY(:user_ids)
                    """
                ),
                {"user_ids": [ADMIN_USER_ID, RECIPIENT_USER_ID]},
            )
            == 2
        )

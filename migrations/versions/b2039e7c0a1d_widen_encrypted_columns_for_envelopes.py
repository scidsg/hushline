"""widen encrypted columns for envelopes

Revision ID: b2039e7c0a1d
Revises: a4c8f2d9e713
Create Date: 2026-05-26 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2039e7c0a1d"
down_revision = "a4c8f2d9e713"
branch_labels = None
depends_on = None


ENCRYPTED_SHORT_STRING_COLUMNS = (
    ("users", "totp_secret"),
    ("users", "email"),
    ("users", "smtp_server"),
    ("users", "smtp_username"),
    ("users", "smtp_password"),
    ("notification_recipients", "email"),
)


def upgrade() -> None:
    for table_name, column_name in ENCRYPTED_SHORT_STRING_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    _raise_if_any_value_exceeds_legacy_limit()

    for table_name, column_name in ENCRYPTED_SHORT_STRING_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def _raise_if_any_value_exceeds_legacy_limit() -> None:
    conn = op.get_bind()
    for table_name, column_name in ENCRYPTED_SHORT_STRING_COLUMNS:
        over_limit_count = conn.execute(
            sa.text(
                f"""
                SELECT count(*)
                FROM {table_name}
                WHERE {column_name} IS NOT NULL
                  AND char_length({column_name}) > 255
                """
            )
        ).scalar_one()

        if over_limit_count:
            raise RuntimeError(
                "Cannot downgrade encrypted column "
                f"{table_name}.{column_name} to VARCHAR(255): "
                f"{over_limit_count} value(s) exceed 255 characters."
            )

"""add password reset tables

Revision ID: 2d8a1f7c9b41
Revises: d1f0e9c2b7aa
Create Date: 2026-04-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d8a1f7c9b41"
down_revision = "d1f0e9c2b7aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_password_reset_attempts_identifier_created",
        "password_reset_attempts",
        ["identifier_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_password_reset_attempts_ip_created",
        "password_reset_attempts",
        ["ip_hash", "created_at"],
        unique=False,
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"),
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "idx_password_reset_tokens_user_used_expires",
        "password_reset_tokens",
        ["user_id", "used_at", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_password_reset_tokens_user_used_expires", table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_token_hash"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("idx_password_reset_attempts_ip_created", table_name="password_reset_attempts")
    op.drop_index(
        "idx_password_reset_attempts_identifier_created",
        table_name="password_reset_attempts",
    )
    op.drop_table("password_reset_attempts")

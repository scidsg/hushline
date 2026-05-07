"""add embed rate limit attempts

Revision ID: a4c8f2d9e713
Revises: 7b9c2d1e4f60
Create Date: 2026-05-07 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4c8f2d9e713"
down_revision = "7b9c2d1e4f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embed_rate_limit_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("bucket_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_embed_rate_limit_attempts_scope_bucket_created",
        "embed_rate_limit_attempts",
        ["scope", "bucket_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_embed_rate_limit_attempts_created",
        "embed_rate_limit_attempts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_embed_rate_limit_attempts_created",
        table_name="embed_rate_limit_attempts",
    )
    op.drop_index(
        "idx_embed_rate_limit_attempts_scope_bucket_created",
        table_name="embed_rate_limit_attempts",
    )
    op.drop_table("embed_rate_limit_attempts")

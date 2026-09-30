"""add single-use recovery codes

Revision ID: 7a4c9e2f1b63
Revises: 3f6e8a1c2d4b
Create Date: 2026-09-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "7a4c9e2f1b63"
down_revision = "3f6e8a1c2d4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recovery_code_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recovery_code_batches_user_id",
        "recovery_code_batches",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(code_hash) = 32",
            name="ck_recovery_codes_hash_length",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["recovery_code_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recovery_codes_batch_consumed",
        "recovery_codes",
        ["batch_id", "consumed_at"],
        unique=False,
    )
    op.create_index("ix_recovery_codes_batch_id", "recovery_codes", ["batch_id"], unique=False)
    op.create_index("ix_recovery_codes_code_hash", "recovery_codes", ["code_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_recovery_codes_code_hash", table_name="recovery_codes")
    op.drop_index("ix_recovery_codes_batch_id", table_name="recovery_codes")
    op.drop_index("ix_recovery_codes_batch_consumed", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index("ix_recovery_code_batches_user_id", table_name="recovery_code_batches")
    op.drop_table("recovery_code_batches")

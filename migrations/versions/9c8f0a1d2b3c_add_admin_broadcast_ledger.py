"""add admin broadcast ledger

Revision ID: 9c8f0a1d2b3c
Revises: 4d2a7c9e1b64
Create Date: 2026-06-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c8f0a1d2b3c"
down_revision = "4d2a7c9e1b64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_admin_broadcasts_admin_user_id",
        "admin_broadcasts",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_broadcasts_public_id",
        "admin_broadcasts",
        ["public_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_broadcasts_status_created_at",
        "admin_broadcasts",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "admin_broadcast_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["broadcast_id"],
            ["admin_broadcasts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_id", "user_id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(
        "ix_admin_broadcast_recipients_broadcast_id",
        "admin_broadcast_recipients",
        ["broadcast_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_broadcast_recipients_broadcast_status",
        "admin_broadcast_recipients",
        ["broadcast_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_admin_broadcast_recipients_user_id",
        "admin_broadcast_recipients",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_broadcast_recipients_user_id",
        table_name="admin_broadcast_recipients",
    )
    op.drop_index(
        "ix_admin_broadcast_recipients_broadcast_status",
        table_name="admin_broadcast_recipients",
    )
    op.drop_index(
        "ix_admin_broadcast_recipients_broadcast_id",
        table_name="admin_broadcast_recipients",
    )
    op.drop_table("admin_broadcast_recipients")
    op.drop_index("ix_admin_broadcasts_status_created_at", table_name="admin_broadcasts")
    op.drop_index("ix_admin_broadcasts_public_id", table_name="admin_broadcasts")
    op.drop_index("ix_admin_broadcasts_admin_user_id", table_name="admin_broadcasts")
    op.drop_table("admin_broadcasts")

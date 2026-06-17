"""add initial conversation nonces

Revision ID: 0f6d4c8e9a21
Revises: 8a4e2c9f1b7d
Create Date: 2026-06-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0f6d4c8e9a21"
down_revision = "8a4e2c9f1b7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "initial_conversation_nonces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce_hash"),
    )
    op.create_index(
        "ix_initial_conversation_nonces_consumed_at",
        "initial_conversation_nonces",
        ["consumed_at"],
        unique=False,
    )
    op.create_index(
        "ix_initial_conversation_nonces_recipient_user_id",
        "initial_conversation_nonces",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_initial_conversation_nonces_sender_recipient_created",
        "initial_conversation_nonces",
        ["sender_user_id", "recipient_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_initial_conversation_nonces_sender_user_id",
        "initial_conversation_nonces",
        ["sender_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_initial_conversation_nonces_sender_user_id",
        table_name="initial_conversation_nonces",
    )
    op.drop_index(
        "ix_initial_conversation_nonces_sender_recipient_created",
        table_name="initial_conversation_nonces",
    )
    op.drop_index(
        "ix_initial_conversation_nonces_recipient_user_id",
        table_name="initial_conversation_nonces",
    )
    op.drop_index(
        "ix_initial_conversation_nonces_consumed_at",
        table_name="initial_conversation_nonces",
    )
    op.drop_table("initial_conversation_nonces")

"""add chat rate limit attempts

Revision ID: 4d2a7c9e1b64
Revises: 2f9a7c8d1e6b
Create Date: 2026-06-19 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d2a7c9e1b64"
down_revision = "2f9a7c8d1e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_rate_limit_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sender_participant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sender_participant_id"],
            ["conversation_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_chat_rate_limit_attempts_sender_conversation_created",
        "chat_rate_limit_attempts",
        ["sender_participant_id", "conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_chat_rate_limit_attempts_user_created",
        "chat_rate_limit_attempts",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_chat_rate_limit_attempts_conversation_created",
        "chat_rate_limit_attempts",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_chat_rate_limit_attempts_created",
        "chat_rate_limit_attempts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_chat_rate_limit_attempts_created",
        table_name="chat_rate_limit_attempts",
    )
    op.drop_index(
        "idx_chat_rate_limit_attempts_conversation_created",
        table_name="chat_rate_limit_attempts",
    )
    op.drop_index(
        "idx_chat_rate_limit_attempts_user_created",
        table_name="chat_rate_limit_attempts",
    )
    op.drop_index(
        "idx_chat_rate_limit_attempts_sender_conversation_created",
        table_name="chat_rate_limit_attempts",
    )
    op.drop_table("chat_rate_limit_attempts")

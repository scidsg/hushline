"""add conversation read cursor

Revision ID: 1c2d3e4f5a6b
Revises: 7d1c2f3a4b5c
Create Date: 2026-06-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1c2d3e4f5a6b"
down_revision = "7d1c2f3a4b5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_participants",
        sa.Column("last_read_message_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_conversation_participants_last_read_message_id"),
        "conversation_participants",
        ["last_read_message_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_conversation_participants_last_read_message_id_conversation_messages"),
        "conversation_participants",
        "conversation_messages",
        ["last_read_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_conversation_participants_last_read_message_id_conversation_messages"),
        "conversation_participants",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_conversation_participants_last_read_message_id"),
        table_name="conversation_participants",
    )
    op.drop_column("conversation_participants", "last_read_message_id")

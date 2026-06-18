"""add conversation participant deleted_at

Revision ID: 2f9a7c8d1e6b
Revises: 0f6d4c8e9a21
Create Date: 2026-06-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2f9a7c8d1e6b"
down_revision = "0f6d4c8e9a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_participants",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_participants", "deleted_at")

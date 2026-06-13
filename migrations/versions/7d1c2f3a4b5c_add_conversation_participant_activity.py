"""add conversation participant activity

Revision ID: 7d1c2f3a4b5c
Revises: f6c1e2d3a4b5
Create Date: 2026-06-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d1c2f3a4b5c"
down_revision = "f6c1e2d3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_participants",
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_participants", "last_active_at")

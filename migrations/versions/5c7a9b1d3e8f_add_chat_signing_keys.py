"""add chat signing keys

Revision ID: 5c7a9b1d3e8f
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c7a9b1d3e8f"
down_revision = "1c2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_keys", sa.Column("public_signing_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_keys", "public_signing_key")

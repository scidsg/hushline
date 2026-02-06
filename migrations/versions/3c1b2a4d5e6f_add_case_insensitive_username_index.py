"""add case-insensitive username index

Revision ID: 3c1b2a4d5e6f
Revises: 7d6a9f2f8c1a
Create Date: 2026-02-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3c1b2a4d5e6f"
down_revision = "7d6a9f2f8c1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_usernames_username_lower",
        "usernames",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_usernames_username_lower", table_name="usernames")

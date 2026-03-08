"""add case-insensitive username index

Revision ID: 3c1b2a4d5e6f
Revises: 9f7c4c3ea9a1
Create Date: 2026-03-08 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3c1b2a4d5e6f"
down_revision = "9f7c4c3ea9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_usernames_username_lower
            ON usernames (lower(username))
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX uq_usernames_username_lower"))

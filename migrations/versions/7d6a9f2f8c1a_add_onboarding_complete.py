"""Add onboarding complete flag to users.

Revision ID: 7d6a9f2f8c1a
Revises: b6a1e3f5a2b1
Create Date: 2025-02-14 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d6a9f2f8c1a"
down_revision = "b6a1e3f5a2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "onboarding_complete",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute("UPDATE users SET onboarding_complete = true")


def downgrade() -> None:
    op.drop_column("users", "onboarding_complete")

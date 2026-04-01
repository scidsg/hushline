"""add user cautious flag

Revision ID: c4f8e2a1b6d9
Revises: 1a2b3c4d5e6a
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c4f8e2a1b6d9"
down_revision = "1a2b3c4d5e6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_cautious",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_cautious")

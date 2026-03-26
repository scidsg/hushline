"""add user suspended flag

Revision ID: 84f1d3b2c6e7
Revises: c4f8e2a1b6d9
Create Date: 2026-03-26 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "84f1d3b2c6e7"
down_revision = "c4f8e2a1b6d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_suspended",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("is_suspended")

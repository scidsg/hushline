"""add featured usernames

Revision ID: e3b7c1a9d2f4
Revises: b2039e7c0a1d
Create Date: 2026-05-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e3b7c1a9d2f4"
down_revision = "b2039e7c0a1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_featured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.drop_column("is_featured")

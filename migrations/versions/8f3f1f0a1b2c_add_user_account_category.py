"""add user account category

Revision ID: 8f3f1f0a1b2c
Revises: 3c1b2a4d5e6f
Create Date: 2026-03-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "8f3f1f0a1b2c"
down_revision = "3c1b2a4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("account_category", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("account_category")

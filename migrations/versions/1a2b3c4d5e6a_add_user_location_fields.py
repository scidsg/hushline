"""add user location fields

Revision ID: 1a2b3c4d5e6a
Revises: 8f3f1f0a1b2c
Create Date: 2026-03-16 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6a"
down_revision = "8f3f1f0a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("country", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("city", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("subdivision", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("subdivision")
        batch_op.drop_column("city")
        batch_op.drop_column("country")

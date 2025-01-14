"""add profile_header to usernames

Revision ID: 0a6cdf5c62f8
Revises: cf2a880aff10
Create Date: 2025-01-14 15:08:02.855886

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0a6cdf5c62f8"
down_revision = "cf2a880aff10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profile_header", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.drop_column("profile_header")

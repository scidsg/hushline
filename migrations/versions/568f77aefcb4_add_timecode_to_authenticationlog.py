"""add timecode to AuthenticationLog

Revision ID: 568f77aefcb4
Revises: ff59dfd3bdf6
Create Date: 2024-06-25 20:44:02.614282

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "568f77aefcb4"
down_revision = "ff59dfd3bdf6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("authentication_logs", sa.Column("timecode", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("authentication_logs", "timecode")

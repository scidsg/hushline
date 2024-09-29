"""add host_organization table

Revision ID: 5410668e15ad
Revises: 5ffe5a5c8e9a
Create Date: 2024-09-28 09:38:02.716771

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5410668e15ad"
down_revision = "5ffe5a5c8e9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_organization",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_app_name", sa.String(length=255), nullable=False),
        sa.Column("brand_primary_hex_color", sa.String(length=7), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_host_organization")),
    )


def downgrade() -> None:
    op.drop_table("host_organization")

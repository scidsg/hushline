"""create tiers table and add default tiers

Revision ID: 677fc6ba8fba
Revises: 62551ed63cbf
Create Date: 2024-09-03 09:40:51.321787

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "677fc6ba8fba"
down_revision = "62551ed63cbf"
branch_labels = None
depends_on = None


def upgrade():
    # Create the tiers table
    op.create_table(
        "tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("monthly_amount", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Add the default tiers
    # Business tier is $20/month or $192/year (20% discount)
    tiers_table = sa.table(
        "tiers",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("monthly_amount", sa.Integer),
    )
    op.bulk_insert(
        tiers_table,
        [
            {"id": 1, "name": "Free", "monthly_amount": 0},
            {"id": 2, "name": "Business", "monthly_amount": 2000},
        ],
    )

    # Add the tier_id column to the users table
    # The default tier is the free tier
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tier_id", sa.Integer(), nullable=False, default=1))
        batch_op.create_foreign_key("fk_users_tiers", "tiers", ["tier_id"], ["id"])


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("fk_users_tiers", type_="foreignkey")
        batch_op.drop_column("tier_id")

    op.drop_table("tiers")

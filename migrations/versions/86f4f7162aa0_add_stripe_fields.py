"""add stripe fields

Revision ID: 86f4f7162aa0
Revises: 677fc6ba8fba
Create Date: 2024-09-04 11:44:00.721173

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "86f4f7162aa0"
down_revision = "677fc6ba8fba"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("tiers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_product_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("stripe_price_id", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("tiers_stripe_product_id", ["stripe_product_id"])
        batch_op.create_unique_constraint("tiers_stripe_price_id", ["stripe_price_id"])

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")

    with op.batch_alter_table("tiers", schema=None) as batch_op:
        batch_op.drop_constraint("tiers_stripe_product_id", type_="unique")
        batch_op.drop_constraint("tiers_stripe_price_id", type_="unique")
        batch_op.drop_column("stripe_price_id")
        batch_op.drop_column("stripe_product_id")

    # ### end Alembic commands ###
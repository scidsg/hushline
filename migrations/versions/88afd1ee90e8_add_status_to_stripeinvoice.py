"""add status to StripeInvoice

Revision ID: 88afd1ee90e8
Revises: 4159b05e9d23
Create Date: 2024-09-16 19:25:12.169033

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "88afd1ee90e8"
down_revision = "4159b05e9d23"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stripe_invoices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(),
                nullable=True,
            )
        )


def downgrade():
    with op.batch_alter_table("stripe_invoices", schema=None) as batch_op:
        batch_op.drop_column("status")

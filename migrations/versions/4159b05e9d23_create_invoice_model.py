"""create Invoice model

Revision ID: 4159b05e9d23
Revises: 5c4788eea43e
Create Date: 2024-09-11 14:24:27.544744

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4159b05e9d23"
down_revision = "5c4788eea43e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stripe_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(length=255), nullable=False),
        sa.Column("invoice_id", sa.String(length=255), nullable=False),
        sa.Column("hosted_invoice_url", sa.String(length=255), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False),
        sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("amount_remaining", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tier_id"],
            ["tiers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id"),
    )
    with op.batch_alter_table("stripe_invoices", schema=None) as batch_op:
        batch_op.create_index("idx_stripe_invoices_invoice_id", ["invoice_id"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index("idx_users_stripe_customer_id", ["stripe_customer_id"], unique=False)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("idx_users_stripe_customer_id")

    with op.batch_alter_table("stripe_invoices", schema=None) as batch_op:
        batch_op.drop_index("idx_stripe_invoices_invoice_id")

    op.drop_table("stripe_invoices")

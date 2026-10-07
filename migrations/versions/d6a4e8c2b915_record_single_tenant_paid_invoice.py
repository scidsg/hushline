"""Retain the independently verified invoice for the paid annual term.

Revision ID: d6a4e8c2b915
Revises: c7d3e9a1b820
"""

from alembic import op
import sqlalchemy as sa

revision = "d6a4e8c2b915"
down_revision = "c7d3e9a1b820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "single_tenant_orders", sa.Column("stripe_invoice_id", sa.String(255), nullable=True)
    )
    op.create_unique_constraint(
        "uq_single_tenant_orders_stripe_invoice_id", "single_tenant_orders", ["stripe_invoice_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_single_tenant_orders_stripe_invoice_id", "single_tenant_orders", type_="unique"
    )
    op.drop_column("single_tenant_orders", "stripe_invoice_id")

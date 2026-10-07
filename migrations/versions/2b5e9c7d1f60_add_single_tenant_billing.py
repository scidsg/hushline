"""Retain independent annual billing evidence without altering premium users.

Revision ID: 2b5e9c7d1f60
Revises: 8c6f1e2a9b04
"""

from alembic import op
import sqlalchemy as sa

revision = "2b5e9c7d1f60"
down_revision = "8c6f1e2a9b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, length in (
        ("period_start", 40),
        ("cancelled_at", 40),
        ("billing_receipt", 32),
        ("stripe_session_id", 255),
        ("stripe_subscription_id", 255),
        ("stripe_customer_id", 255),
    ):
        op.add_column("single_tenant_orders", sa.Column(name, sa.String(length)))
    op.add_column(
        "single_tenant_orders",
        sa.Column("billing_sync_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for name in ("billing_receipt", "stripe_session_id", "stripe_subscription_id"):
        op.create_unique_constraint("uq_single_tenant_" + name, "single_tenant_orders", [name])


def downgrade() -> None:
    for name in ("billing_receipt", "stripe_session_id", "stripe_subscription_id"):
        op.drop_constraint("uq_single_tenant_" + name, "single_tenant_orders", type_="unique")
    for name in (
        "billing_sync_pending",
        "stripe_customer_id",
        "stripe_subscription_id",
        "stripe_session_id",
        "billing_receipt",
        "cancelled_at",
        "period_start",
    ):
        op.drop_column("single_tenant_orders", name)

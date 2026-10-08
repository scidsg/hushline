"""Retain immediate destruction intent across failures and account deletion."""

from alembic import op
import sqlalchemy as sa

revision = "e8b7a2d9c410"
down_revision = "d6a4e8c2b915"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "single_tenant_orders", sa.Column("stripe_free_coupon_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "single_tenant_orders", sa.Column("destroy_requested_at", sa.String(40), nullable=True)
    )
    op.add_column(
        "single_tenant_orders",
        sa.Column("destruction_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("single_tenant_orders", "stripe_free_coupon_id")
    op.drop_column("single_tenant_orders", "destruction_pending")
    op.drop_column("single_tenant_orders", "destroy_requested_at")

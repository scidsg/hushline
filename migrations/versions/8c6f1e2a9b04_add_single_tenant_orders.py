"""add durable single tenant ownership and cancellation intent

Revision ID: 8c6f1e2a9b04
Revises: 7a4c9e2f1b63
"""

from alembic import op
import sqlalchemy as sa

revision = "8c6f1e2a9b04"
down_revision = "7a4c9e2f1b63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "single_tenant_orders",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("owner_ref", sa.String(64), nullable=False),
        sa.Column("license_limit", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("service_state", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column("cancellation_pending", sa.Boolean(), nullable=False),
        sa.Column("period_end", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_ref"),
    )
    op.create_index(
        "ix_single_tenant_orders_user_id", "single_tenant_orders", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_single_tenant_orders_user_id", table_name="single_tenant_orders")
    op.drop_table("single_tenant_orders")

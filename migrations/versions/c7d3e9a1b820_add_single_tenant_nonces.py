"""Replay protection for authenticated billing-authority requests.

Revision ID: c7d3e9a1b820
Revises: 2b5e9c7d1f60
"""

from alembic import op
import sqlalchemy as sa

revision = "c7d3e9a1b820"
down_revision = "2b5e9c7d1f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "single_tenant_nonces",
        sa.Column("nonce", sa.String(32), primary_key=True),
        sa.Column("seen", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_single_tenant_nonces_seen", "single_tenant_nonces", ["seen"])


def downgrade() -> None:
    op.drop_index("ix_single_tenant_nonces_seen", table_name="single_tenant_nonces")
    op.drop_table("single_tenant_nonces")

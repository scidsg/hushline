"""rename index

Revision ID: 06b343c38386
Revises: 0b1321c8de13
Create Date: 2024-11-09 10:32:09.966628

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "06b343c38386"
down_revision = "0b1321c8de13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER INDEX idx_users_stripe_customer_id RENAME TO ix_users_stripe_customer_id")
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER INDEX ix_users_stripe_customer_id RENAME TO idx_users_stripe_customer_id")
    )

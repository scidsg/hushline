"""add Stripe tables

Revision ID: e3784181a957
Revises: c2b6eff6e213
Create Date: 2024-09-18 14:14:43.460228

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3784181a957"
down_revision = "c2b6eff6e213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("event_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column(
            "status",
            sa.Enum("PENDING", "IN_PROGRESS", "ERROR", "FINISHED", name="stripeeventstatusenum"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stripe_events_event_id"), ["event_id"], unique=True)

    op.create_table(
        "tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("monthly_amount", sa.Integer(), nullable=False),
        sa.Column("stripe_product_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("stripe_price_id"),
        sa.UniqueConstraint("stripe_product_id"),
    )
    op.create_table(
        "stripe_invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(length=255), nullable=False),
        sa.Column("invoice_id", sa.String(length=255), nullable=False),
        sa.Column("hosted_invoice_url", sa.String(length=2048), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "OPEN", "PAID", "UNCOLLECTIBLE", "VOID", name="stripeinvoicestatusenum"
            ),
            nullable=True,
        ),
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
    )
    with op.batch_alter_table("stripe_invoices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stripe_invoices_invoice_id"), ["invoice_id"], unique=True
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tier_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stripe_subscription_cancel_at_period_end", sa.Boolean, nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "stripe_subscription_status",
                sa.Enum(
                    "INCOMPLETE",
                    "INCOMPLETE_EXPIRED",
                    "TRIALING",
                    "ACTIVE",
                    "PAST_DUE",
                    "CANCELED",
                    "UNPAID",
                    "PAUSED",
                    name="stripesubscriptionstatusenum",
                ),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "stripe_subscription_current_period_end",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        batch_op.add_column(
            sa.Column(
                "stripe_subscription_current_period_start",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        batch_op.create_index("idx_users_stripe_customer_id", ["stripe_customer_id"], unique=False)
        batch_op.create_foreign_key("users_tier_id_fkey", "tiers", ["tier_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("users_tier_id_fkey", type_="foreignkey")
        batch_op.drop_index("idx_users_stripe_customer_id")
        batch_op.drop_column("stripe_subscription_current_period_start")
        batch_op.drop_column("stripe_subscription_current_period_end")
        batch_op.drop_column("stripe_subscription_status")
        batch_op.drop_column("stripe_subscription_cancel_at_period_end")
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("stripe_customer_id")
        batch_op.drop_column("tier_id")

    op.drop_table("stripe_invoices")
    op.drop_table("tiers")
    op.drop_table("stripe_events")

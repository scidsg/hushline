"""add stripe_events

Revision ID: 5c4788eea43e
Revises: 5c3fbcc6f32a
Create Date: 2024-09-11 13:56:55.831910

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c4788eea43e"
down_revision = "5c3fbcc6f32a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("event_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.create_index("idx_stripe_events_event_id", ["event_id"], unique=False)


def downgrade():
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.drop_index("idx_stripe_events_event_id")

    op.drop_table("stripe_events")

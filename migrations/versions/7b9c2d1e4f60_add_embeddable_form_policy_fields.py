"""add embeddable form policy fields

Revision ID: 7b9c2d1e4f60
Revises: 2d8a1f7c9b41
Create Date: 2026-05-04 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "7b9c2d1e4f60"
down_revision = "2d8a1f7c9b41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "embed_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "embed_admin_disabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "embed_allowed_origins",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("usernames", schema=None) as batch_op:
        batch_op.drop_column("embed_allowed_origins")
        batch_op.drop_column("embed_admin_disabled")
        batch_op.drop_column("embed_enabled")

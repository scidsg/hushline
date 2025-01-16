"""add FieldDefinition and FieldValue

Revision ID: 4a53667aff6e
Revises: cf2a880aff10
Create Date: 2025-01-16 23:24:40.316301

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "4a53667aff6e"
down_revision = "cf2a880aff10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_definitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username_id", sa.Integer, sa.ForeignKey("usernames.id")),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column(
            "field_type",
            sa.Enum("TEXT", "NUMBER", "DATE", "BOOLEAN", name="fieldtype"),
            default="TEXT",
        ),
        sa.Column("required", sa.Boolean, default=False),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("encrypted", sa.Boolean, default=False),
        sa.Column("choices", JSONB, default=[]),
        sa.Column("sort_order", sa.Integer, default=0),
    )

    op.create_table(
        "field_values",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("field_definition_id", sa.Integer, sa.ForeignKey("field_definitions.id")),
        sa.Column("message_id", sa.Integer, sa.ForeignKey("messages.id")),
        sa.Column("_value", sa.String(1024), nullable=False),
        sa.Column("encrypted", sa.Boolean, default=False),
    )


def downgrade() -> None:
    op.drop_table("field_values")
    op.drop_table("field_definitions")

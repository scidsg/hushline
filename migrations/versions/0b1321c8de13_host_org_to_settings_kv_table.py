"""host org to settings kv table

Revision ID: 0b1321c8de13
Revises: be0744a5679f
Create Date: 2024-11-01 11:24:16.572490

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0b1321c8de13"
down_revision = "be0744a5679f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_organization_settings")),
    )

    op.execute(
        sa.text(
            """
        INSERT INTO organization_settings (key, value)
        SELECT 'brand_name', to_jsonb(brand_app_name)
        FROM host_organization
        WHERE id = 1
        UNION ALL
        SELECT 'brand_primary_color', to_jsonb(brand_primary_hex_color)
        FROM host_organization
        WHERE id = 1
        """
        )
    )

    op.drop_table("host_organization")


def downgrade() -> None:
    op.create_table(
        "host_organization",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("brand_app_name", sa.VARCHAR(length=255), nullable=False),
        sa.Column("brand_primary_hex_color", sa.VARCHAR(length=7), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_host_organization"),
    )

    op.execute(
        sa.text(
            """
        INSERT INTO host_organization
        SELECT
            id,
            COALESCE(brand_app_name, '🤫 Hush Line'),
            COALESCE(brand_primary_hex_color, '#7d25c1')
        FROM (
            SELECT
                1 AS id, -- default id
                MAX(brand_app_name.value #>> '{}') AS brand_app_name,
                MAX(brand_primary_hex_color.value #>> '{}') AS brand_primary_hex_color
            FROM (SELECT null AS value) -- to guarantee with get both rows
            LEFT OUTER JOIN (
                SELECT value
                FROM organization_settings
                WHERE key = 'brand_name'
            ) AS brand_app_name
            ON TRUE
            LEFT OUTER JOIN (
                SELECT value
                FROM organization_settings
                WHERE key = 'brand_primary_color'
            ) AS brand_primary_hex_color
            ON TRUE
            GROUP BY 1
        ) AS x
        """
        )
    )

    op.drop_table("organization_settings")

"""fix field definition nullability and field value fk

Revision ID: 2e3e5b1f2b3c
Revises: 7d6a9f2f8c1a
Create Date: 2026-02-04 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2e3e5b1f2b3c"
down_revision = "7d6a9f2f8c1a"
branch_labels = None
depends_on = None


fieldtype_enum = sa.Enum(
    "TEXT",
    "MULTILINE_TEXT",
    "CHOICE_SINGLE",
    "CHOICE_MULTIPLE",
    name="fieldtype",
)


def upgrade() -> None:
    op.execute("UPDATE field_definitions SET field_type='TEXT' WHERE field_type IS NULL")
    op.execute("UPDATE field_definitions SET required=false WHERE required IS NULL")
    op.execute("UPDATE field_definitions SET enabled=true WHERE enabled IS NULL")
    op.execute("UPDATE field_definitions SET encrypted=false WHERE encrypted IS NULL")

    with op.batch_alter_table("field_definitions", schema=None) as batch_op:
        batch_op.alter_column(
            "field_type",
            existing_type=fieldtype_enum,
            nullable=False,
        )
        batch_op.alter_column("required", existing_type=sa.BOOLEAN(), nullable=False)
        batch_op.alter_column("enabled", existing_type=sa.BOOLEAN(), nullable=False)
        batch_op.alter_column("encrypted", existing_type=sa.BOOLEAN(), nullable=False)

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    fk_name = None
    for fk in inspector.get_foreign_keys("field_values"):
        if fk["referred_table"] == "field_definitions" and fk["constrained_columns"] == [
            "field_definition_id"
        ]:
            fk_name = fk["name"]
            break

    with op.batch_alter_table("field_values", schema=None) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        batch_op.create_foreign_key(
            None,
            "field_definitions",
            ["field_definition_id"],
            ["id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    fk_name = None
    for fk in inspector.get_foreign_keys("field_values"):
        if fk["referred_table"] == "field_definitions" and fk["constrained_columns"] == [
            "field_definition_id"
        ]:
            fk_name = fk["name"]
            break

    with op.batch_alter_table("field_values", schema=None) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        batch_op.create_foreign_key(
            None,
            "field_definitions",
            ["field_definition_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("field_definitions", schema=None) as batch_op:
        batch_op.alter_column(
            "field_type",
            existing_type=fieldtype_enum,
            nullable=True,
        )
        batch_op.alter_column("required", existing_type=sa.BOOLEAN(), nullable=True)
        batch_op.alter_column("enabled", existing_type=sa.BOOLEAN(), nullable=True)
        batch_op.alter_column("encrypted", existing_type=sa.BOOLEAN(), nullable=True)

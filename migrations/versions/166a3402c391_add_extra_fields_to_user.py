"""add extra fields to user

Revision ID: 166a3402c391
Revises: 6e53eac9ea14
Create Date: 2024-08-21 14:47:07.012516

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "166a3402c391"
down_revision = "6e53eac9ea14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("extra_field_label1", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_value1", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_label2", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_value2", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_label3", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_value3", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_label4", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("extra_field_value4", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("extra_field_value4")
        batch_op.drop_column("extra_field_label4")
        batch_op.drop_column("extra_field_value3")
        batch_op.drop_column("extra_field_label3")
        batch_op.drop_column("extra_field_value2")
        batch_op.drop_column("extra_field_label2")
        batch_op.drop_column("extra_field_value1")
        batch_op.drop_column("extra_field_label1")

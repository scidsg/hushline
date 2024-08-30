"""make boolean fields required

Revision ID: 62551ed63cbf
Revises: 166a3402c391
Create Date: 2024-08-30 09:51:53.990304

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '62551ed63cbf'
down_revision = '166a3402c391'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash',
               existing_type=sa.VARCHAR(length=512),
               nullable=False)
        batch_op.alter_column('is_verified',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('is_admin',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('show_in_directory',
               existing_type=sa.BOOLEAN(),
               nullable=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('show_in_directory',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('is_admin',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('is_verified',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('password_hash',
               existing_type=sa.VARCHAR(length=512),
               nullable=True)

    # ### end Alembic commands ###

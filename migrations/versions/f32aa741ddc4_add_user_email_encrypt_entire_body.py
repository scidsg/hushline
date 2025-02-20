"""add user.email_encrypt_entire_body

Revision ID: f32aa741ddc4
Revises: 6071f1eea074
Create Date: 2025-02-20 00:38:43.927348

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f32aa741ddc4"
down_revision = "6071f1eea074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "email_encrypt_entire_body",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("email_encrypt_entire_body")

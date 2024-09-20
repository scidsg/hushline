"""smtp encryption protocol

Revision ID: 6e53eac9ea14
Revises: 568f77aefcb4
Create Date: 2024-08-14 16:49:11.025694

"""

from alembic import op
import sqlalchemy as sa

from hushline.model import SMTPEncryption


# revision identifiers, used by Alembic.
revision = "6e53eac9ea14"
down_revision = "568f77aefcb4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "smtp_encryption",
            sa.String(),
            nullable=False,
            server_default=SMTPEncryption.StartTLS.value,
        ),
    )
    op.add_column("users", sa.Column("smtp_sender", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "smtp_encryption")
    op.drop_column("users", "smtp_sender")

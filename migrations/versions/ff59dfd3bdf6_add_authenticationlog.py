"""add AuthenticationLog

Revision ID: ff59dfd3bdf6
Revises: 691dba936e64
Create Date: 2024-06-21 10:24:59.976327

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "ff59dfd3bdf6"
down_revision = "691dba936e64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authentication_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("otp_code", sa.String(length=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("authentication_logs_user_id_fkey"),
        ),
        sa.Index(
            op.f("idx_authentication_logs_user_id_timestamp_successful"),
            *["user_id", "timestamp", "successful"],
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("authentication_logs_pkey")),
    )


def downgrade() -> None:
    op.drop_table("authentication_logs")

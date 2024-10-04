"""Initial migration

Revision ID: 691dba936e64
Revises:
Create Date: 2024-06-10 13:41:47.958407

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "691dba936e64"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("expiration_date", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("invite_code_pkey")),
        sa.UniqueConstraint("code", name=op.f("invite_code_code_key")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("primary_username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("smtp_server", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("smtp_password", sa.String(length=255), nullable=True),
        sa.Column("pgp_key", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("show_in_directory", sa.Boolean(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.UniqueConstraint("primary_username", name=op.f("users_primary_username_key")),
    )
    op.create_table(
        "secondary_usernames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("secondary_usernames_user_id_fkey"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("secondary_usernames_pkey")),
        sa.UniqueConstraint("username", name=op.f("secondary_usernames_username_key")),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("secondary_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["secondary_user_id"],
            ["secondary_usernames.id"],
            name=op.f("message_secondary_user_id_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("message_user_id_fkey"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("message_pkey")),
    )


def downgrade() -> None:
    op.drop_table("message")
    op.drop_table("secondary_usernames")
    op.drop_table("users")
    op.drop_table("invite_code")

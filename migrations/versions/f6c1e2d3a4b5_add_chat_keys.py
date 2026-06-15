"""add chat keys

Revision ID: f6c1e2d3a4b5
Revises: a9d8c7b6e5f4
Create Date: 2026-06-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6c1e2d3a4b5"
down_revision = "a9d8c7b6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("kdf_algorithm", sa.String(length=128), nullable=False),
        sa.Column("kdf_params", sa.JSON(), nullable=False),
        sa.Column("kdf_salt", sa.Text(), nullable=False),
        sa.Column("wrapping_algorithm", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_state", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_keys")),
        sa.UniqueConstraint("user_id", "key_version", name=op.f("uq_chat_keys_user_id")),
    )
    op.create_index(op.f("ix_chat_keys_user_id"), "chat_keys", ["user_id"], unique=False)
    op.create_index(
        "ix_chat_keys_user_id_disabled_at",
        "chat_keys",
        ["user_id", "disabled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_keys_user_id_disabled_at", table_name="chat_keys")
    op.drop_index(op.f("ix_chat_keys_user_id"), table_name="chat_keys")
    op.drop_table("chat_keys")

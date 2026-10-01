"""preserve encrypted chat history on account deletion

Revision ID: 7b4c9d2e1f60
Revises: 2a6f8c1d4e90
Create Date: 2026-09-30 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "7b4c9d2e1f60"
down_revision = "2a6f8c1d4e90"
branch_labels = None
depends_on = None


def _set_user_foreign_key(*, table: str, nullable: bool, ondelete: str) -> None:
    constraint = f"fk_{table}_user_id_users"
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.drop_constraint(constraint, type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=nullable)
        batch_op.create_foreign_key(
            constraint,
            "users",
            ["user_id"],
            ["id"],
            ondelete=ondelete,
        )


def upgrade() -> None:
    with op.batch_alter_table("chat_devices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("account_identity_public_key", sa.Text(), nullable=True))
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE chat_devices SET account_identity_public_key = "
            "chat_accounts.identity_public_key FROM chat_accounts "
            "WHERE chat_devices.account_id = chat_accounts.id"
        )
    )
    _set_user_foreign_key(table="conversation_participants", nullable=True, ondelete="SET NULL")


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM conversation_messages WHERE sender_participant_id IN "
            "(SELECT id FROM conversation_participants WHERE user_id IS NULL)"
        )
    )
    connection.execute(sa.text("DELETE FROM conversation_participants WHERE user_id IS NULL"))
    connection.execute(
        sa.text(
            "DELETE FROM conversations WHERE NOT EXISTS "
            "(SELECT 1 FROM conversation_participants "
            "WHERE conversation_participants.conversation_id = conversations.id)"
        )
    )
    _set_user_foreign_key(table="conversation_participants", nullable=False, ondelete="CASCADE")
    with op.batch_alter_table("chat_devices", schema=None) as batch_op:
        batch_op.drop_column("account_identity_public_key")

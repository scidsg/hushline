"""add conversation tables

Revision ID: a9d8c7b6e5f4
Revises: e3b7c1a9d2f4
Create Date: 2026-06-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a9d8c7b6e5f4"
down_revision = "e3b7c1a9d2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_table(
        "conversation_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "has_usable_public_key",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_participants_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversation_participants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_participants")),
        sa.UniqueConstraint(
            "conversation_id",
            "user_id",
            name=op.f("uq_conversation_participants_conversation_id"),
        ),
    )
    op.create_index(
        op.f("ix_conversation_participants_conversation_id"),
        "conversation_participants",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_participants_user_id"),
        "conversation_participants",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_participants_user_id_conversation_id",
        "conversation_participants",
        ["user_id", "conversation_id"],
        unique=False,
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sender_participant_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_participant_id"],
            ["conversation_participants.id"],
            name=op.f("fk_conversation_messages_sender_participant_id_conversation_participants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_messages")),
    )
    op.create_index(
        op.f("ix_conversation_messages_conversation_id"),
        "conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_messages_conversation_id_created_at",
        "conversation_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_sender_participant_id"),
        "conversation_messages",
        ["sender_participant_id"],
        unique=False,
    )
    op.create_table(
        "conversation_message_copies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_message_id", sa.Integer(), nullable=False),
        sa.Column("recipient_participant_id", sa.Integer(), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_message_id"],
            ["conversation_messages.id"],
            name=op.f(
                "fk_conversation_message_copies_conversation_message_id_conversation_messages"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_participant_id"],
            ["conversation_participants.id"],
            name=op.f(
                "fk_conversation_message_copies_recipient_participant_id_conversation_participants"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_message_copies")),
        sa.UniqueConstraint(
            "conversation_message_id",
            "recipient_participant_id",
            name=op.f("uq_conversation_message_copies_conversation_message_id"),
        ),
    )
    op.create_index(
        op.f("ix_conversation_message_copies_conversation_message_id"),
        "conversation_message_copies",
        ["conversation_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_message_copies_participant_message",
        "conversation_message_copies",
        ["recipient_participant_id", "conversation_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_message_copies_recipient_participant_id"),
        "conversation_message_copies",
        ["recipient_participant_id"],
        unique=False,
    )

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_messages_conversation_id_conversations"),
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_messages_conversation_id"),
            ["conversation_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_messages_conversation_id"), type_="unique")
        batch_op.drop_constraint(
            batch_op.f("fk_messages_conversation_id_conversations"),
            type_="foreignkey",
        )
        batch_op.drop_column("conversation_id")

    op.drop_index(
        op.f("ix_conversation_message_copies_recipient_participant_id"),
        table_name="conversation_message_copies",
    )
    op.drop_index(
        "ix_conversation_message_copies_participant_message",
        table_name="conversation_message_copies",
    )
    op.drop_index(
        op.f("ix_conversation_message_copies_conversation_message_id"),
        table_name="conversation_message_copies",
    )
    op.drop_table("conversation_message_copies")
    op.drop_index(
        op.f("ix_conversation_messages_sender_participant_id"),
        table_name="conversation_messages",
    )
    op.drop_index(
        "ix_conversation_messages_conversation_id_created_at",
        table_name="conversation_messages",
    )
    op.drop_index(
        op.f("ix_conversation_messages_conversation_id"),
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index(
        "ix_conversation_participants_user_id_conversation_id",
        table_name="conversation_participants",
    )
    op.drop_index(
        op.f("ix_conversation_participants_user_id"),
        table_name="conversation_participants",
    )
    op.drop_index(
        op.f("ix_conversation_participants_conversation_id"),
        table_name="conversation_participants",
    )
    op.drop_table("conversation_participants")
    op.drop_table("conversations")

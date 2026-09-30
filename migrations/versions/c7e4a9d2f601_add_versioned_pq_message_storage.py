"""add versioned post-quantum message storage

Revision ID: c7e4a9d2f601
Revises: 9c8f0a1d2b3c
Create Date: 2026-09-29 00:00:00.000000

"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "c7e4a9d2f601"
down_revision = "9c8f0a1d2b3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("identity_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "membership_sequence", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("identity_public_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_accounts")),
        sa.CheckConstraint("identity_version >= 0", name=op.f("ck_chat_accounts_identity_version")),
        sa.CheckConstraint(
            "membership_sequence >= 0", name=op.f("ck_chat_accounts_membership_sequence")
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_chat_accounts_public_id")),
        sa.UniqueConstraint("user_id", name=op.f("uq_chat_accounts_user_id")),
    )
    op.create_index(op.f("ix_chat_accounts_public_id"), "chat_accounts", ["public_id"], unique=True)
    op.create_index(op.f("ix_chat_accounts_user_id"), "chat_accounts", ["user_id"], unique=True)

    connection = op.get_bind()
    user_ids = connection.execute(sa.text("SELECT id FROM users ORDER BY id")).scalars()
    for user_id in user_ids:
        connection.execute(
            sa.text("INSERT INTO chat_accounts (user_id, public_id) VALUES (:user_id, :public_id)"),
            {"user_id": user_id, "public_id": str(uuid4())},
        )

    op.create_table(
        "chat_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("session_id_hash", sa.String(length=64), nullable=False),
        sa.Column("membership_sequence", sa.BigInteger(), nullable=False),
        sa.Column("key_version", sa.BigInteger(), nullable=False),
        sa.Column("membership_sha256", sa.String(length=64), nullable=False),
        sa.Column("signing_public_key", sa.Text(), nullable=False),
        sa.Column("protocol_identity_public_key", sa.Text(), nullable=False),
        sa.Column("membership", sa.JSON(), nullable=False),
        sa.Column("membership_signature", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["chat_accounts.id"],
            name=op.f("fk_chat_devices_account_id_chat_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_devices")),
        sa.CheckConstraint(
            "membership_sequence > 0", name=op.f("ck_chat_devices_membership_sequence")
        ),
        sa.CheckConstraint("key_version > 0", name=op.f("ck_chat_devices_key_version")),
        sa.UniqueConstraint("account_id", "public_id", name=op.f("uq_chat_devices_account_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_chat_devices_public_id")),
    )
    op.create_index(
        op.f("ix_chat_devices_account_id"),
        "chat_devices",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_devices_account_active",
        "chat_devices",
        ["account_id", "revoked_at", "expires_at"],
        unique=False,
    )

    op.create_table(
        "chat_archive_epochs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["chat_accounts.id"],
            name=op.f("fk_chat_archive_epochs_account_id_chat_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_archive_epochs")),
        sa.CheckConstraint("epoch > 0", name=op.f("ck_chat_archive_epochs_epoch")),
        sa.UniqueConstraint("account_id", "epoch", name=op.f("uq_chat_archive_epochs_account_id")),
    )
    op.create_index(
        op.f("ix_chat_archive_epochs_account_id"),
        "chat_archive_epochs",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_archive_epochs_account_active",
        "chat_archive_epochs",
        ["account_id", "retired_at"],
        unique=False,
    )
    op.create_index(
        "uq_chat_archive_epochs_account_current",
        "chat_archive_epochs",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "minimum_protocol_version",
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("version", sa.BigInteger(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_conversations_minimum_protocol_version"),
            "minimum_protocol_version >= 0",
        )
        batch_op.create_check_constraint(batch_op.f("ck_conversations_version"), "version >= 0")

    with op.batch_alter_table("conversation_messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("protocol_version", sa.Integer(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.add_column(sa.Column("conversation_version", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("request_sha256", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("manifest", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("manifest_signature", sa.Text(), nullable=True))

    message_ids = connection.execute(
        sa.text("SELECT id FROM conversation_messages ORDER BY id")
    ).scalars()
    for message_id in message_ids:
        connection.execute(
            sa.text("UPDATE conversation_messages SET public_id = :public_id WHERE id = :id"),
            {"id": message_id, "public_id": str(uuid4())},
        )

    with op.batch_alter_table("conversation_messages", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint(op.f("uq_conversation_messages_public_id"), ["public_id"])
        batch_op.create_unique_constraint(
            op.f("uq_conversation_messages_idempotency_key"), ["idempotency_key"]
        )
        batch_op.create_unique_constraint(
            op.f("uq_conversation_messages_conversation_id"),
            ["conversation_id", "conversation_version"],
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_conversation_messages_protocol_version"),
            "protocol_version >= 0",
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_conversation_messages_conversation_version"),
            "conversation_version IS NULL OR conversation_version > 0",
        )
        batch_op.create_index(
            op.f("ix_conversation_messages_public_id"), ["public_id"], unique=True
        )
        batch_op.create_index(
            op.f("ix_conversation_messages_idempotency_key"), ["idempotency_key"], unique=True
        )

    op.create_table(
        "conversation_message_transport_copies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_message_id", sa.Integer(), nullable=False),
        sa.Column("recipient_participant_id", sa.Integer(), nullable=False),
        sa.Column("recipient_device_id", sa.Integer(), nullable=False),
        sa.Column("key_version", sa.BigInteger(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("context_sha256", sa.String(length=64), nullable=False),
        sa.Column("ciphertext_sha256", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_message_id"],
            ["conversation_messages.id"],
            name=op.f(
                "fk_conversation_message_transport_copies_"
                "conversation_message_id_conversation_messages"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_participant_id"],
            ["conversation_participants.id"],
            name=op.f(
                "fk_conversation_message_transport_copies_"
                "recipient_participant_id_conversation_participants"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_device_id"],
            ["chat_devices.id"],
            name=op.f("fk_conversation_message_transport_copies_recipient_device_id_chat_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_message_transport_copies")),
        sa.UniqueConstraint(
            "conversation_message_id",
            "recipient_device_id",
            name=op.f("uq_conversation_message_transport_copies_conversation_message_id"),
        ),
    )
    for columns, name in (
        (
            ["conversation_message_id"],
            op.f("ix_conversation_message_transport_copies_conversation_message_id"),
        ),
        (
            ["recipient_participant_id"],
            op.f("ix_conversation_message_transport_copies_recipient_participant_id"),
        ),
        (
            ["recipient_device_id"],
            op.f("ix_conversation_message_transport_copies_recipient_device_id"),
        ),
        (
            ["recipient_participant_id", "conversation_message_id"],
            "ix_conversation_transport_copies_participant_message",
        ),
    ):
        op.create_index(name, "conversation_message_transport_copies", columns, unique=False)

    op.create_table(
        "conversation_message_archive_copies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_message_id", sa.Integer(), nullable=False),
        sa.Column("recipient_participant_id", sa.Integer(), nullable=False),
        sa.Column("archive_epoch_id", sa.Integer(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("context_sha256", sa.String(length=64), nullable=False),
        sa.Column("ciphertext_sha256", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_message_id"],
            ["conversation_messages.id"],
            name=op.f(
                "fk_conversation_message_archive_copies_"
                "conversation_message_id_conversation_messages"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_participant_id"],
            ["conversation_participants.id"],
            name=op.f(
                "fk_conversation_message_archive_copies_"
                "recipient_participant_id_conversation_participants"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["archive_epoch_id"],
            ["chat_archive_epochs.id"],
            name=op.f(
                "fk_conversation_message_archive_copies_" "archive_epoch_id_chat_archive_epochs"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_message_archive_copies")),
        sa.UniqueConstraint(
            "conversation_message_id",
            "recipient_participant_id",
            name=op.f("uq_conversation_message_archive_copies_conversation_message_id"),
        ),
    )
    for columns, name in (
        (
            ["conversation_message_id"],
            op.f("ix_conversation_message_archive_copies_conversation_message_id"),
        ),
        (
            ["recipient_participant_id"],
            op.f("ix_conversation_message_archive_copies_recipient_participant_id"),
        ),
        (["archive_epoch_id"], op.f("ix_conversation_message_archive_copies_archive_epoch_id")),
        (
            ["recipient_participant_id", "conversation_message_id"],
            "ix_conversation_archive_copies_participant_message",
        ),
    ):
        op.create_index(name, "conversation_message_archive_copies", columns, unique=False)


def downgrade() -> None:
    protected_count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM conversation_messages WHERE protocol_version > 0"))
        .scalar_one()
    )
    if protected_count:
        raise RuntimeError(
            "Cannot downgrade versioned message storage after protected traffic exists; "
            "retain an HL-PQCHAT-1-capable reader and disable writes instead."
        )

    op.drop_table("conversation_message_archive_copies")
    op.drop_table("conversation_message_transport_copies")
    with op.batch_alter_table("conversation_messages", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_conversation_messages_idempotency_key"))
        batch_op.drop_index(op.f("ix_conversation_messages_public_id"))
        batch_op.drop_constraint(op.f("uq_conversation_messages_idempotency_key"), type_="unique")
        batch_op.drop_constraint(op.f("uq_conversation_messages_public_id"), type_="unique")
        batch_op.drop_constraint(op.f("uq_conversation_messages_conversation_id"), type_="unique")
        batch_op.drop_constraint(
            batch_op.f("ck_conversation_messages_conversation_version"), type_="check"
        )
        batch_op.drop_constraint(
            batch_op.f("ck_conversation_messages_protocol_version"), type_="check"
        )
        batch_op.drop_column("manifest_signature")
        batch_op.drop_column("manifest")
        batch_op.drop_column("request_sha256")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("conversation_version")
        batch_op.drop_column("protocol_version")
        batch_op.drop_column("public_id")
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_conversations_version"), type_="check")
        batch_op.drop_constraint(
            batch_op.f("ck_conversations_minimum_protocol_version"), type_="check"
        )
        batch_op.drop_column("version")
        batch_op.drop_column("minimum_protocol_version")
    op.drop_table("chat_archive_epochs")
    op.drop_table("chat_devices")
    op.drop_table("chat_accounts")

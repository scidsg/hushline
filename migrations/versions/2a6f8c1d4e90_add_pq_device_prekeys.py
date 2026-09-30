"""add authenticated PQ device prekeys

Revision ID: 2a6f8c1d4e90
Revises: c7e4a9d2f601
Create Date: 2026-09-29 23:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "2a6f8c1d4e90"
down_revision = "c7e4a9d2f601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_signed_prekeys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.BigInteger(), nullable=False),
        sa.Column("membership_sequence", sa.BigInteger(), nullable=False),
        sa.Column("classical_public_key", sa.Text(), nullable=False),
        sa.Column("classical_signature", sa.Text(), nullable=False),
        sa.Column("pq_public_key", sa.Text(), nullable=False),
        sa.Column("pq_signature", sa.Text(), nullable=False),
        sa.Column("publication_sha256", sa.String(length=64), nullable=False),
        sa.Column("publication_signature", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("key_id > 0", name=op.f("ck_chat_signed_prekeys_key_id")),
        sa.CheckConstraint(
            "membership_sequence > 0",
            name=op.f("ck_chat_signed_prekeys_membership_sequence"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["chat_devices.id"],
            name=op.f("fk_chat_signed_prekeys_device_id_chat_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_signed_prekeys")),
        sa.UniqueConstraint("device_id", "key_id", name=op.f("uq_chat_signed_prekeys_device_id")),
    )
    op.create_index(
        op.f("ix_chat_signed_prekeys_device_id"),
        "chat_signed_prekeys",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_signed_prekeys_device_active",
        "chat_signed_prekeys",
        ["device_id", "retired_at", "expires_at"],
        unique=False,
    )

    op.create_table(
        "chat_one_time_prekeys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("key_id", sa.BigInteger(), nullable=False),
        sa.Column("membership_sequence", sa.BigInteger(), nullable=False),
        sa.Column("classical_public_key", sa.Text(), nullable=False),
        sa.Column("pq_public_key", sa.Text(), nullable=False),
        sa.Column("pq_signature", sa.Text(), nullable=False),
        sa.Column("publication_signature", sa.Text(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tombstone_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("key_id > 0", name=op.f("ck_chat_one_time_prekeys_key_id")),
        sa.CheckConstraint(
            "membership_sequence > 0",
            name=op.f("ck_chat_one_time_prekeys_membership_sequence"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["chat_devices.id"],
            name=op.f("fk_chat_one_time_prekeys_device_id_chat_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_one_time_prekeys")),
        sa.UniqueConstraint("device_id", "key_id", name=op.f("uq_chat_one_time_prekeys_device_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_chat_one_time_prekeys_public_id")),
    )
    op.create_index(
        op.f("ix_chat_one_time_prekeys_device_id"),
        "chat_one_time_prekeys",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_one_time_prekeys_claimable",
        "chat_one_time_prekeys",
        ["device_id", "consumed_at", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_one_time_prekeys_tombstone",
        "chat_one_time_prekeys",
        ["tombstone_expires_at"],
        unique=False,
    )

    op.create_table(
        "chat_prekey_claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("prekey_id", sa.Integer(), nullable=False),
        sa.Column("claimed_by_device_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tombstone_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["claimed_by_device_id"],
            ["chat_devices.id"],
            name=op.f("fk_chat_prekey_claims_claimed_by_device_id_chat_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prekey_id"],
            ["chat_one_time_prekeys.id"],
            name=op.f("fk_chat_prekey_claims_prekey_id_chat_one_time_prekeys"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_prekey_claims")),
        sa.UniqueConstraint("claim_id", name=op.f("uq_chat_prekey_claims_claim_id")),
    )
    op.create_index(
        op.f("ix_chat_prekey_claims_prekey_id"),
        "chat_prekey_claims",
        ["prekey_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_prekey_claims_claimed_by_device_id"),
        "chat_prekey_claims",
        ["claimed_by_device_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_prekey_claims_prekey_active",
        "chat_prekey_claims",
        ["prekey_id", "reservation_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_prekey_claims_tombstone",
        "chat_prekey_claims",
        ["tombstone_expires_at"],
        unique=False,
    )

    op.create_table(
        "chat_pq_rate_limit_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_pq_rate_limit_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_pq_rate_limit_attempts")),
    )
    op.create_index(
        op.f("ix_chat_pq_rate_limit_attempts_user_id"),
        "chat_pq_rate_limit_attempts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_pq_rate_limit_user_action_created",
        "chat_pq_rate_limit_attempts",
        ["user_id", "action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_pq_rate_limit_created",
        "chat_pq_rate_limit_attempts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    prekey_count = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM chat_signed_prekeys) "
                "+ (SELECT count(*) FROM chat_one_time_prekeys) "
                "+ (SELECT count(*) FROM chat_prekey_claims)"
            )
        )
        .scalar_one()
    )
    if prekey_count:
        raise RuntimeError(
            "Cannot downgrade authenticated device prekeys while published or consumed "
            "prekey records exist."
        )
    op.drop_table("chat_pq_rate_limit_attempts")
    op.drop_table("chat_prekey_claims")
    op.drop_table("chat_one_time_prekeys")
    op.drop_table("chat_signed_prekeys")

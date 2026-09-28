"""add WebAuthn credential and challenge storage

Revision ID: 3f6e8a1c2d4b
Revises: 9c8f0a1d2b3c
Create Date: 2026-09-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3f6e8a1c2d4b"
down_revision = "9c8f0a1d2b3c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webauthn_user_handles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("handle", sa.LargeBinary(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(handle) = 64",
            name="ck_webauthn_user_handles_handle_length",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webauthn_user_handles_handle",
        "webauthn_user_handles",
        ["handle"],
        unique=True,
    )
    op.create_index(
        "ix_webauthn_user_handles_user_id",
        "webauthn_user_handles",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(length=1024), nullable=False),
        sa.Column("public_key", sa.LargeBinary(length=4096), nullable=False),
        sa.Column("algorithm", sa.Integer(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=False),
        sa.Column("device_type", sa.String(length=32), nullable=False),
        sa.Column("backed_up", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "algorithm IN (-8, -7, -257)",
            name="ck_webauthn_credentials_algorithm",
        ),
        sa.CheckConstraint(
            "octet_length(credential_id) BETWEEN 1 AND 1024",
            name="ck_webauthn_credentials_id_length",
        ),
        sa.CheckConstraint(
            "octet_length(public_key) BETWEEN 1 AND 4096",
            name="ck_webauthn_credentials_public_key_length",
        ),
        sa.CheckConstraint("sign_count >= 0", name="ck_webauthn_credentials_sign_count"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webauthn_credentials_credential_id",
        "webauthn_credentials",
        ["credential_id"],
        unique=True,
    )
    op.create_index(
        "ix_webauthn_credentials_user_active",
        "webauthn_credentials",
        ["user_id", "disabled_at"],
        unique=False,
    )
    op.create_index(
        "ix_webauthn_credentials_user_id",
        "webauthn_credentials",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("challenge_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("session_binding_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(challenge_hash) = 32",
            name="ck_webauthn_challenges_challenge_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_webauthn_challenges_expiry",
        ),
        sa.CheckConstraint(
            "purpose IN ('registration', 'authentication', 'recovery')",
            name="ck_webauthn_challenges_purpose",
        ),
        sa.CheckConstraint(
            "octet_length(session_binding_hash) = 32",
            name="ck_webauthn_challenges_session_hash_length",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webauthn_challenges_account_purpose_created",
        "webauthn_challenges",
        ["user_id", "purpose", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_webauthn_challenges_challenge_hash",
        "webauthn_challenges",
        ["challenge_hash"],
        unique=True,
    )
    op.create_index(
        "ix_webauthn_challenges_session_purpose_created",
        "webauthn_challenges",
        ["session_binding_hash", "purpose", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_webauthn_challenges_user_id",
        "webauthn_challenges",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_user_id", table_name="webauthn_challenges")
    op.drop_index(
        "ix_webauthn_challenges_session_purpose_created",
        table_name="webauthn_challenges",
    )
    op.drop_index(
        "ix_webauthn_challenges_challenge_hash",
        table_name="webauthn_challenges",
    )
    op.drop_index(
        "ix_webauthn_challenges_account_purpose_created",
        table_name="webauthn_challenges",
    )
    op.drop_table("webauthn_challenges")

    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_index(
        "ix_webauthn_credentials_user_active",
        table_name="webauthn_credentials",
    )
    op.drop_index(
        "ix_webauthn_credentials_credential_id",
        table_name="webauthn_credentials",
    )
    op.drop_table("webauthn_credentials")

    op.drop_index("ix_webauthn_user_handles_user_id", table_name="webauthn_user_handles")
    op.drop_index("ix_webauthn_user_handles_handle", table_name="webauthn_user_handles")
    op.drop_table("webauthn_user_handles")

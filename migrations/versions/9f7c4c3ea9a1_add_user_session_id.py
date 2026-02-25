"""add user session_id

Revision ID: 9f7c4c3ea9a1
Revises: 2e3e5b1f2b3c
Create Date: 2026-02-25 00:00:00.000000

"""

import secrets

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "9f7c4c3ea9a1"
down_revision = "2e3e5b1f2b3c"
branch_labels = None
depends_on = None


def _new_session_id() -> str:
    return secrets.token_urlsafe(48)


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    user_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM users"))]
    for user_id in user_ids:
        conn.execute(
            sa.text("UPDATE users SET session_id = :session_id WHERE id = :user_id"),
            {"session_id": _new_session_id(), "user_id": user_id},
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("session_id", existing_type=sa.String(length=255), nullable=False)
        batch_op.create_index("ix_users_session_id", ["session_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_session_id")
        batch_op.drop_column("session_id")

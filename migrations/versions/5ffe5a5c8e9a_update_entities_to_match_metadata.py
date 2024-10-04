"""update entities to match metadata

Revision ID: 5ffe5a5c8e9a
Revises: 46aedec8fd9b
Create Date: 2024-09-20 17:09:10.819963

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5ffe5a5c8e9a"
down_revision = "46aedec8fd9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER INDEX invite_code_code_key RENAME TO uq_invite_codes_code"))
    op.execute(sa.text("ALTER INDEX usernames_username_key RENAME TO uq_usernames_username"))
    op.execute(sa.text("ALTER TABLE invite_code RENAME TO invite_codes"))
    op.execute(sa.text("ALTER TABLE message RENAME TO messages"))


def downgrade() -> None:
    op.execute(sa.text("ALTER INDEX uq_usernames_username RENAME TO usernames_username_key"))
    op.execute(sa.text("ALTER TABLE messages RENAME TO message"))
    op.execute(sa.text("ALTER TABLE invite_codes RENAME TO invite_code"))
    op.execute(sa.text("ALTER INDEX uq_invite_codes_code RENAME TO invite_code_code_key"))

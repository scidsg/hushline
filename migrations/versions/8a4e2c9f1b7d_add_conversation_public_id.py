"""add conversation public id

Revision ID: 8a4e2c9f1b7d
Revises: 5c7a9b1d3e8f
Create Date: 2026-06-15 00:00:00.000000

"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = "8a4e2c9f1b7d"
down_revision = "5c7a9b1d3e8f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))

    session = Session(op.get_bind())
    for row in session.execute(sa.text("SELECT id FROM conversations")).fetchall():
        session.execute(
            sa.text("UPDATE conversations SET public_id = :public_id WHERE id = :id"),
            {"id": row[0], "public_id": str(uuid4())},
        )
    session.commit()

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_conversations_public_id"), ["public_id"])


def downgrade() -> None:
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_conversations_public_id"), type_="unique")
        batch_op.drop_column("public_id")

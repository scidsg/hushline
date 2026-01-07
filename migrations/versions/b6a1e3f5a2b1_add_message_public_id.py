"""add message public id

Revision ID: b6a1e3f5a2b1
Revises: f32aa741ddc4
Create Date: 2025-02-14 00:00:00.000000

"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision = "b6a1e3f5a2b1"
down_revision = "f32aa741ddc4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))

    session = Session(op.get_bind())
    for row in session.execute(sa.text("SELECT id FROM messages")).fetchall():
        session.execute(
            sa.text("UPDATE messages SET public_id = :public_id WHERE id = :id"),
            {"id": row[0], "public_id": str(uuid4())},
        )
    session.commit()

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_messages_public_id"), ["public_id"])


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_messages_public_id"), type_="unique")
        batch_op.drop_column("public_id")

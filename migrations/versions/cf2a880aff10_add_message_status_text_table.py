"""add message status text table

Revision ID: cf2a880aff10
Revises: 06b343c38386
Create Date: 2024-11-27 20:11:30.154068

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from uuid import uuid4


# revision identifiers, used by Alembic.
revision = "cf2a880aff10"
down_revision = "06b343c38386"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_status_text",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "DECLINED", "ARCHIVED", name="messagestatus"),
            nullable=False,
        ),
        sa.Column("markdown", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_message_status_text_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_status_text")),
        sa.UniqueConstraint("user_id", "status", name=op.f("uq_message_status_text_user_id")),
    )

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("reply_slug", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum("PENDING", "ACCEPTED", "DECLINED", "ARCHIVED", name="messagestatus"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "status_changed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
                nullable=True,
            )
        )
        batch_op.create_index(batch_op.f("ix_messages_reply_slug"), ["reply_slug"], unique=False)

    op.execute(
        sa.text(
            """
        UPDATE messages SET
            created_at = '2000-01-01T00:00:00',
            status = 'PENDING',
            status_changed_at = '2000-01-01T00:00:00'
        """
        )
    )

    session = Session(op.get_bind())
    for row in session.execute(sa.text("SELECT id FROM messages")).fetchall():
        session.execute(
            sa.text("UPDATE messages SET reply_slug = :slug WHERE id = :id"),
            {"id": row[0], "slug": str(uuid4())},
        )
    session.commit()

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch_op.alter_column("reply_slug", existing_type=sa.String(), nullable=False)
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "PENDING", "ACCEPTED", "DECLINED", "ARCHIVED", name="messagestatus"
            ),
            nullable=False,
        )
        batch_op.alter_column(
            "status_changed_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_reply_slug"))
        batch_op.drop_column("status_changed_at")
        batch_op.drop_column("status")
        batch_op.drop_column("reply_slug")
        batch_op.drop_column("created_at")

    op.drop_table("message_status_text")

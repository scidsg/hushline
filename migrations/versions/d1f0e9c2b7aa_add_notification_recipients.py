"""add notification recipients

Revision ID: d1f0e9c2b7aa
Revises: 84f1d3b2c6e7
Create Date: 2026-04-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d1f0e9c2b7aa"
down_revision = "84f1d3b2c6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("pgp_key", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notification_recipients_user_id"),
        "notification_recipients",
        ["user_id"],
        unique=False,
    )

    conn = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("email", sa.String(length=255)),
        sa.column("pgp_key", sa.Text()),
    )
    recipients = sa.table(
        "notification_recipients",
        sa.column("user_id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("position", sa.Integer()),
        sa.column("email", sa.String(length=255)),
        sa.column("pgp_key", sa.Text()),
    )

    rows = conn.execute(sa.select(users.c.id, users.c.email, users.c.pgp_key)).mappings().all()
    for row in rows:
        if not row["email"] and not row["pgp_key"]:
            continue
        conn.execute(
            recipients.insert().values(
                user_id=row["id"],
                enabled=True,
                position=0,
                email=row["email"],
                pgp_key=row["pgp_key"],
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_recipients_user_id"), table_name="notification_recipients")
    op.drop_table("notification_recipients")

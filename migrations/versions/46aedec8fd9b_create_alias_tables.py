"""create alias tables

Revision ID: 46aedec8fd9b
Revises: c2b6eff6e213
Create Date: 2024-09-19 10:15:41.889874

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "46aedec8fd9b"
down_revision = "62551ed63cbf"
branch_labels = None
depends_on = None

user_common_fields = ["display_name", "is_verified", "show_in_directory", "bio"]
for i in range(1, 5):
    user_common_fields.extend(
        [
            f"extra_field_label{i}",
            f"extra_field_value{i}",
            f"extra_field_verified{i}",
        ]
    )

user_common_fields_str = ", ".join(user_common_fields)


def upgrade() -> None:
    op.create_table(
        "usernames",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("show_in_directory", sa.Boolean(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("extra_field_label1", sa.String(), nullable=True),
        sa.Column("extra_field_value1", sa.String(), nullable=True),
        sa.Column("extra_field_label2", sa.String(), nullable=True),
        sa.Column("extra_field_value2", sa.String(), nullable=True),
        sa.Column("extra_field_label3", sa.String(), nullable=True),
        sa.Column("extra_field_value3", sa.String(), nullable=True),
        sa.Column("extra_field_label4", sa.String(), nullable=True),
        sa.Column("extra_field_value4", sa.String(), nullable=True),
        sa.Column("extra_field_verified1", sa.Boolean(), nullable=True),
        sa.Column("extra_field_verified2", sa.Boolean(), nullable=True),
        sa.Column("extra_field_verified3", sa.Boolean(), nullable=True),
        sa.Column("extra_field_verified4", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.execute(
        sa.text(
            f"""
            INSERT INTO usernames (user_id, is_primary, username, {user_common_fields_str})
            SELECT id, true AS is_primary, primary_username, {user_common_fields_str}
            FROM users
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO usernames (
                user_id, is_primary, username, display_name, is_verified, show_in_directory)
            SELECT
                user_id, false AS is_primary, username, display_name, false AS is_verified,
                false AS show_in_directory
            FROM secondary_usernames
            """
        )
    )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.add_column(sa.Column("username_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE message
            SET username_id = q.username_id
            FROM (
                SELECT id AS username_id, user_id
                FROM usernames
            ) AS q
            WHERE message.user_id = q.user_id
            """
        )
    )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.alter_column("username_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("message_secondary_user_id_fkey", type_="foreignkey")
        batch_op.drop_constraint("message_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(None, "usernames", ["username_id"], ["id"])
        batch_op.drop_column("user_id")
        batch_op.drop_column("secondary_user_id")

    op.drop_table("secondary_usernames")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("users_primary_username_key", type_="unique")
        batch_op.drop_column("primary_username")
        batch_op.drop_column("display_name")
        batch_op.drop_column("bio")
        batch_op.drop_column("is_verified")
        batch_op.drop_column("show_in_directory")

        for i in range(1, 5):
            batch_op.drop_column(f"extra_field_value{i}")
            batch_op.drop_column(f"extra_field_label{i}")
            batch_op.drop_column(f"extra_field_verified{i}")


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("display_name", sa.VARCHAR(length=80), autoincrement=False, nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "primary_username",
                sa.VARCHAR(length=80),
                autoincrement=False,
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("is_verified", sa.BOOLEAN(), autoincrement=False, nullable=True)
        )
        batch_op.add_column(sa.Column("bio", sa.TEXT(), autoincrement=False, nullable=True))
        batch_op.add_column(
            sa.Column("show_in_directory", sa.BOOLEAN(), autoincrement=False, nullable=True)
        )

        for i in range(1, 5):
            batch_op.add_column(
                sa.Column(f"extra_field_value{i}", sa.VARCHAR(), autoincrement=False, nullable=True)
            )
            batch_op.add_column(
                sa.Column(f"extra_field_label{i}", sa.VARCHAR(), autoincrement=False, nullable=True)
            )
            batch_op.add_column(
                sa.Column(
                    f"extra_field_verified{i}", sa.BOOLEAN(), autoincrement=False, nullable=True
                )
            )

        batch_op.create_unique_constraint("users_primary_username_key", ["primary_username"])

    users_insert_str = ""
    for field in user_common_fields:
        users_insert_str += field + "=q." + field + ",\n"
    users_insert_str = users_insert_str[0:-2]  # trim last comma

    op.execute(
        sa.text(
            f"""
            UPDATE users
            SET primary_username=q.username,
                {users_insert_str}
            FROM (
                SELECT user_id, username, {user_common_fields_str}
                FROM usernames
                WHERE is_primary = true
            ) AS q
            WHERE users.id = q.user_id
            """
        )
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "is_verified", existing_type=sa.BOOLEAN(), autoincrement=False, nullable=False
        )
        batch_op.alter_column(
            "primary_username",
            existing_type=sa.VARCHAR(length=80),
            autoincrement=False,
            nullable=False,
        )
        batch_op.alter_column(
            "show_in_directory", existing_type=sa.BOOLEAN(), autoincrement=False, nullable=False
        )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(
            sa.Column("secondary_user_id", sa.INTEGER(), autoincrement=False, nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE message
            SET user_id = q.user_id
            FROM (
                SELECT id AS username_id, user_id
                FROM usernames
            ) AS q
            WHERE message.username_id = q.username_id
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE message
            SET secondary_user_id = q.user_id
            FROM (
                SELECT id AS username_id, user_id
                FROM usernames
                WHERE is_primary = false
            ) AS q
            WHERE message.username_id = q.username_id
            """
        )
    )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.alter_column(
            "user_id", existing_type=sa.INTEGER(), autoincrement=False, nullable=False
        )

    op.create_table(
        "secondary_usernames",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("username", sa.VARCHAR(length=80), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("display_name", sa.VARCHAR(length=80), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="secondary_usernames_user_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="secondary_usernames_pkey"),
        sa.UniqueConstraint("username", name="secondary_usernames_username_key"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO secondary_usernames (user_id, username, display_name)
            SELECT user_id, username, display_name
            FROM usernames
            WHERE is_primary = false
            """
        )
    )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.drop_constraint("message_username_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("message_user_id_fkey", "users", ["user_id"], ["id"])
        batch_op.create_foreign_key(
            "message_secondary_user_id_fkey", "secondary_usernames", ["secondary_user_id"], ["id"]
        )
        batch_op.drop_column("username_id")

    op.drop_table("usernames")

"""add FieldDefinition and FieldValue

Revision ID: 4a53667aff6e
Revises: cf2a880aff10
Create Date: 2025-01-16 23:24:40.316301

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "4a53667aff6e"
down_revision = "cf2a880aff10"
branch_labels = None
depends_on = None


fieldtype_enum = sa.Enum(
    "text", "multiline_text", "choice_single", "choice_multiple", name="fieldtype"
)


def upgrade() -> None:
    op.create_table(
        "field_definitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username_id", sa.Integer, sa.ForeignKey("usernames.id")),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column(
            "field_type",
            fieldtype_enum,
            default="TEXT",
        ),
        sa.Column("required", sa.Boolean, default=False),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("encrypted", sa.Boolean, default=False),
        sa.Column("choices", JSONB, default=[]),
        sa.Column("sort_order", sa.Integer, default=0),
    )

    op.create_table(
        "field_values",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("field_definition_id", sa.Integer, sa.ForeignKey("field_definitions.id")),
        sa.Column("message_id", sa.Integer, sa.ForeignKey("messages.id")),
        sa.Column("_value", sa.Text, nullable=False),
        sa.Column("encrypted", sa.Boolean, default=False),
    )

    # Create field definitions for every username
    connection = op.get_bind()
    usernames_result = connection.execute(sa.text("""SELECT id FROM usernames"""))
    for username_row in usernames_result:
        username_id = username_row[0]

        # Create field definitions
        insert_result = connection.execute(
            sa.text(
                f"""
                INSERT INTO field_definitions (
                    username_id, label, field_type,
                    required, enabled, encrypted, choices, sort_order
                )
                VALUES
                    ({username_id}, 'Contact Method', 'text', false, true, true, '[]', 0),
                    ({username_id}, 'Message', 'multiline_text', true, true, false, '[]', 1)
                RETURNING id
                """
            )
        )

        # Fetch the inserted IDs
        inserted_ids = insert_result.fetchall()
        message_field_definition_id = inserted_ids[1][0]

        # Select all messages for this username
        messages_result = connection.execute(
            sa.text(f"""SELECT id, content FROM messages WHERE username_id = {username_id}""")
        )
        for message_row in messages_result:
            message_id = message_row[0]
            message_content = message_row[1]

            # Create field value for message's content
            connection.execute(
                sa.text(
                    f"""
                    INSERT INTO field_values (
                        field_definition_id, message_id, _value, encrypted
                    )
                    VALUES
                        ({message_field_definition_id}, {message_id}, '{message_content}', true)
                    """
                )
            )

    # Drop the content column from messages
    op.drop_column("messages", "content")


def downgrade() -> None:
    # Add the content column back to messages
    op.add_column("messages", sa.Column("content", sa.Text))

    # Fetch all field values for messages' content
    connection = op.get_bind()

    field_values_result = connection.execute(
        sa.text(
            """
            SELECT field_values.message_id, field_values._value
            FROM field_values
            JOIN field_definitions ON field_values.field_definition_id = field_definitions.id
            WHERE field_definitions.label = 'Message'
            """
        )
    )
    print(f"Found {field_values_result.rowcount} field values to update")

    # Update messages with the content from field_values
    for field_value_row in field_values_result:
        message_id = field_value_row[0]
        message_content = field_value_row[1]

        connection.execute(
            sa.text(
                f"""
                UPDATE messages
                SET content = '{message_content}'
                WHERE id = {message_id}
                """
            )
        )

    # Drop the field_values and field_definitions tables
    op.drop_table("field_values")
    op.drop_table("field_definitions")

    # Drop the fieldtype enum type
    fieldtype_enum.drop(op.get_bind(), checkfirst=False)

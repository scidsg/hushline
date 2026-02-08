from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    FieldDefinition,
    FieldValue,
    Message,
    MessageStatusText,
    User,
    Username,
)


def delete_user_and_related(user: User) -> None:
    # Delete field values and definitions
    usernames = db.session.scalars(db.select(Username).filter_by(user_id=user.id)).all()
    username_ids = [username.id for username in usernames]

    # Delete all FieldValue entries related to the user's usernames
    db.session.execute(
        db.delete(FieldValue).where(
            FieldValue.field_definition_id.in_(
                db.select(FieldDefinition.id).where(FieldDefinition.username_id.in_(username_ids))
            )
        )
    )

    # Delete all FieldDefinition entries related to the user's usernames
    db.session.execute(
        db.delete(FieldDefinition).where(FieldDefinition.username_id.in_(username_ids))
    )

    # Delete messages and related data
    db.session.execute(
        db.delete(Message).filter(
            Message.username_id.in_(db.select(Username.id).filter_by(user_id=user.id))
        )
    )
    db.session.execute(db.delete(MessageStatusText).filter_by(user_id=user.id))
    db.session.execute(db.delete(AuthenticationLog).filter_by(user_id=user.id))

    # Delete username and finally the user
    db.session.execute(db.delete(Username).filter_by(user_id=user.id))
    db.session.delete(user)


def delete_username_and_related(username: Username) -> None:
    # Delete field values and definitions for this username
    db.session.execute(
        db.delete(FieldValue).where(
            FieldValue.field_definition_id.in_(
                db.select(FieldDefinition.id).where(FieldDefinition.username_id == username.id)
            )
        )
    )
    db.session.execute(db.delete(FieldDefinition).where(FieldDefinition.username_id == username.id))

    # Delete messages scoped to this username
    db.session.execute(db.delete(Message).filter(Message.username_id == username.id))

    # Delete the username itself
    db.session.delete(username)

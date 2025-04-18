from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
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


def register_delete_account_routes(bp: Blueprint) -> None:
    @bp.route("/delete-account", methods=["POST"])
    @authentication_required
    def delete_account() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user:
            if user.is_admin:
                admin_count = db.session.query(User).filter_by(is_admin=True).count()
                if admin_count == 1:
                    flash("⛔️ You cannot delete the only admin account")
                    return abort(400)

            # Delete field values and definitions
            usernames = db.session.scalars(db.select(Username).filter_by(user_id=user.id)).all()
            username_ids = [username.id for username in usernames]

            # Delete all FieldValue entries related to the user's usernames
            db.session.execute(
                db.delete(FieldValue).where(
                    FieldValue.field_definition_id.in_(
                        db.select(FieldDefinition.id).where(
                            FieldDefinition.username_id.in_(username_ids)
                        )
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
            db.session.commit()

            session.clear()
            flash("🔥 Your account and all related information have been deleted.")
            return redirect(url_for("index"))

        flash("User not found. Please log in again.")
        return redirect(url_for("login"))

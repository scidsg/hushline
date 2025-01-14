from flask import (
    Blueprint,
    flash,
    redirect,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import AuthenticationLog, Message, MessageStatusText, User, Username


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
            db.session.execute(
                db.delete(Message).filter(
                    Message.username_id.in_(db.select(Username.id).filter_by(user_id=user.id))
                )
            )
            db.session.execute(db.delete(MessageStatusText).filter_by(user_id=user.id))
            db.session.execute(db.delete(AuthenticationLog).filter_by(user_id=user.id))
            db.session.execute(db.delete(Username).filter_by(user_id=user.id))
            db.session.delete(user)
            db.session.commit()

            session.clear()
            flash("🔥 Your account and all related information have been deleted.")
            return redirect(url_for("index"))

        flash("User not found. Please log in again.")
        return redirect(url_for("login"))

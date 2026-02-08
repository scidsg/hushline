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
from hushline.model import User
from hushline.user_deletion import delete_user_and_related


def register_delete_account_routes(bp: Blueprint) -> None:
    @bp.route("/delete-account", methods=["POST"])
    @authentication_required
    def delete_account() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.")
            return redirect(url_for("login"))

        with db.session.begin_nested():
            user = db.session.get(User, user_id)
            if user:
                if user.is_admin:
                    admin_count = db.session.query(User).filter_by(is_admin=True).count()
                    if admin_count == 1:
                        flash("⛔️ You cannot delete the only admin account")
                        return abort(400)

                delete_user_and_related(user)
            else:
                flash("User not found. Please log in again.")
                return redirect(url_for("login"))

        db.session.commit()
        session.clear()
        flash("🔥 Your account and all related information have been deleted.")
        return redirect(url_for("index"))

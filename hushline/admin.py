from flask import Blueprint, abort, flash, redirect, url_for
from werkzeug.wrappers.response import Response

from .db import db
from .model import User
from .utils import admin_authentication_required


def create_blueprint() -> Blueprint:
    bp = Blueprint("admin", __file__, url_prefix="/admin")

    @bp.route("/toggle_verified/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_verified(user_id: int) -> Response:
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        user.is_verified = not user.is_verified
        db.session.commit()
        flash("✅ User verification status toggled.", "success")
        return redirect(url_for("settings.index"))

    @bp.route("/toggle_admin/<int:user_id>", methods=["POST"])
    @admin_authentication_required
    def toggle_admin(user_id: int) -> Response:
        user = db.session.get(User, user_id)
        if user is None:
            abort(404)
        user.is_admin = not user.is_admin
        db.session.commit()
        flash("✅ User admin status toggled.", "success")
        return redirect(url_for("settings.index"))

    return bp

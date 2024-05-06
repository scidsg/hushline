from flask import Blueprint, Response, flash, redirect, session, url_for

from .db import db
from .ext import limiter
from .model import User
from .utils import require_2fa


def create_blueprint() -> Blueprint:
    bp = Blueprint("admin", __file__, url_prefix="/admin")

    @bp.route("/toggle_verified/<int:user_id>", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def toggle_verified(user_id: int) -> Response:
        if not session.get("is_admin", False):
            flash("Unauthorized access.", "error")
            return redirect(url_for("settings.index"))

        user = User.query.get_or_404(user_id)
        user.is_verified = not user.is_verified
        db.session.commit()
        flash("✅ User verification status toggled.", "success")
        return redirect(url_for("settings.index"))

    @bp.route("/toggle_admin/<int:user_id>", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def toggle_admin(user_id: int) -> Response:
        if not session.get("is_admin", False):
            flash("Unauthorized access.", "error")
            return redirect(url_for("settings.index"))

        user = User.query.get_or_404(user_id)
        user.is_admin = not user.is_admin
        db.session.commit()
        flash("✅ User admin status toggled.", "success")
        return redirect(url_for("settings.index"))

    return bp

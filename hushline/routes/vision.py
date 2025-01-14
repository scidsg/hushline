from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import User


def register_vision_routes(app: Flask) -> None:
    @app.route("/vision")
    @authentication_required
    def vision() -> str | Response:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("⛔️ Please log in to access this feature.")
            return redirect(url_for("login"))

        if not user.tier_id:  # Assuming tier_id is None for unpaid users
            flash("⛔️ This feature is only available to paid users.")
            return redirect(url_for("premium.select_tier"))

        return render_template("vision.html")

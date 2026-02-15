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
from hushline.routes.tools import TOOL_TABS, TOOLS_SIDEBAR_THRESHOLD


def register_vision_routes(app: Flask) -> None:
    @app.route("/vision")
    @authentication_required
    def vision() -> str | Response:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("⛔️ Please log in to access this feature.")
            return redirect(url_for("login"))

        return render_template(
            "vision.html",
            tool_tabs=TOOL_TABS,
            tools_sidebar=len(TOOL_TABS) >= TOOLS_SIDEBAR_THRESHOLD,
        )

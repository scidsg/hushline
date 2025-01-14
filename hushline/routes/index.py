from flask import (
    Flask,
    flash,
    redirect,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.db import db
from hushline.model import (
    OrganizationSetting,
    User,
    Username,
)


def register_index_routes(app: Flask) -> None:
    @app.route("/")
    def index() -> Response:
        if "user_id" in session:
            user = db.session.get(User, session.get("user_id"))
            if user:
                return redirect(url_for("inbox"))

            flash("🫥 User not found. Please log in again.")
            session.pop("user_id", None)  # Clear the invalid user_id from session
            return redirect(url_for("login"))

        if homepage_username := OrganizationSetting.fetch_one(
            OrganizationSetting.HOMEPAGE_USER_NAME
        ):
            if db.session.scalar(
                db.exists(Username).where(Username._username == homepage_username).select()
            ):
                return redirect(url_for("profile", username=homepage_username))
            else:
                app.logger.warning(f"Homepage for username {homepage_username!r} not found")

        return redirect(url_for("directory"))

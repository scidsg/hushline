import json

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
    @app.route("/site.webmanifest")
    def site_webmanifest() -> Response:
        brand_name = OrganizationSetting.fetch_one(OrganizationSetting.BRAND_NAME) or "Hush Line"
        brand_primary_color = (
            OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PRIMARY_COLOR) or "#7d25c1"
        )

        logo_path = OrganizationSetting.fetch_one(OrganizationSetting.BRAND_LOGO)
        logo_url = url_for("storage.public", path=logo_path) if logo_path else None

        icons = []
        if logo_url:
            icons.append({"src": logo_url, "sizes": "any", "type": "image/png"})
        icons.extend(
            [
                {
                    "src": url_for("static", filename="favicon/android-chrome-192x192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": url_for("static", filename="favicon/android-chrome-512x512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                },
            ]
        )

        manifest = {
            "name": brand_name,
            "short_name": brand_name,
            "start_url": "/",
            "display": "standalone",
            "background_color": "#fbf3ff",
            "theme_color": brand_primary_color,
            "description": (
                "Anonymous reporting and whistleblower management for organizations "
                "and individuals."
            ),
            "icons": icons,
        }
        return Response(json.dumps(manifest), mimetype="application/manifest+json")

    @app.route("/")
    def index() -> Response:
        # If logged in, redirect to inbox
        if "user_id" in session:
            user = db.session.get(User, session.get("user_id"))
            if user:
                return redirect(url_for("inbox"))

            flash("🫥 User not found. Please log in again.")
            session.pop("user_id", None)  # Clear the invalid user_id from session
            return redirect(url_for("login"))

        # If there are no users, redirect to registration
        user_count = db.session.query(User).count()
        if user_count == 0:
            return redirect(url_for("register"))

        # If there is a homepage username set, redirect to that user's profile
        if homepage_username := OrganizationSetting.fetch_one(
            OrganizationSetting.HOMEPAGE_USER_NAME
        ):
            if db.session.scalar(
                db.exists(Username).where(Username._username == homepage_username).select()
            ):
                return redirect(url_for("profile", username=homepage_username))
            else:
                app.logger.warning(f"Homepage for username {homepage_username!r} not found")

        # If there is no homepage username set, redirect to the directory
        return redirect(url_for("directory"))

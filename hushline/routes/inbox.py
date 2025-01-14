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
from hushline.model import (
    User,
    Username,
)


def register_inbox_routes(app: Flask) -> None:
    @app.route("/inbox")
    @authentication_required
    def inbox() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("👉 Please log in to access your inbox.")
            return redirect(url_for("login"))

        user_alias_count = db.session.scalar(
            db.select(db.func.count(Username.id).filter(Username.user_id == user.id))
        )
        return render_template(
            "inbox.html",
            user=user,
            user_has_aliases=user_alias_count > 1,
        )

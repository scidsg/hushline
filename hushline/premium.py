from flask import Blueprint, redirect, render_template, session, url_for
from werkzeug.wrappers.response import Response

from .db import db
from .model import User
from .utils import authentication_required


def create_blueprint() -> Blueprint:
    bp = Blueprint("premium", __file__, url_prefix="/premium")

    @bp.route("/", methods=["GET"])
    @authentication_required
    def premium() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        return render_template("premium.html", user=user)

    return bp

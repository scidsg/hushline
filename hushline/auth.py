from functools import wraps
from typing import Any, Callable

from flask import abort, flash, redirect, session, url_for

from hushline.model import User

from .db import db


def authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if "user_id" not in session:
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))

        if not session.get("is_authenticated", False):
            return redirect(url_for("verify_2fa_login"))

        return f(*args, **kwargs)

    return decorated_function


def admin_authentication_required(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    @authentication_required
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        user = db.session.get(User, session["user_id"])
        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function

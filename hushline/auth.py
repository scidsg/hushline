from functools import wraps
from hmac import compare_digest
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, session, url_for

from hushline.db import db
from hushline.model import User

AUTH_SESSION_KEYS = ("user_id", "session_id", "username", "is_authenticated")


def clear_auth_session() -> None:
    for key in AUTH_SESSION_KEYS:
        session.pop(key, None)


def rotate_user_session_id(user: User) -> None:
    user.session_id = User.new_session_id()
    db.session.add(user)


def set_session_user(*, user: User, username: str, is_authenticated: bool) -> None:
    session.permanent = True
    session["user_id"] = user.id
    session["session_id"] = user.session_id
    session["username"] = username
    session["is_authenticated"] = is_authenticated


def get_session_user() -> User | None:
    user_id = session.get("user_id")
    session_id = session.get("session_id")
    if user_id is None and session_id is None:
        return None

    if user_id is None or not isinstance(session_id, str):
        clear_auth_session()
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.session_id:
        clear_auth_session()
        return None

    if not compare_digest(user.session_id, session_id):
        clear_auth_session()
        return None

    return user


def authentication_required(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        if not get_session_user():
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))

        if not session.get("is_authenticated", False):
            return redirect(url_for("verify_2fa_login"))

        return current_app.ensure_sync(func)(*args, **kwargs)

    return decorated_function


def admin_authentication_required(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    @authentication_required
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        user = get_session_user()
        if not user or not user.is_admin:
            abort(403)
        return current_app.ensure_sync(func)(*args, **kwargs)

    return decorated_function

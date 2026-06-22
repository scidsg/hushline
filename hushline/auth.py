import secrets
from functools import wraps
from hmac import compare_digest
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from flask import abort, current_app, flash, redirect, request, session, url_for

from hushline.db import db
from hushline.model import User

PENDING_PASSWORD_REHASH_SESSION_KEY = "pending_password_rehash"  # noqa: S105
PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY = "pending_password_rehash_source_digest"  # noqa: S105
POST_AUTH_REDIRECT_SESSION_KEY = "post_auth_redirect"
CHAT_KEY_SESSION_ID_SESSION_KEY = "chat_key_session_id"
ASCII_CONTROL_MAX = 31
ASCII_DELETE = 127
AUTH_SESSION_KEYS = (
    "user_id",
    "session_id",
    "username",
    "is_authenticated",
    CHAT_KEY_SESSION_ID_SESSION_KEY,
    POST_AUTH_REDIRECT_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY,
)


def clear_auth_session() -> None:
    for key in AUTH_SESSION_KEYS:
        session.pop(key, None)


def rotate_user_session_id(user: User) -> None:
    user.session_id = User.new_session_id()
    db.session.add(user)


def rotate_chat_key_session_id() -> str:
    session[CHAT_KEY_SESSION_ID_SESSION_KEY] = secrets.token_urlsafe(32)
    return str(session[CHAT_KEY_SESSION_ID_SESSION_KEY])


def set_session_user(*, user: User, username: str, is_authenticated: bool) -> None:
    session.permanent = True
    session["user_id"] = user.id
    session["session_id"] = user.session_id
    session["username"] = username
    session["is_authenticated"] = is_authenticated
    if is_authenticated:
        rotate_chat_key_session_id()
    else:
        session.pop(CHAT_KEY_SESSION_ID_SESSION_KEY, None)


def _is_safe_post_auth_redirect_target(redirect_target: str | None) -> bool:
    if not isinstance(redirect_target, str):
        return False
    if not redirect_target.startswith("/") or redirect_target.startswith("//"):
        return False

    parsed_target = urlsplit(redirect_target)
    if parsed_target.scheme or parsed_target.netloc:
        return False

    decoded_target = unquote(redirect_target)
    if "\\" in redirect_target or "\\" in decoded_target:
        return False
    return not any(
        ord(char) <= ASCII_CONTROL_MAX or ord(char) == ASCII_DELETE for char in decoded_target
    )


def stash_post_auth_redirect_target(redirect_target: str | None) -> None:
    if not _is_safe_post_auth_redirect_target(redirect_target):
        return

    session[POST_AUTH_REDIRECT_SESSION_KEY] = redirect_target


def stash_post_auth_redirect() -> None:
    if request.method != "GET":
        return
    if request.endpoint == "logout":
        return

    stash_post_auth_redirect_target(request.full_path.removesuffix("?"))


def pop_post_auth_redirect(*, default_endpoint: str = "inbox") -> str:
    redirect_target = session.pop(POST_AUTH_REDIRECT_SESSION_KEY, None)
    if _is_safe_post_auth_redirect_target(redirect_target):
        return redirect_target

    return url_for(default_endpoint)


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
            stash_post_auth_redirect()
            flash("👉 Please complete authentication.")
            return redirect(url_for("login"))

        if not session.get("is_authenticated", False):
            stash_post_auth_redirect()
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

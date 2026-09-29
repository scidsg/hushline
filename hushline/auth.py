import secrets
import time
from datetime import datetime
from functools import wraps
from hmac import compare_digest
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import pyotp
from flask import abort, current_app, flash, redirect, request, session, url_for

from hushline.db import db
from hushline.model import AuthenticationLog, User

PENDING_PASSWORD_REHASH_SESSION_KEY = "pending_password_rehash"  # noqa: S105
PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY = "pending_password_rehash_source_digest"  # noqa: S105
PENDING_LOGIN_CHAT_KEY_SESSION_KEY = "pending_login_chat_key_payload"
PENDING_MFA_METHODS_SESSION_KEY = "pending_mfa_methods"
POST_AUTH_REDIRECT_SESSION_KEY = "post_auth_redirect"
CHAT_KEY_SESSION_ID_SESSION_KEY = "chat_key_session_id"
WEBAUTHN_SESSION_BINDING_KEY = "webauthn_session_binding"
WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY = "webauthn_enrollment_authorization"
WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY = "webauthn_password_confirmation"  # noqa: S105
RECOVERY_CODES_PENDING_ACK_SESSION_KEY = "recovery_codes_pending_ack"
STRONG_AUTHENTICATION_SESSION_KEY = "strong_authentication"
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
    PENDING_LOGIN_CHAT_KEY_SESSION_KEY,
    PENDING_MFA_METHODS_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
    WEBAUTHN_ENROLLMENT_AUTHORIZATION_SESSION_KEY,
    WEBAUTHN_PASSWORD_CONFIRMATION_SESSION_KEY,
    RECOVERY_CODES_PENDING_ACK_SESSION_KEY,
    STRONG_AUTHENTICATION_SESSION_KEY,
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


def record_strong_authentication(*, user: User, method: str) -> None:
    session[STRONG_AUTHENTICATION_SESSION_KEY] = {
        "authenticated_at": int(time.time()),
        "method": method,
        "session_id": user.session_id,
        "user_id": user.id,
    }


def matching_totp_timecode(*, totp: pyotp.TOTP, code: str, now: datetime) -> int | None:
    """Return the counter that produced a code in the accepted clock-skew window."""
    current_timecode = totp.timecode(now)
    matched_timecode = None
    for offset in range(-1, 2):
        candidate_timecode = current_timecode + offset
        if compare_digest(totp.generate_otp(candidate_timecode), code):
            matched_timecode = candidate_timecode
    return matched_timecode


def totp_code_was_used(*, user_id: int, code: str, timecode: int) -> bool:
    """Serialize and detect successful use of a TOTP code in its time step."""
    db.session.scalar(db.select(User.id).where(User.id == user_id).with_for_update())
    return (
        db.session.scalar(
            db.select(AuthenticationLog.id)
            .where(
                AuthenticationLog.user_id == user_id,
                AuthenticationLog.successful.is_(True),
                AuthenticationLog.otp_code == code,
                AuthenticationLog.timecode == timecode,
            )
            .limit(1)
        )
        is not None
    )


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
        session.pop(STRONG_AUTHENTICATION_SESSION_KEY, None)


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

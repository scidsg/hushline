import json
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from http import HTTPStatus
from typing import Any

import pyotp
from flask import (
    Flask,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import validate_csrf
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, MultipleResultsFound
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import (
    PENDING_LOGIN_CHAT_KEY_SESSION_KEY,
    PENDING_MFA_METHODS_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY,
    WEBAUTHN_SESSION_BINDING_KEY,
    authentication_required,
    clear_auth_session,
    get_session_user,
    matching_totp_timecode,
    pop_post_auth_redirect,
    record_strong_authentication,
    rotate_user_session_id,
    set_session_user,
    stash_post_auth_redirect_target,
    totp_code_was_used,
)
from hushline.chat_key_lifecycle import retire_active_chat_key, validate_chat_key_payload
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    ChatKey,
    InviteCode,
    OrganizationSetting,
    PasswordResetAttempt,
    PasswordResetToken,
    User,
    Username,
)
from hushline.password_hasher import (
    LEGACY_PASSLIB_SCRYPT_PREFIX,
    emit_password_rehash_on_auth_telemetry,
    prepare_password_rehash_on_auth,
)
from hushline.recovery_codes import consume_recovery_code, has_usable_recovery_codes
from hushline.routes.common import validate_captcha
from hushline.routes.forms import (
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RecoveryCodeLoginForm,
    RegistrationForm,
    TwoFactorForm,
)

PASSWORD_RESET_CONFIRMATION_MESSAGE = (
    "If an eligible account exists, reset instructions will be sent."  # noqa: S105
)
PASSWORD_RESET_INVALID_LINK_MESSAGE = (
    "Password reset links expire quickly and can only be used once. Request a new reset if needed."  # noqa: S105
)
TOTP_MFA_METHOD = "totp"
SECURITY_KEY_MFA_METHOD = "security_key"
RECOVERY_CODE_MFA_METHOD = "recovery_code"


class PendingLoginStateError(Exception):
    pass


def _now() -> datetime:
    return datetime.now()


def _password_hash_digest(stored_hash: str) -> str:
    return sha256(stored_hash.encode("utf-8")).hexdigest()


def _password_reset_hmac(value: str) -> str:
    secret = (
        current_app.config.get("SECRET_KEY")
        or current_app.config.get("SESSION_FERNET_KEY")
        or current_app.config.get("ENCRYPTION_KEY")
        or ""
    )
    return hmac_new(str(secret).encode("utf-8"), value.encode("utf-8"), sha256).hexdigest()


def _password_reset_identifier_hash(identifier: str) -> str:
    return _password_reset_hmac(identifier.strip().lower())


def _password_reset_ip_hash() -> str:
    return _password_reset_hmac(request.remote_addr or "unknown")


def _password_reset_ttl() -> timedelta:
    minutes = int(current_app.config.get("PASSWORD_RESET_TOKEN_TTL_MINUTES", 30))
    return timedelta(minutes=minutes)


def _create_initial_chat_key_from_payload(
    user: User,
    payload: dict[str, Any] | None,
    *,
    when: datetime | None = None,
) -> ChatKey | None:
    if payload is None or user.active_chat_key is not None:
        return None

    next_version = max((chat_key.key_version for chat_key in user.chat_keys), default=0) + 1
    chat_key = ChatKey(
        user=user,
        key_version=next_version,
        public_key=payload["public_key"],
        public_signing_key=payload["public_signing_key"],
        encrypted_private_key=payload["encrypted_private_key"],
        kdf_algorithm=payload["kdf_algorithm"],
        kdf_params=payload["kdf_params"],
        kdf_salt=payload["kdf_salt"],
        wrapping_algorithm=payload["wrapping_algorithm"],
        recovery_state=payload["recovery_state"],
        created_at=when or datetime.now(UTC),
    )
    db.session.add(chat_key)
    return chat_key


def _validated_login_chat_key_payload(user: User) -> dict[str, Any] | None:
    raw_payload = request.form.get("chat_key_payload", "").strip()
    if not raw_payload:
        session.pop(PENDING_LOGIN_CHAT_KEY_SESSION_KEY, None)
        return None

    try:
        submitted_payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        current_app.logger.warning("Ignoring malformed login chat key payload.")
        session.pop(PENDING_LOGIN_CHAT_KEY_SESSION_KEY, None)
        return None

    cleaned_payload, error = validate_chat_key_payload(submitted_payload, current_user_id=user.id)
    if error:
        current_app.logger.warning(
            "Ignoring invalid login chat key payload.",
            extra={"chat_key_error": error},
        )
        session.pop(PENDING_LOGIN_CHAT_KEY_SESSION_KEY, None)
        return None
    return cleaned_payload


def _stash_pending_login_chat_key(user: User, payload: dict[str, Any] | None) -> None:
    if payload is None or user.active_chat_key is not None:
        session.pop(PENDING_LOGIN_CHAT_KEY_SESSION_KEY, None)
        return
    session[PENDING_LOGIN_CHAT_KEY_SESSION_KEY] = payload


def _provision_pending_login_chat_key(user: User) -> None:
    payload = session.pop(PENDING_LOGIN_CHAT_KEY_SESSION_KEY, None)
    if isinstance(payload, dict):
        _create_initial_chat_key_from_payload(user, payload)


def _active_mfa_methods(user: User) -> list[str]:
    methods: list[str] = []
    if user.totp_secret:
        methods.append(TOTP_MFA_METHOD)
    if any(credential.disabled_at is None for credential in user.webauthn_credentials):
        methods.append(SECURITY_KEY_MFA_METHOD)
    if has_usable_recovery_codes(user.id):
        methods.append(RECOVERY_CODE_MFA_METHOD)
    return methods


def _pending_mfa_methods(user: User) -> frozenset[str]:
    methods = session.get(PENDING_MFA_METHODS_SESSION_KEY)
    if methods is None:
        # Continue pre-deployment TOTP challenges without weakening the current
        # account policy. New password logins always store the permitted set.
        return frozenset(_active_mfa_methods(user))
    if not isinstance(methods, list) or any(not isinstance(method, str) for method in methods):
        return frozenset()
    return frozenset(methods).intersection(
        {TOTP_MFA_METHOD, SECURITY_KEY_MFA_METHOD, RECOVERY_CODE_MFA_METHOD}
    )


def _mfa_attempt_rate_limited(user_id: int) -> bool:
    failed_logins = db.session.scalar(
        db.select(db.func.count())
        .select_from(AuthenticationLog)
        .where(
            AuthenticationLog.user_id == user_id,
            AuthenticationLog.successful == db.false(),
            AuthenticationLog.timestamp > datetime.now() - timedelta(seconds=30),
        )
    )
    return failed_logins is not None and failed_logins >= 5  # noqa: PLR2004


def _json_csrf_error() -> str | None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None
    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError:
        return "Invalid CSRF token."
    return None


def _json_error(message: str, status: HTTPStatus) -> tuple[Response, int]:
    response = make_response({"error": message})
    response.headers["Cache-Control"] = "no-store"
    return response, status.value


def _password_reset_rate_limited(identifier_hash: str, ip_hash: str) -> bool:
    now = _now()
    window_minutes = int(current_app.config.get("PASSWORD_RESET_RATE_LIMIT_WINDOW_MINUTES", 60))
    identifier_max = int(current_app.config.get("PASSWORD_RESET_RATE_LIMIT_IDENTIFIER_MAX", 5))
    ip_max = int(current_app.config.get("PASSWORD_RESET_RATE_LIMIT_IP_MAX", 20))
    window_start = now - timedelta(minutes=window_minutes)

    identifier_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(PasswordResetAttempt)
        .where(
            PasswordResetAttempt.identifier_hash == identifier_hash,
            PasswordResetAttempt.created_at >= window_start,
        )
    )
    ip_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(PasswordResetAttempt)
        .where(
            PasswordResetAttempt.ip_hash == ip_hash,
            PasswordResetAttempt.created_at >= window_start,
        )
    )

    db.session.add(
        PasswordResetAttempt(
            identifier_hash=identifier_hash,
            ip_hash=ip_hash,
            created_at=now,
        )
    )
    db.session.commit()
    return bool(
        identifier_count is not None
        and identifier_count >= identifier_max
        or ip_count is not None
        and ip_count >= ip_max
    )


def _find_primary_username(identifier: str) -> Username | None:
    try:
        return db.session.scalars(
            db.select(Username).where(
                func.lower(Username._username) == identifier.strip().lower(),
                Username.is_primary.is_(True),
            )
        ).one_or_none()
    except MultipleResultsFound:
        current_app.logger.error(
            "Multiple primary usernames matched case-insensitive password reset lookup",
            extra={"username_hash": _password_reset_identifier_hash(identifier)},
        )
        return None


def _invalidate_password_reset_tokens(user: User, *, used_at: datetime) -> None:
    for token in user.password_reset_tokens:
        if token.used_at is None:
            token.used_at = used_at
            db.session.add(token)


def _eligible_password_reset_user(identifier: str) -> User | None:
    """Return a reset-eligible user only when a verified recovery factor exists.

    Notification recipients can be shared/team-controlled mailboxes, so they must not be
    treated as password reset authorities. Until a dedicated verified recovery address is
    available, public reset requests remain generic and do not create reset tokens.
    """
    username = _find_primary_username(identifier)
    if username is None:
        return None

    user = username.user
    if user.enable_email_notifications and user.enabled_notification_recipients:
        current_app.logger.info(
            "Skipping password reset for account with notification recipients but no verified "
            "recovery address",
            extra={"user_id": user.id},
        )
    return None


def _load_active_password_reset_token(raw_token: str) -> PasswordResetToken | None:
    token_hash = PasswordResetToken.hash_password_reset_token(raw_token)
    token = db.session.scalars(
        db.select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).one_or_none()
    if token is None or token.used_at is not None or token.expires_at <= _now():
        return None
    return token


def _stash_pending_password_rehash(*, replacement_hash: str, source_hash: str) -> None:
    session[PENDING_PASSWORD_REHASH_SESSION_KEY] = replacement_hash
    session[PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY] = _password_hash_digest(source_hash)


def _apply_pending_password_rehash(user: User, *, source_hash: str) -> bool:
    replacement_hash = session.pop(PENDING_PASSWORD_REHASH_SESSION_KEY, None)
    source_digest = session.pop(PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY, None)

    if replacement_hash is None and source_digest is None:
        return False

    if not isinstance(replacement_hash, str) or not isinstance(source_digest, str):
        raise RuntimeError("Pending password rehash state was invalid")

    if not source_hash.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX):
        raise RuntimeError("Pending password rehash source was not legacy")

    if _password_hash_digest(source_hash) != source_digest:
        raise RuntimeError("Pending password rehash source no longer matched")

    user._password_hash = replacement_hash
    db.session.add(user)
    return True


def _complete_pending_login(
    user: User, auth_log: AuthenticationLog, *, authentication_method: str
) -> str:
    password_rehash_source_hash = user.password_hash
    has_pending_password_rehash = PENDING_PASSWORD_REHASH_SESSION_KEY in session
    username = session.get("username")
    pending_session_id = session.get("session_id")
    if not isinstance(username, str) or not isinstance(pending_session_id, str):
        clear_auth_session()
        raise PendingLoginStateError("Pending login state was invalid")

    replacement_session_id = User.new_session_id()
    claimed_user_id = db.session.scalar(
        db.update(User)
        .where(User.id == user.id, User.session_id == pending_session_id)
        .values(session_id=replacement_session_id)
        .returning(User.id)
    )
    if claimed_user_id is None:
        db.session.rollback()
        clear_auth_session()
        raise PendingLoginStateError("Pending login was already completed")
    user.session_id = replacement_session_id

    db.session.add(auth_log)
    set_session_user(user=user, username=username, is_authenticated=True)
    record_strong_authentication(user=user, method=authentication_method)
    session.pop(PENDING_MFA_METHODS_SESSION_KEY, None)
    session.pop(WEBAUTHN_SESSION_BINDING_KEY, None)
    try:
        _apply_pending_password_rehash(user, source_hash=password_rehash_source_hash)
        _provision_pending_login_chat_key(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        clear_auth_session()
        if has_pending_password_rehash:
            emit_password_rehash_on_auth_telemetry(
                password_rehash_source_hash,
                success=False,
            )
        raise
    if has_pending_password_rehash:
        emit_password_rehash_on_auth_telemetry(
            password_rehash_source_hash,
            success=True,
        )

    if current_app.config.get("SINGLE_TENANT_ENABLED"):
        from hushline.single_tenant import pending_setup

        if user.tier_id is None:
            return url_for("single_tenant.plans")
        if pending_setup(user):
            return url_for("single_tenant.setup")
    if not user.onboarding_complete:
        return url_for("onboarding")
    if current_app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
        return url_for("premium.select_tier")
    return pop_post_auth_redirect()


def _lock_first_user_registration() -> None:
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return

    # Serialize first-user privilege assignment so concurrent registrations
    # cannot both observe an empty users table.
    db.session.execute(db.select(func.pg_advisory_xact_lock(7255323892615124088)))


def _get_math_problem(force_new: bool = False) -> str:
    if not force_new and session.get("math_problem") and session.get("math_answer"):
        return session["math_problem"]

    num1 = secrets.randbelow(10) + 1
    num2 = secrets.randbelow(10) + 1
    math_problem = f"{num1} + {num2} ="
    session["math_answer"] = str(num1 + num2)
    session["math_problem"] = math_problem
    return math_problem


def register_auth_routes(app: Flask) -> None:
    def _stash_next_post_auth_redirect() -> None:
        if request.method == "GET":
            stash_post_auth_redirect_target(request.args.get("next"))

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Response | str:
        if session.get("is_authenticated", False) and get_session_user():
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

        _stash_next_post_auth_redirect()

        # Check if this is the first user for template/rendering hints.
        first_user = db.session.query(User).count() == 0

        # Check if registration is allowed
        registration_enabled = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_ENABLED
        )
        if not registration_enabled and not first_user:
            flash("⛔️ Registration is disabled.")
            return redirect(url_for("index"))

        # Check if registration codes are required
        registration_codes_enabled = OrganizationSetting.fetch_one(
            OrganizationSetting.REGISTRATION_CODES_REQUIRED
        )

        form = RegistrationForm()
        if not registration_codes_enabled:
            del form.invite_code

        math_problem = _get_math_problem(force_new=request.method == "GET")

        if request.method == "POST" and form.validate():
            captcha_answer = request.form.get("captcha_answer", "")
            app.logger.debug(f"Session math_answer: {session.get('math_answer')}")
            app.logger.debug(f"User entered captcha_answer: {captcha_answer}")

            if str(captcha_answer) != session.get("math_answer"):
                flash("⛔️ Incorrect CAPTCHA. Please try again.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    math_problem=math_problem,
                    first_user=first_user,
                )

            # Proceed with registration logic
            submitted_username = form.username.data
            password = form.password.data

            invite_code_input = form.invite_code.data if registration_codes_enabled else None
            if invite_code_input:
                invite_code = db.session.scalars(
                    db.select(InviteCode).filter_by(code=invite_code_input)
                ).one_or_none()
                if not invite_code or invite_code.expiration_date.replace(
                    tzinfo=UTC
                ) < datetime.now(UTC):
                    flash("⛔️ Invalid or expired invite code.", "error")
                    return render_template(
                        "register.html",
                        form=form,
                        math_problem=math_problem,
                        first_user=first_user,
                    )

            if db.session.scalar(
                db.exists(Username)
                .where(func.lower(Username._username) == submitted_username.lower())
                .select()
            ):
                flash("💔 Username already taken.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    math_problem=math_problem,
                    first_user=first_user,
                )

            _lock_first_user_registration()
            registered_users = db.session.query(User).count()
            license_limit = current_app.config.get("SINGLE_TENANT_LICENSE_LIMIT")
            if license_limit is not None and (
                isinstance(license_limit, bool)
                or not isinstance(license_limit, int)
                or license_limit < 1
                or registered_users >= license_limit
            ):
                db.session.rollback()
                flash("This instance has reached its licensed account limit.")
                return redirect(url_for("register"))
            first_user = registered_users == 0
            if not registration_enabled and not first_user:
                flash("⛔️ Registration is disabled.")
                return redirect(url_for("index"))

            user = User(password=password)

            # If this is the first user, set them as admin
            if first_user:
                user.is_admin = True

            db.session.add(user)
            db.session.flush()

            username = Username(_username=submitted_username, user_id=user.id, is_primary=True)

            # If this is the first user, show them in the directory
            if first_user:
                username.show_in_directory = True

            db.session.add(username)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                if db.session.scalar(
                    db.exists(Username)
                    .where(func.lower(Username._username) == submitted_username.lower())
                    .select()
                ):
                    flash("💔 Username already taken.", "error")
                else:
                    current_app.logger.error("Unexpected registration error", exc_info=True)
                    flash("⛔️ Internal server error. Registration failed.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    math_problem=math_problem,
                    first_user=first_user,
                )

            username.create_default_field_defs()

            if invite_code_input:
                # Delete the invite code after use
                db.session.delete(invite_code)
                db.session.commit()

            flash("👍 Registration successful!", "success")
            return redirect(url_for("login"))

        return render_template(
            "register.html",
            form=form,
            math_problem=math_problem,
            first_user=first_user,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Response | str:
        if session.get("is_authenticated", False) and get_session_user():
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

        _stash_next_post_auth_redirect()

        form = LoginForm()
        if request.method == "POST" and form.validate():
            session.pop(PENDING_PASSWORD_REHASH_SESSION_KEY, None)
            session.pop(PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY, None)
            try:
                username = db.session.scalars(
                    db.select(Username).where(
                        func.lower(Username._username) == form.username.data.strip().lower(),
                        Username.is_primary.is_(True),
                    )
                ).one_or_none()
            except MultipleResultsFound:
                current_app.logger.error(
                    "Multiple primary usernames matched case-insensitive login lookup",
                    extra={"username": form.username.data.strip().lower()},
                )
                flash("⛔️ Invalid username or password.")
                return render_template("login.html", form=form)
            if username and username.user.check_password(form.password.data):
                user = username.user
                password_rehash_source_hash = user.password_hash
                pending_password_rehash = prepare_password_rehash_on_auth(
                    form.password.data,
                    password_rehash_source_hash,
                )
                login_chat_key_payload = _validated_login_chat_key_payload(user)
                mfa_methods = _active_mfa_methods(user)
                session.pop(WEBAUTHN_SESSION_BINDING_KEY, None)

                if mfa_methods:
                    set_session_user(user=user, username=username.username, is_authenticated=False)
                    session[PENDING_MFA_METHODS_SESSION_KEY] = mfa_methods
                    _stash_pending_login_chat_key(user, login_chat_key_payload)
                    if pending_password_rehash is not None:
                        _stash_pending_password_rehash(
                            replacement_hash=pending_password_rehash,
                            source_hash=password_rehash_source_hash,
                        )
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        clear_auth_session()
                        raise
                    return redirect(url_for("verify_2fa_login"))

                session.pop(PENDING_MFA_METHODS_SESSION_KEY, None)
                rotate_user_session_id(user)
                set_session_user(user=user, username=username.username, is_authenticated=True)

                auth_log = AuthenticationLog(user_id=user.id, successful=True)
                db.session.add(auth_log)
                _create_initial_chat_key_from_payload(user, login_chat_key_payload)
                if pending_password_rehash is not None:
                    user._password_hash = pending_password_rehash
                    db.session.add(user)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    clear_auth_session()
                    if pending_password_rehash is not None:
                        emit_password_rehash_on_auth_telemetry(
                            password_rehash_source_hash,
                            success=False,
                        )
                    raise
                if pending_password_rehash is not None:
                    emit_password_rehash_on_auth_telemetry(
                        password_rehash_source_hash,
                        success=True,
                    )

                if app.config.get("SINGLE_TENANT_ENABLED"):
                    from hushline.single_tenant import pending_setup

                    if user.tier_id is None:
                        return redirect(url_for("single_tenant.plans"))
                    if pending_setup(user):
                        return redirect(url_for("single_tenant.setup"))
                if not user.onboarding_complete:
                    return redirect(url_for("onboarding"))

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
                    return redirect(url_for("premium.select_tier"))

                return redirect(pop_post_auth_redirect())

            flash("⛔️ Invalid username or password.")
        return render_template("login.html", form=form)

    @app.route("/password-reset", methods=["GET", "POST"])
    def request_password_reset() -> Response | str | tuple[str, int]:
        form = PasswordResetRequestForm()
        math_problem = _get_math_problem(force_new=request.method == "GET")
        if request.method == "POST" and form.validate():
            if not validate_captcha(form.captcha_answer.data):
                return render_template(
                    "password_reset_request.html", form=form, math_problem=math_problem
                )

            identifier = form.username.data or ""
            identifier_hash = _password_reset_identifier_hash(identifier)
            ip_hash = _password_reset_ip_hash()
            if _password_reset_rate_limited(identifier_hash, ip_hash):
                flash("⏲️ Please wait before requesting another password reset.")
                return render_template("password_reset_requested.html"), 429

            _eligible_password_reset_user(identifier)

            return render_template("password_reset_requested.html")

        return render_template("password_reset_request.html", form=form, math_problem=math_problem)

    @app.route("/password-reset/<token>", methods=["GET", "POST"])
    def reset_password(token: str) -> Response | str | tuple[str, int]:
        reset_token = _load_active_password_reset_token(token)
        if reset_token is None:
            flash(PASSWORD_RESET_INVALID_LINK_MESSAGE)
            return redirect(url_for("request_password_reset"))

        form = PasswordResetForm()
        if request.method == "POST":
            if form.validate():
                user = reset_token.user
                new_password = form.password.data
                if user.check_password(new_password):
                    form.password.errors.append("Cannot choose a repeat password.")
                    return render_template("password_reset.html", form=form), 400

                now = _now()
                retire_active_chat_key(
                    user,
                    recovery_state="password_reset_locked",
                    when=datetime.now(UTC),
                )
                user.password_hash = new_password
                rotate_user_session_id(user)
                _invalidate_password_reset_tokens(user, used_at=now)
                db.session.commit()
                session.clear()
                flash("👍 Password successfully reset. Please log in.", "success")
                return redirect(url_for("login"))

            return render_template("password_reset.html", form=form), 400

        return render_template("password_reset.html", form=form)

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    def verify_2fa_login() -> Response | str | tuple[Response | str, int]:
        # Redirect to login if the login process has not started yet
        user = get_session_user()
        if not user:
            clear_auth_session()
            return redirect(url_for("login"))

        if session.get("is_authenticated", False):
            return redirect(url_for("inbox"))

        pending_methods = _pending_mfa_methods(user)
        allow_totp = TOTP_MFA_METHOD in pending_methods and bool(user.totp_secret)
        allow_security_key = SECURITY_KEY_MFA_METHOD in pending_methods and any(
            credential.disabled_at is None for credential in user.webauthn_credentials
        )
        allow_recovery_code = (
            RECOVERY_CODE_MFA_METHOD in pending_methods and has_usable_recovery_codes(user.id)
        )
        if not allow_totp and not allow_security_key and not allow_recovery_code:
            clear_auth_session()
            flash("⛔️ No permitted second factor is available. Please log in again.")
            return redirect(url_for("login"))

        form = TwoFactorForm()

        def render_mfa() -> Response:
            response = make_response(
                render_template(
                    "verify_2fa_login.html",
                    form=form,
                    allow_totp=allow_totp,
                    allow_security_key=allow_security_key,
                    allow_recovery_code=allow_recovery_code,
                    recovery_code_form=RecoveryCodeLoginForm(),
                )
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        if request.method == "POST" and form.validate():
            if not allow_totp or not user.totp_secret:
                flash("⛔️ Authenticator app verification is not permitted for this login.")
                return redirect(url_for("login"))

            totp = pyotp.TOTP(user.totp_secret)
            verification_code = form.verification_code.data
            timecode = matching_totp_timecode(
                totp=totp,
                code=verification_code,
                now=datetime.now(),
            )

            rate_limit = False

            if timecode is not None and totp_code_was_used(
                user_id=user.id, code=verification_code, timecode=timecode
            ):
                # Bind replay detection to the counter that generated the code. This also rejects
                # reuse from the previous counter while it remains inside the accepted skew window.
                rate_limit = True

            # If there were 5 failed logins in the last 30 seconds, don't allow another one
            if _mfa_attempt_rate_limited(user.id):
                rate_limit = True

            if rate_limit:
                flash("⏲️ Please wait a moment before trying again.")
                return render_mfa(), 429

            if timecode is not None:
                auth_log = AuthenticationLog(
                    user_id=user.id, successful=True, otp_code=verification_code, timecode=timecode
                )
                try:
                    return redirect(
                        _complete_pending_login(
                            user,
                            auth_log,
                            authentication_method=TOTP_MFA_METHOD,
                        )
                    )
                except PendingLoginStateError:
                    flash("⛔️ This login was already completed. Please log in again.")
                    return redirect(url_for("login"))

            auth_log = AuthenticationLog(user_id=user.id, successful=False)
            db.session.add(auth_log)
            db.session.commit()

            flash("⛔️ Invalid 2FA code. Please try again.")
            return render_mfa(), 401

        return render_mfa()

    @app.post("/verify-recovery-code-login")
    def verify_recovery_code_login() -> Response | str | tuple[Response | str, int]:
        user = get_session_user()
        if user is None or session.get("is_authenticated", False):
            clear_auth_session()
            return redirect(url_for("login"))
        if RECOVERY_CODE_MFA_METHOD not in _pending_mfa_methods(user):
            clear_auth_session()
            flash("⛔️ Recovery code verification is not permitted for this login.")
            return redirect(url_for("login"))

        form = RecoveryCodeLoginForm()

        def render_recovery_challenge() -> Response:
            pending_methods = _pending_mfa_methods(user)
            response = make_response(
                render_template(
                    "verify_2fa_login.html",
                    form=TwoFactorForm(),
                    allow_totp=TOTP_MFA_METHOD in pending_methods and bool(user.totp_secret),
                    allow_security_key=SECURITY_KEY_MFA_METHOD in pending_methods
                    and any(
                        credential.disabled_at is None for credential in user.webauthn_credentials
                    ),
                    allow_recovery_code=True,
                    recovery_code_form=form,
                )
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        if not form.validate_on_submit():
            if form.errors.get("csrf_token"):
                return make_response("Invalid CSRF token.", HTTPStatus.BAD_REQUEST)
            db.session.add(AuthenticationLog(user_id=user.id, successful=False))
            db.session.commit()
            flash("⛔️ Invalid recovery code. Please try again.")
            form.recovery_code.data = ""
            return render_recovery_challenge(), HTTPStatus.UNAUTHORIZED.value
        if _mfa_attempt_rate_limited(user.id):
            flash("⏲️ Please wait a moment before trying again.")
            form.recovery_code.data = ""
            return render_recovery_challenge(), HTTPStatus.TOO_MANY_REQUESTS.value

        if not consume_recovery_code(user_id=user.id, value=form.recovery_code.data):
            db.session.add(AuthenticationLog(user_id=user.id, successful=False))
            db.session.commit()
            flash("⛔️ Invalid recovery code. Please try again.")
            form.recovery_code.data = ""
            return render_recovery_challenge(), HTTPStatus.UNAUTHORIZED.value

        try:
            return redirect(
                _complete_pending_login(
                    user,
                    AuthenticationLog(user_id=user.id, successful=True),
                    authentication_method=RECOVERY_CODE_MFA_METHOD,
                )
            )
        except PendingLoginStateError:
            flash("⛔️ This login was already completed. Please log in again.")
            return redirect(url_for("login"))

    @app.post("/verify-security-key-login/options")
    def security_key_login_options() -> Response | tuple[Response, int]:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnConfigurationError,
            WebAuthnRateLimitError,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _json_csrf_error()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)
        user = get_session_user()
        if user is None or session.get("is_authenticated", False):
            return _json_error("This login is no longer pending.", HTTPStatus.UNAUTHORIZED)
        if SECURITY_KEY_MFA_METHOD not in _pending_mfa_methods(user) or not any(
            credential.disabled_at is None for credential in user.webauthn_credentials
        ):
            return _json_error(
                "Security key verification is not permitted for this login.",
                HTTPStatus.FORBIDDEN,
            )

        try:
            options = WebAuthnCeremonyService.begin_authentication(
                user=user,
                session_binding=current_webauthn_session_binding(),
            )
        except WebAuthnRateLimitError:
            return _json_error(
                "Too many security key attempts. Please wait and try again.",
                HTTPStatus.TOO_MANY_REQUESTS,
            )
        except WebAuthnConfigurationError:
            return _json_error(
                "Security key verification is temporarily unavailable.",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except WebAuthnServiceError:
            return _json_error(
                "Security key verification could not be started.",
                HTTPStatus.BAD_REQUEST,
            )

        response = make_response(options)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/verify-security-key-login")
    def verify_security_key_login() -> Response | tuple[Response, int]:
        from hushline.webauthn import (
            WebAuthnCeremonyService,
            WebAuthnServiceError,
            current_webauthn_session_binding,
        )

        csrf_error = _json_csrf_error()
        if csrf_error:
            return _json_error(csrf_error, HTTPStatus.BAD_REQUEST)
        user = get_session_user()
        if user is None or session.get("is_authenticated", False):
            return _json_error("This login is no longer pending.", HTTPStatus.UNAUTHORIZED)
        if SECURITY_KEY_MFA_METHOD not in _pending_mfa_methods(user) or not any(
            credential.disabled_at is None for credential in user.webauthn_credentials
        ):
            return _json_error(
                "Security key verification is not permitted for this login.",
                HTTPStatus.FORBIDDEN,
            )

        payload = request.get_json(silent=True)
        credential_response = payload.get("credential") if isinstance(payload, dict) else None
        if not isinstance(credential_response, dict):
            return _json_error("Security key response is invalid.", HTTPStatus.BAD_REQUEST)

        try:
            WebAuthnCeremonyService.finish_authentication(
                user=user,
                session_binding=current_webauthn_session_binding(),
                response=credential_response,
            )
        except WebAuthnServiceError:
            db.session.add(AuthenticationLog(user_id=user.id, successful=False))
            db.session.commit()
            return _json_error(
                "The security key could not be verified. Please try again.",
                HTTPStatus.UNAUTHORIZED,
            )

        try:
            redirect_target = _complete_pending_login(
                user,
                AuthenticationLog(user_id=user.id, successful=True),
                authentication_method=SECURITY_KEY_MFA_METHOD,
            )
        except PendingLoginStateError:
            return _json_error("This login is no longer pending.", HTTPStatus.UNAUTHORIZED)
        response = make_response({"redirect": redirect_target})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/logout")
    @authentication_required
    def logout() -> Response:
        user = get_session_user()
        if user:
            rotate_user_session_id(user)
            db.session.commit()

        session.clear()
        flash("👋 You have been logged out successfully.", "info")
        response = make_response(redirect(url_for("index")))
        response.headers["Clear-Site-Data"] = '"*"'
        return response

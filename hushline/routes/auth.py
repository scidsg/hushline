import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new

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
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, MultipleResultsFound
from werkzeug.wrappers.response import Response

from hushline.auth import (
    PENDING_PASSWORD_REHASH_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY,
    authentication_required,
    clear_auth_session,
    get_session_user,
    pop_post_auth_redirect,
    rotate_user_session_id,
    set_session_user,
)
from hushline.db import db
from hushline.external_urls import canonical_external_url
from hushline.model import (
    AuthenticationLog,
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
from hushline.routes.common import send_email_to_user_recipients, validate_captcha
from hushline.routes.forms import (
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RegistrationForm,
    TwoFactorForm,
)

PASSWORD_RESET_CONFIRMATION_MESSAGE = (
    "If an eligible account exists, reset instructions will be sent."  # noqa: S105
)
PASSWORD_RESET_INVALID_LINK_MESSAGE = (
    "Password reset links expire quickly and can only be used once. Request a new reset if needed."  # noqa: S105
)


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
    username = _find_primary_username(identifier)
    if username is None:
        return None

    user = username.user
    if not user.enable_email_notifications or not user.enabled_notification_recipients:
        return None
    return user


def _send_password_reset_email(user: User, raw_token: str) -> None:
    reset_url = canonical_external_url("reset_password", token=raw_token)
    body = (
        "A password reset was requested for your Hush Line account.\n\n"
        f"Use this link to set a new password: {reset_url}\n\n"
        "This link expires quickly and can only be used once. "
        "If you did not request this reset, ignore this email."
    )
    send_email_to_user_recipients(user, "Hush Line password reset", body)


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
    @app.route("/register", methods=["GET", "POST"])
    def register() -> Response | str:
        if session.get("is_authenticated", False) and get_session_user():
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

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
            first_user = db.session.query(User).count() == 0
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
                rotate_user_session_id(user)

                # 2FA enabled?
                if user.totp_secret:
                    set_session_user(user=user, username=username.username, is_authenticated=False)
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

                set_session_user(user=user, username=username.username, is_authenticated=True)

                auth_log = AuthenticationLog(user_id=user.id, successful=True)
                db.session.add(auth_log)
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

            if user := _eligible_password_reset_user(identifier):
                now = _now()
                _invalidate_password_reset_tokens(user, used_at=now)
                reset_token, raw_token = PasswordResetToken.create_for_user(
                    user.id,
                    ttl=_password_reset_ttl(),
                )
                db.session.add(reset_token)
                db.session.commit()
                _send_password_reset_email(user, raw_token)

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

        form = TwoFactorForm()

        if request.method == "POST" and form.validate():
            if not user.totp_secret:
                flash("⛔️ 2FA is not enabled.")
                return redirect(url_for("login"))

            totp = pyotp.TOTP(user.totp_secret)
            timecode = totp.timecode(datetime.now())
            verification_code = form.verification_code.data

            rate_limit = False

            # If the most recent successful login was made with the same OTP code, reject this one
            last_login = db.session.scalars(
                db.select(AuthenticationLog)
                .filter_by(user_id=user.id, successful=True)
                .order_by(AuthenticationLog.timestamp.desc())
                .limit(1)
            ).first()
            if (
                last_login
                and last_login.timecode == timecode
                and last_login.otp_code == verification_code
            ):
                # If the time interval has incremented, then a repeat TOTP code which passes the
                # totp.verify(...) check is OK & part of the security model of the TOTP spec.
                # However, a repeat TOTP code during the same time interval should be disallowed.
                rate_limit = True

            # If there were 5 failed logins in the last 30 seconds, don't allow another one
            failed_logins = db.session.scalar(
                db.select(
                    db.func.count(AuthenticationLog.id)
                    .filter(AuthenticationLog.user_id == user.id)
                    .filter(AuthenticationLog.successful == db.false())
                    .filter(AuthenticationLog.timestamp > datetime.now() - timedelta(seconds=30))
                )
            )
            if failed_logins is not None and failed_logins >= 5:  # noqa: PLR2004
                rate_limit = True

            if rate_limit:
                flash("⏲️ Please wait a moment before trying again.")
                return render_template("verify_2fa_login.html", form=form), 429

            if totp.verify(verification_code, valid_window=1):
                auth_log = AuthenticationLog(
                    user_id=user.id, successful=True, otp_code=verification_code, timecode=timecode
                )
                db.session.add(auth_log)
                session["is_authenticated"] = True
                password_rehash_source_hash = user.password_hash
                has_pending_password_rehash = PENDING_PASSWORD_REHASH_SESSION_KEY in session
                try:
                    _apply_pending_password_rehash(user, source_hash=password_rehash_source_hash)
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

                if not user.onboarding_complete:
                    return redirect(url_for("onboarding"))

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
                    return redirect(url_for("premium.select_tier"))

                return redirect(pop_post_auth_redirect())

            auth_log = AuthenticationLog(user_id=user.id, successful=False)
            db.session.add(auth_log)
            db.session.commit()

            flash("⛔️ Invalid 2FA code. Please try again.")
            return render_template("verify_2fa_login.html", form=form), 401

        return render_template("verify_2fa_login.html", form=form)

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

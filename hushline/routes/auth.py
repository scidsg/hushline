import secrets
from datetime import UTC, datetime, timedelta

import pyotp
from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func
from werkzeug.wrappers.response import Response

from hushline.auth import (
    authentication_required,
    clear_auth_session,
    get_session_user,
    rotate_user_session_id,
    set_session_user,
)
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    InviteCode,
    OrganizationSetting,
    User,
    Username,
)
from hushline.routes.forms import LoginForm, RegistrationForm, TwoFactorForm


def register_auth_routes(app: Flask) -> None:
    @app.route("/register", methods=["GET", "POST"])
    def register() -> Response | str:
        if session.get("is_authenticated", False) and get_session_user():
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

        # Check if this is the first user
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

        # Generate a math CAPTCHA only for a GET request or if "math_answer" is not already set
        if request.method == "GET" or "math_answer" not in session:
            num1 = secrets.randbelow(10) + 1
            num2 = secrets.randbelow(10) + 1
            session["math_answer"] = str(num1 + num2)  # Store the answer in session
            math_problem = f"{num1} + {num2} ="
            session["math_problem"] = math_problem  # Store the problem in session
        else:
            # Use the existing math problem from the session
            math_problem = session.get("math_problem", "Error: CAPTCHA not generated.")

        if form.validate_on_submit():
            captcha_answer = request.form.get("captcha_answer", "")
            app.logger.debug(f"Session math_answer: {session.get('math_answer')}")
            app.logger.debug(f"User entered captcha_answer: {captcha_answer}")

            if str(captcha_answer) != session.get("math_answer"):
                flash("Incorrect CAPTCHA. Please try again.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    math_problem=math_problem,
                    first_user=first_user,
                )

            # Proceed with registration logic
            username = form.username.data
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
                .where(func.lower(Username._username) == username.lower())
                .select()
            ):
                flash("💔 Username already taken.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    math_problem=math_problem,
                    first_user=first_user,
                )

            user = User(password=password)

            # If this is the first user, set them as admin
            if first_user:
                user.is_admin = True

            db.session.add(user)
            db.session.flush()

            username = Username(_username=username, user_id=user.id, is_primary=True)

            # If this is the first user, show them in the directory
            if first_user:
                username.show_in_directory = True

            db.session.add(username)
            db.session.commit()

            username.create_default_field_defs()

            if invite_code_input:
                # Delete the invite code after use
                db.session.delete(invite_code)
                db.session.commit()

            flash("Registration successful!", "success")
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
        if form.validate_on_submit():
            username = db.session.scalars(
                db.select(Username).where(
                    func.lower(Username._username) == form.username.data.strip().lower(),
                    Username.is_primary.is_(True),
                )
            ).one_or_none()
            if username and username.user.check_password(form.password.data):
                user = username.user
                rotate_user_session_id(user)

                # 2FA enabled?
                if user.totp_secret:
                    set_session_user(user=user, username=username.username, is_authenticated=False)
                    db.session.commit()
                    return redirect(url_for("verify_2fa_login"))

                set_session_user(user=user, username=username.username, is_authenticated=True)

                auth_log = AuthenticationLog(user_id=user.id, successful=True)
                db.session.add(auth_log)
                db.session.commit()

                if not user.onboarding_complete:
                    return redirect(url_for("onboarding"))

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
                    return redirect(url_for("premium.select_tier"))

                return redirect(url_for("inbox"))

            flash("⛔️ Invalid username or password")
        return render_template("login.html", form=form)

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

        if form.validate_on_submit():
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
                db.session.commit()

                session["is_authenticated"] = True

                if not user.onboarding_complete:
                    return redirect(url_for("onboarding"))

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config.get("STRIPE_SECRET_KEY") and user.tier_id is None:
                    return redirect(url_for("premium.select_tier"))

                return redirect(url_for("inbox"))

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

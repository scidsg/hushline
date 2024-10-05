import logging
import re
import secrets
import socket
from datetime import UTC, datetime, timedelta
from typing import Sequence

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
from flask_wtf import FlaskForm
from werkzeug.wrappers.response import Response
from wtforms import Field, Form, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from .crypto import decrypt_field, encrypt_field, encrypt_message, generate_salt
from .db import db
from .forms import ComplexPassword
from .model import AuthenticationLog, InviteCode, Message, SMTPEncryption, User, Username
from .utils import SMTPConfig, authentication_required, create_smtp_config, send_email

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


def valid_username(form: Form, field: Field) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


class MessageForm(FlaskForm):
    contact_method = StringField(
        "Contact Method",
        validators=[Optional(), Length(max=255)],  # Optional if you want it to be non-mandatory
    )
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
    )


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=25), valid_username]
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )
    invite_code = StringField("Invite Code", validators=[DataRequired(), Length(min=6, max=25)])


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


def validate_captcha(captcha_answer: str) -> bool:
    if not captcha_answer.isdigit():
        flash("Incorrect CAPTCHA. Please enter a valid number.", "error")
        return False

    if captcha_answer != session.get("math_answer"):
        flash("Incorrect CAPTCHA. Please try again.", "error")
        return False

    return True


def get_ip_address() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 1))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = "127.0.0.1"
    finally:
        s.close()
    return ip_address


def init_app(app: Flask) -> None:
    @app.route("/")
    def index() -> Response:
        if "user_id" in session:
            user = db.session.get(User, session.get("user_id"))
            if user:
                return redirect(url_for("inbox"))

            flash("🫥 User not found. Please log in again.")
            session.pop("user_id", None)  # Clear the invalid user_id from session
            return redirect(url_for("login"))

        return redirect(url_for("directory"))

    @app.route("/inbox")
    @authentication_required
    def inbox() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("👉 Please log in to access your inbox.")
            return redirect(url_for("login"))

        return render_template(
            "inbox.html",
            user=user,
            is_personal_server=app.config["IS_PERSONAL_SERVER"],
        )

    @app.route("/to/<username>", methods=["GET"])
    def profile(username: str) -> Response | str:
        form = MessageForm()
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        # If the encrypted message is stored in the session, use it to populate the form
        scope = "submit_message"
        if (
            f"{scope}:salt" in session
            and f"{scope}:contact_method" in session
            and f"{scope}:content" in session
        ):
            try:
                form.contact_method.data = decrypt_field(
                    session[f"{scope}:contact_method"], scope, session[f"{scope}:salt"]
                )
                form.content.data = decrypt_field(
                    session[f"{scope}:content"], scope, session[f"{scope}:salt"]
                )
            except Exception:
                app.logger.error("Error decrypting content", exc_info=True)

            session.pop(f"{scope}:contact_method", None)
            session.pop(f"{scope}:content", None)
            session.pop(f"{scope}:salt", None)

        # Generate a simple math problem using secrets module (e.g., "What is 6 + 7?")
        num1 = secrets.randbelow(10) + 1
        num2 = secrets.randbelow(10) + 1
        math_problem = f"{num1} + {num2} ="
        session["math_answer"] = str(num1 + num2)  # Store the answer in session as a string

        return render_template(
            "profile.html",
            form=form,
            user=uname.user,
            username=uname,
            display_name_or_username=uname.display_name or uname.username,
            current_user_id=session.get("user_id"),
            public_key=uname.user.pgp_key,
            is_personal_server=app.config["IS_PERSONAL_SERVER"],
            require_pgp=app.config["REQUIRE_PGP"],
            math_problem=math_problem,
        )

    @app.route("/to/<username>", methods=["POST"])
    def submit_message(username: str) -> Response | str:
        form = MessageForm()
        uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one_or_none()
        if not uname:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        if form.validate_on_submit():
            if not uname.user.pgp_key and app.config["REQUIRE_PGP"]:
                flash("⛔️ You cannot submit messages to users who have not set a PGP key.", "error")
                return redirect(url_for("profile", username=username))

            captcha_answer = request.form.get("captcha_answer", "")
            if not validate_captcha(captcha_answer):
                # Encrypt the message and store it in the session
                scope = "submit_message"
                salt = generate_salt()
                session[f"{scope}:contact_method"] = encrypt_field(
                    form.contact_method.data, scope, salt
                )
                session[f"{scope}:content"] = encrypt_field(form.content.data, scope, salt)
                session[f"{scope}:salt"] = salt

                return redirect(url_for("profile", username=username))

            content = form.content.data
            contact_method = form.contact_method.data.strip() if form.contact_method.data else ""
            full_content = (
                f"Contact Method: {contact_method}\n\n{content}" if contact_method else content
            )
            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            if client_side_encrypted:
                content_to_save = (
                    content  # Assume content is already encrypted and includes contact method
                )
            elif uname.user.pgp_key:
                try:
                    encrypted_content = encrypt_message(full_content, uname.user.pgp_key)
                    if not encrypted_content:
                        flash("⛔️ Failed to encrypt message.", "error")
                        return redirect(url_for("profile", username=username))
                    content_to_save = encrypted_content
                except Exception as e:
                    app.logger.error("Encryption failed: %s", str(e), exc_info=True)
                    flash("⛔️ Failed to encrypt message.", "error")
                    return redirect(url_for("profile", username=username))
            else:
                content_to_save = full_content

            new_message = Message(content=content_to_save, username_id=uname.id)
            db.session.add(new_message)
            db.session.commit()

            if uname.user.email and content_to_save:
                try:
                    smtp_config: SMTPConfig = create_smtp_config(
                        app.config["SMTP_USERNAME"],
                        app.config["SMTP_SERVER"],
                        app.config["SMTP_PORT"],
                        app.config["SMTP_PASSWORD"],
                        app.config["NOTIFICATIONS_ADDRESS"],
                        encryption=SMTPEncryption[app.config["SMTP_ENCRYPTION"]],
                    )
                    if uname.user.smtp_server:
                        smtp_config = create_smtp_config(
                            uname.user.smtp_username,
                            uname.user.smtp_server,
                            uname.user.smtp_port,
                            uname.user.smtp_password,
                            uname.user.smtp_sender,
                            encryption=uname.user.smtp_encryption,
                        )

                    email_sent = send_email(
                        uname.user.email, "New Message", content_to_save, smtp_config
                    )
                    flash_message = (
                        "👍 Message submitted successfully."
                        if email_sent
                        else "👍 Message submitted successfully."
                    )
                    flash(flash_message)
                except Exception as e:
                    app.logger.error(f"Error sending email: {str(e)}", exc_info=True)
                    flash("👍 Message submitted successfully.", "warning")
            else:
                flash("👍 Message submitted successfully.")

        return redirect(url_for("profile", username=username))

    # Redirect from the old route, /submit_message/<username>, to the new route, /to/<username>
    @app.route("/submit_message/<username>", methods=["GET"])
    def redirect_submit_message(username: str) -> Response:
        return redirect(url_for("profile", username=username), 301)

    @app.route("/delete_message/<int:message_id>", methods=["POST"])
    @authentication_required
    def delete_message(message_id: int) -> Response:
        if "user_id" not in session:
            flash("🔑 Please log in to continue.")
            return redirect(url_for("login"))

        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("🫥 User not found. Please log in again.")
            return redirect(url_for("login"))

        row_count = db.session.execute(
            db.delete(Message).where(
                Message.id == message_id,
                Message.username_id.in_(
                    db.select(Username.user_id)
                    .select_from(Username)
                    .filter(Username.user_id == user.id)
                ),
            )
        ).rowcount
        match row_count:
            case 1:
                db.session.commit()
                flash("🗑️ Message deleted successfully.")
            case 0:
                db.session.rollback()
                flash("⛔️ Message not found.")
            case _:
                db.session.rollback()
                current_app.logger.error(
                    f"Multiple messages would have been deleted. Message.id={message_id}"
                )
                flash("Internal server error. Message not deleted.")

        return redirect(url_for("inbox"))

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Response | str | tuple[Response | str, int]:
        if (
            session.get("is_authenticated", False)
            and (user_id := session.get("user_id", False))
            and db.session.get(User, user_id)
        ):
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

        require_invite_code = app.config["REGISTRATION_CODES_REQUIRED"]
        form = RegistrationForm()
        if not require_invite_code:
            del form.invite_code

        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data

            invite_code_input = form.invite_code.data if require_invite_code else None
            if invite_code_input:
                invite_code = db.session.scalars(
                    db.select(InviteCode).filter_by(code=invite_code_input)
                ).one_or_none()
                if not invite_code or invite_code.expiration_date.replace(
                    tzinfo=UTC
                ) < datetime.now(UTC):
                    flash("⛔️ Invalid or expired invite code.", "error")
                    return (
                        render_template(
                            "register.html",
                            form=form,
                            require_invite_code=require_invite_code,
                        ),
                        400,
                    )

            if db.session.scalar(
                db.exists(Username).where(Username._username == username).select()
            ):
                flash("💔 Username already taken.", "error")
                return (
                    render_template(
                        "register.html",
                        form=form,
                        require_invite_code=require_invite_code,
                    ),
                    409,
                )

            user = User(password=password)
            db.session.add(user)
            db.session.flush()

            username = Username(_username=username, user_id=user.id, is_primary=True)
            db.session.add(username)
            db.session.commit()

            flash("Registration successful!", "success")
            return redirect(url_for("login"))

        return render_template(
            "register.html",
            form=form,
            require_invite_code=require_invite_code,
            is_personal_server=app.config["IS_PERSONAL_SERVER"],
        )

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Response | str:
        if "user_id" in session and session.get("is_authenticated", False):
            flash("👉 You are already logged in.")
            return redirect(url_for("inbox"))

        form = LoginForm()
        if form.validate_on_submit():
            username = db.session.scalars(
                db.select(Username).filter_by(_username=form.username.data.strip(), is_primary=True)
            ).one_or_none()
            if username and username.user.check_password(form.password.data):
                session.permanent = True
                session["user_id"] = username.user_id
                session["username"] = username.username
                session["is_authenticated"] = True

                # 2FA enabled?
                if username.user.totp_secret:
                    session["is_authenticated"] = False
                    return redirect(url_for("verify_2fa_login"))

                auth_log = AuthenticationLog(user_id=username.user_id, successful=True)
                db.session.add(auth_log)
                db.session.commit()

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config["STRIPE_SECRET_KEY"]:
                    user = db.session.get(User, username.user_id)
                    if user and user.tier_id is None:
                        return redirect(url_for("premium.select_tier"))

                return redirect(url_for("inbox"))

            flash("⛔️ Invalid username or password")
        return render_template(
            "login.html",
            form=form,
            is_personal_server=app.config["IS_PERSONAL_SERVER"],
        )

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    def verify_2fa_login() -> Response | str | tuple[Response | str, int]:
        # Redirect to login if the login process has not started yet
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
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

                # If premium features are enabled, prompt the user to select a tier if they haven't
                if app.config["STRIPE_SECRET_KEY"] and user.tier_id is None:
                    return redirect(url_for("premium.select_tier"))

                return redirect(url_for("inbox"))

            auth_log = AuthenticationLog(user_id=user.id, successful=False)
            db.session.add(auth_log)
            db.session.commit()

            flash("⛔️ Invalid 2FA code. Please try again.")
            return render_template("verify_2fa_login.html", form=form), 401

        return render_template(
            "verify_2fa_login.html", form=form, is_personal_server=app.config["IS_PERSONAL_SERVER"]
        )

    @app.route("/logout")
    @authentication_required
    def logout() -> Response:
        session.clear()
        flash("👋 You have been logged out successfully.", "info")
        return redirect(url_for("index"))

    def get_directory_usernames(admin_first: bool = False) -> Sequence[Username]:
        query = db.select(Username).filter_by(show_in_directory=True)
        display_ordering = db.func.coalesce(Username._display_name, Username._username)
        if admin_first:
            query = query.order_by(Username.user.is_admin.desc(), display_ordering)
        else:
            query = query.order_by(display_ordering)
        return db.session.scalars(query).all()

    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        is_personal_server = app.config["IS_PERSONAL_SERVER"]
        return render_template(
            "directory.html",
            usernames=get_directory_usernames(),
            logged_in=logged_in,
            is_personal_server=is_personal_server,
        )

    @app.route("/directory/get-session-user.json")
    def session_user() -> dict[str, bool]:
        logged_in = "user_id" in session
        return {"logged_in": logged_in}

    @app.route("/directory/users.json")
    def directory_users() -> list[dict[str, str | bool | None]]:
        return [
            {
                "primary_username": username.username,
                "display_name": username.display_name or username.username,
                "bio": username.bio,
                "is_admin": username.user.is_admin,
                "is_verified": username.is_verified,
            }
            for username in get_directory_usernames()
        ]

    @app.route("/vision", methods=["GET"])
    def vision() -> str:
        return render_template("vision.html")

    @app.route("/info")
    def personal_server_info() -> Response:
        if app.config.get("IS_PERSONAL_SERVER"):
            ip_address = get_ip_address()
            return make_response(
                render_template(
                    "personal_server_info.html", is_personal_server=True, ip_address=ip_address
                )
            )
        return Response(status=404)

    @app.route("/health.json")
    def health() -> dict[str, str]:
        return {"status": "ok"}

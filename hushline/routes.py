import logging
import re
import secrets
import socket
from datetime import UTC, datetime, timedelta
from typing import Sequence

import pyotp
from flask import (
    Flask,
    abort,
    current_app,
    flash,
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

from .auth import authentication_required
from .crypto import decrypt_field, encrypt_field, encrypt_message, generate_salt
from .db import db
from .email import create_smtp_config, send_email
from .forms import ComplexPassword, DeleteMessageForm, UpdateMessageStatusForm
from .model import (
    AuthenticationLog,
    InviteCode,
    Message,
    OrganizationSetting,
    SMTPEncryption,
    User,
    Username,
)

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


def valid_username(form: Form, field: Field) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )


def get_directory_usernames() -> Sequence[Username]:
    return db.session.scalars(
        db.select(Username)
        .join(User)
        .filter(Username.show_in_directory.is_(True))
        .order_by(
            User.is_admin.desc(),
            db.func.coalesce(Username._display_name, Username._username),
        )
    ).all()


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


def do_send_email(user: User, content_to_save: str) -> None:
    if user.email and content_to_save:
        try:
            if user.smtp_server:
                smtp_config = create_smtp_config(
                    user.smtp_username,  # type: ignore[arg-type]
                    user.smtp_server,  # type: ignore[arg-type]
                    user.smtp_port,  # type: ignore[arg-type]
                    user.smtp_password,  # type: ignore[arg-type]
                    user.smtp_sender,  # type: ignore[arg-type]
                    encryption=user.smtp_encryption,
                )
            else:
                smtp_config = create_smtp_config(
                    current_app.config["SMTP_USERNAME"],
                    current_app.config["SMTP_SERVER"],
                    current_app.config["SMTP_PORT"],
                    current_app.config["SMTP_PASSWORD"],
                    current_app.config["NOTIFICATIONS_ADDRESS"],
                    encryption=SMTPEncryption[current_app.config["SMTP_ENCRYPTION"]],
                )

            send_email(user.email, "New Message", content_to_save, smtp_config)
        except Exception as e:
            current_app.logger.error(f"Error sending email: {str(e)}", exc_info=True)


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

        if homepage_username := OrganizationSetting.fetch_one(
            OrganizationSetting.HOMEPAGE_USER_NAME
        ):
            if db.session.scalar(
                db.exists(Username).where(Username._username == homepage_username).select()
            ):
                return redirect(url_for("profile", username=homepage_username))
            else:
                app.logger.warning(f"Homepage for username {homepage_username!r} not found")

        return redirect(url_for("directory"))

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

    @app.route("/to/<username>")
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

            do_send_email(uname.user, content_to_save)
            flash("👍 Message submitted successfully.")
            session["reply_slug"] = new_message.reply_slug
            return redirect(url_for("submission_success"))

        return redirect(url_for("profile", username=username))

    @app.route("/submit/success")
    def submission_success() -> Response | str:
        reply_slug = session.pop("reply_slug", None)
        if not reply_slug:
            current_app.logger.debug(
                "Attempted to access submission_success endpoint without a reply_slug in session"
            )
            return redirect(url_for("directory"))

        msg = db.session.scalars(
            db.session.query(Message).filter_by(reply_slug=reply_slug)
        ).one_or_none()
        if msg is None:
            abort(404)

        return render_template("submission_success.html", message=msg)

    @app.route("/reply/<slug>")
    def message_reply(slug: str) -> str:
        msg = db.session.scalars(db.select(Message).filter_by(reply_slug=slug)).one_or_none()
        if msg is None:
            abort(404)

        return render_template("reply.html", message=msg)

    @app.route("/message/<int:id>")
    @authentication_required
    def message(id: int) -> str:
        msg = db.session.scalars(
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == session["user_id"], Message.id == id)
        ).one_or_none()

        if not msg:
            abort(404)

        update_status_form = UpdateMessageStatusForm(data={"status": msg.status.value})
        delete_message_form = DeleteMessageForm()

        return render_template(
            "message.html",
            message=msg,
            update_status_form=update_status_form,
            delete_message_form=delete_message_form,
        )

    @app.route("/submit_message/<username>")
    def redirect_submit_message(username: str) -> Response:
        return redirect(url_for("profile", username=username), 301)

    @app.route("/message/<int:id>/delete", methods=["POST"])
    @authentication_required
    def delete_message(id: int) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        row_count = db.session.execute(
            db.delete(Message).where(
                Message.id == id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
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
                    f"Multiple messages would have been deleted. Message.id={id} User.id={user.id}"
                )
                flash("Internal server error. Message not deleted.")

        return redirect(url_for("inbox"))

    @app.route("/message/<int:id>/status", methods=["POST"])
    @authentication_required
    def set_message_status(id: int) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        form = UpdateMessageStatusForm()
        if not form.validate():
            flash(f"Invalid status: {form.status.data}")
            return redirect(url_for("message", id=id))

        row_count = db.session.execute(
            db.update(Message)
            .where(
                Message.id == id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
                ),
            )
            .values(status=form.status.data, status_changed_at=datetime.now(UTC))
        ).rowcount
        match row_count:
            case 1:
                db.session.commit()
                flash("👍 Message status updated.")
            case 0:
                db.session.rollback()
                flash("⛔️ Message not found.")
            case _:
                db.session.rollback()
                current_app.logger.error(
                    f"Multiple messages would have been updated. Message.id={id} User.id={user.id}"
                )
                flash("Internal server error. Message not updated.")
        return redirect(url_for("message", id=id))

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Response | str:
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
                    require_invite_code=require_invite_code,
                    math_problem=math_problem,
                )

            # Proceed with registration logic
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
                    return render_template(
                        "register.html",
                        form=form,
                        require_invite_code=require_invite_code,
                        math_problem=math_problem,
                    )

            if db.session.scalar(
                db.exists(Username).where(Username._username == username).select()
            ):
                flash("💔 Username already taken.", "error")
                return render_template(
                    "register.html",
                    form=form,
                    require_invite_code=require_invite_code,
                    math_problem=math_problem,
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
            math_problem=math_problem,
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
                if app.config.get("STRIPE_SECRET_KEY"):
                    user = db.session.get(User, username.user_id)
                    if user and user.tier_id is None:
                        return redirect(url_for("premium.select_tier"))

                return redirect(url_for("inbox"))

            flash("⛔️ Invalid username or password")
        return render_template("login.html", form=form)

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
        session.clear()
        flash("👋 You have been logged out successfully.", "info")
        return redirect(url_for("index"))

    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        return render_template(
            "directory.html",
            intro_text=OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT),
            usernames=get_directory_usernames(),
            logged_in=logged_in,
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

    @app.route("/vision")
    @authentication_required
    def vision() -> str | Response:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            flash("⛔️ Please log in to access this feature.")
            return redirect(url_for("login"))

        if not user.tier_id:  # Assuming tier_id is None for unpaid users
            flash("⛔️ This feature is only available to paid users.")
            return redirect(url_for("premium.select_tier"))

        return render_template("vision.html")

    @app.route("/info")
    def server_info() -> Response | str:
        return render_template("server_info.html", ip_address=get_ip_address())

    @app.route("/health.json")
    def health() -> dict[str, str]:
        return {"status": "ok"}

import logging
import os
import re
from datetime import datetime

import pyotp
from flask import (
    Flask,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from sqlalchemy import event
from sqlalchemy.engine.base import Connection
from sqlalchemy.orm import Mapper
from werkzeug.wrappers.response import Response
from wtforms import Field, Form, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from .crypto import encrypt_message
from .db import db
from .forms import ComplexPassword
from .limiter import limiter
from .model import InviteCode, Message, User
from .utils import generate_user_directory_json, require_2fa, send_email

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


def init_app(app: Flask) -> None:
    @app.route("/")
    @limiter.limit("120 per minute")
    def index() -> Response:
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            if user:
                return redirect(url_for("inbox", username=user.primary_username))

            flash("🫥 User not found. Please log in again.")
            session.pop("user_id", None)  # Clear the invalid user_id from session
            return redirect(url_for("login"))

        return redirect(url_for("directory"))

    @app.route("/inbox")
    @limiter.limit("120 per minute")
    @require_2fa
    def inbox() -> Response | str:
        # Redirect if not logged in
        if "user_id" not in session:
            flash("Please log in to access your inbox.")
            return redirect(url_for("login"))

        logged_in_user_id = session["user_id"]
        requested_username = request.args.get("username")
        logged_in_user = User.query.get(logged_in_user_id)
        if logged_in_user:
            logged_in_username = logged_in_user.primary_username

        if requested_username and requested_username != logged_in_username:
            return redirect(url_for("inbox"))

        primary_user = User.query.get(logged_in_user_id)
        if primary_user:
            messages = (
                Message.query.filter_by(user_id=primary_user.id).order_by(Message.id.desc()).all()
            )
            secondary_users_dict = {su.id: su for su in primary_user.secondary_usernames}

        return render_template(
            "inbox.html",
            user=primary_user,
            secondary_username=None,
            messages=messages,
            is_secondary=False,
            secondary_usernames=secondary_users_dict,
        )

    @app.route("/submit_message/<username>", methods=["GET", "POST"])
    def submit_message(username: str) -> Response | str:
        form = MessageForm()
        user = User.query.filter_by(primary_username=username).first()
        if not user:
            flash("User not found.")
            return redirect(url_for("index"))

        if form.validate_on_submit():
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
            elif user.pgp_key:
                try:
                    encrypted_content = encrypt_message(full_content, user.pgp_key)
                    if not encrypted_content:
                        flash("Failed to encrypt message with PGP key.", "error")
                        return redirect(url_for("submit_message", username=username))
                    content_to_save = encrypted_content
                except Exception as e:
                    app.logger.error("Encryption failed: %s", str(e), exc_info=True)
                    flash("Failed to encrypt message due to an error.", "error")
                    return redirect(url_for("submit_message", username=username))
            else:
                content_to_save = full_content

            new_message = Message(content=content_to_save, user_id=user.id)
            db.session.add(new_message)
            db.session.commit()

            if (
                user.email
                and user.smtp_server
                and user.smtp_port
                and user.smtp_username
                and user.smtp_password
                and content_to_save
            ):
                try:
                    sender_email = user.smtp_username
                    email_sent = send_email(
                        user.email, "New Message", content_to_save, user, sender_email
                    )
                    flash_message = (
                        "Message submitted and email sent successfully."
                        if email_sent
                        else "Message submitted, but failed to send email."
                    )
                    flash(flash_message)
                except Exception as e:
                    app.logger.error(f"Error sending email: {str(e)}", exc_info=True)
                    flash(
                        "Message submitted, but an error occurred while sending email.", "warning"
                    )
            else:
                flash("Message submitted successfully.")

            return redirect(url_for("submit_message", username=username))

        return render_template(
            "submit_message.html",
            form=form,
            user=user,
            username=username,
            display_name_or_username=user.display_name or user.primary_username,
            current_user_id=session.get("user_id"),
            public_key=user.pgp_key,
        )

    @app.route("/delete_message/<int:message_id>", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def delete_message(message_id: int) -> Response:
        if "user_id" not in session:
            flash("🔑 Please log in to continue.")
            return redirect(url_for("login"))

        user = User.query.get(session["user_id"])
        if not user:
            flash("🫥 User not found. Please log in again.")
            return redirect(url_for("login"))

        message = Message.query.get(message_id)
        if message and message.user_id == user.id:
            db.session.delete(message)
            db.session.commit()
            flash("🗑️ Message deleted successfully.")
            return redirect(url_for("inbox", username=user.primary_username))

        flash("⛔️ Message not found or unauthorized access.")
        return redirect(url_for("inbox", username=user.primary_username))

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def register() -> Response | str | tuple[Response | str, int]:
        require_invite_code = os.environ.get("REGISTRATION_CODES_REQUIRED", "True") == "True"
        form = RegistrationForm()
        if not require_invite_code:
            del form.invite_code

        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data

            invite_code_input = form.invite_code.data if require_invite_code else None
            if invite_code_input:
                invite_code = InviteCode.query.filter_by(code=invite_code_input).first()
                if not invite_code or invite_code.expiration_date < datetime.utcnow():
                    flash("⛔️ Invalid or expired invite code.", "error")
                    return (
                        render_template(
                            "register.html",
                            form=form,
                            require_invite_code=require_invite_code,
                        ),
                        400,
                    )

            if User.query.filter_by(primary_username=username).first():
                flash("💔 Username already taken.", "error")
                return (
                    render_template(
                        "register.html",
                        form=form,
                        require_invite_code=require_invite_code,
                    ),
                    409,
                )

            # Create new user instance
            new_user = User(primary_username=username)
            new_user.password_hash = password  # This triggers the password_hash setter
            db.session.add(new_user)
            db.session.commit()

            flash("👍 Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html", form=form, require_invite_code=require_invite_code)

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def login() -> Response | str:
        form = LoginForm()
        if request.method == "POST" and form.validate_on_submit():
            username = form.username.data.strip()
            password = form.password.data

            user = User.query.filter_by(primary_username=username).first()

            if user and user.check_password(password):
                session.permanent = True
                session["user_id"] = user.id
                session["username"] = user.primary_username
                session["is_authenticated"] = True
                session["2fa_required"] = user.totp_secret is not None
                session["2fa_verified"] = False
                session["is_admin"] = user.is_admin

                if user.totp_secret:
                    return redirect(url_for("verify_2fa_login"))

                session["2fa_verified"] = True
                return redirect(url_for("inbox", username=user.primary_username))

            flash("⛔️ Invalid username or password")
        return render_template("login.html", form=form)

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def verify_2fa_login() -> Response | str | tuple[Response | str, int]:
        # Redirect to login if user is not authenticated or 2FA is not required
        if "user_id" not in session or not session.get("2fa_required", False):
            flash("You need to log in first.")
            return redirect(url_for("login"))

        user = User.query.get(session["user_id"])
        if not user:
            flash("🫥 User not found. Please login again.")
            session.clear()  # Clearing the session for security
            return redirect(url_for("login"))

        form = TwoFactorForm()

        if form.validate_on_submit():
            verification_code = form.verification_code.data
            totp = pyotp.TOTP(user.totp_secret)
            if totp.verify(verification_code):
                session["2fa_verified"] = True  # Set 2FA verification flag
                return redirect(url_for("inbox", username=user.primary_username))

            flash("⛔️ Invalid 2FA code. Please try again.")
            return render_template("verify_2fa_login.html", form=form), 401

        return render_template("verify_2fa_login.html", form=form)

    @app.route("/logout")
    @limiter.limit("120 per minute")
    @require_2fa
    def logout() -> Response:
        # Explicitly remove specific session keys related to user authentication
        session.pop("user_id", None)
        session.pop("2fa_verified", None)

        # Clear the entire session to ensure no leftover data
        session.clear()

        # Flash a confirmation message for the user
        flash("👋 You have been logged out successfully.", "info")

        # Redirect to the login page or home page after logout
        return redirect(url_for("index"))

    @app.route("/settings/update_directory_visibility", methods=["POST"])
    def update_directory_visibility() -> Response:
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            if user:
                user.show_in_directory = "show_in_directory" in request.form
            db.session.commit()
            flash("Directory visibility updated.")
        else:
            flash("You need to be logged in to update settings.")
        return redirect(url_for("settings.index"))

    def sort_users_by_display_name(users: list[User], admin_first: bool = True) -> list[User]:
        if admin_first:
            # Sorts admins to the top, then by display name or username
            return sorted(
                users,
                key=lambda u: (
                    not u.is_admin,
                    (u.display_name or u.primary_username).strip().lower(),
                ),
            )

        # Sorts only by display name or username
        return sorted(users, key=lambda u: (u.display_name or u.primary_username).strip().lower())

    @app.route("/directory")
    def directory() -> Response | str:
        logged_in = "user_id" in session
        users = User.query.all()  # Fetch all users
        sorted_users = sort_users_by_display_name(
            users, admin_first=True
        )  # Sort users in Python with admins first
        return render_template("directory.html", users=sorted_users, logged_in=logged_in)

    @event.listens_for(User, "after_update")
    def receive_after_update(mapper: Mapper, connection: Connection, target: User) -> None:
        current_app.logger.info("Triggering JSON regeneration due to user update/insert")
        generate_user_directory_json()

    @app.route("/health.json")
    def health() -> Response:
        return {"status": "ok"}

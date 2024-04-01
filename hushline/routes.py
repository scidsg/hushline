import logging
import os
from datetime import datetime

import pyotp
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length

from .crypto import encrypt_message
from .db import db
from .ext import bcrypt, limiter
from .forms import ComplexPassword
from .model import InviteCode, Message, SecondaryUsername, User
from .utils import require_2fa, send_email

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


class MessageForm(FlaskForm):
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
        render_kw={"placeholder": "Include a contact method if you want a response..."},
    )


class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=4, max=25)])
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
            else:
                # Handle case where user ID in session does not exist in the database
                flash("🫥 User not found. Please log in again.")
                session.pop("user_id", None)  # Clear the invalid user_id from session
                return redirect(url_for("login"))
        else:
            return redirect(url_for("login"))

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
        logged_in_username = User.query.get(logged_in_user_id).primary_username

        if requested_username and requested_username != logged_in_username:
            return redirect(url_for("inbox"))

        primary_user = User.query.get(logged_in_user_id)
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
    @limiter.limit("120 per minute")
    def submit_message(username: str) -> Response | str:
        form = MessageForm()
        user = None
        secondary_username = None
        display_name_or_username = ""

        primary_user = User.query.filter_by(primary_username=username).first()
        if primary_user:
            user = primary_user
            display_name_or_username = primary_user.display_name or primary_user.primary_username
        else:
            secondary_username = SecondaryUsername.query.filter_by(username=username).first()
            if secondary_username:
                user = secondary_username.primary_user
                display_name_or_username = (
                    secondary_username.display_name or secondary_username.username
                )

        if not user:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        if form.validate_on_submit():
            content = form.content.data
            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            if not client_side_encrypted and user.pgp_key:
                encrypted_content = encrypt_message(content, user.pgp_key)
                email_content = encrypted_content if encrypted_content else content
                if not encrypted_content:
                    flash("⛔️ Failed to encrypt message with PGP key.", "error")
                    return redirect(url_for("submit_message", username=username))
            else:
                email_content = content

            new_message = Message(
                content=email_content,
                user_id=user.id,
                secondary_user_id=secondary_username.id if secondary_username else None,
            )
            db.session.add(new_message)
            db.session.commit()

            if (
                user.email
                and user.smtp_server
                and user.smtp_port
                and user.smtp_username
                and user.smtp_password
                and email_content
            ):
                try:
                    sender_email = user.smtp_username
                    email_sent = send_email(
                        user.email, "New Message", email_content, user, sender_email
                    )
                    flash_message = (
                        "👍 Message submitted and email sent successfully."
                        if email_sent
                        else "👍 Message submitted, but failed to send email."
                    )
                    flash(flash_message)
                except Exception as e:
                    flash(
                        "👍 Message submitted, but an error occurred while sending email.",
                        "warning",
                    )
                    app.logger.error(f"Error sending email: {str(e)}")
            else:
                flash("👍 Message submitted successfully.")

            return redirect(url_for("submit_message", username=username))

        return render_template(
            "submit_message.html",
            form=form,
            user=user,
            secondary_username=secondary_username if secondary_username else None,
            username=username,
            display_name_or_username=display_name_or_username,
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
        else:
            flash("⛔️ Message not found or unauthorized access.")

        return redirect(url_for("inbox", username=user.primary_username))

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def register() -> Response | str:
        # TODO this should be a setting pulled from `current_app`
        require_invite_code = os.environ.get("REGISTRATION_CODES_REQUIRED", "True") == "True"

        form = RegistrationForm()

        # TODO don't dynamically remove the form field. instead use a custom renderer and validator
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
                    return redirect(url_for("register"))

            if User.query.filter_by(primary_username=username).first():
                flash("💔 Username already taken.", "error")
                return redirect(url_for("register"))

            password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
            new_user = User(primary_username=username, password_hash=password_hash)
            db.session.add(new_user)
            db.session.commit()

            flash("👍 Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html", form=form, require_invite_code=require_invite_code)

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def login() -> Response | str:
        form = LoginForm()
        if request.method == "POST":  # Ensure we're processing form submissions
            if form.validate_on_submit():
                username = form.username.data.strip()
                password = form.password.data

                user = User.query.filter_by(primary_username=username).first()

                if user and bcrypt.check_password_hash(user.password_hash, password):
                    session.permanent = True
                    session["user_id"] = user.id
                    session["username"] = user.primary_username
                    session["is_authenticated"] = True
                    session["2fa_required"] = user.totp_secret is not None
                    session["2fa_verified"] = False
                    session["is_admin"] = user.is_admin

                    if user.totp_secret:
                        return redirect(url_for("verify_2fa_login"))
                    else:
                        session["2fa_verified"] = True
                        return redirect(url_for("inbox", username=user.primary_username))
                else:
                    flash("⛔️ Invalid username or password")
            else:
                flash("⛔️ Invalid form data")

        # GET requests will reach this point without triggering the flash messages
        return render_template("login.html", form=form)

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def verify_2fa_login() -> Response | str:
        # Redirect to login if user is not authenticated
        if "user_id" not in session or not session.get("2fa_required", False):
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
            else:
                flash("⛔️ Invalid 2FA code. Please try again.")

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

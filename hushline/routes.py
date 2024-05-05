import logging
import os
import re
from datetime import datetime

import pyotp
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, ValidationError

from .crypto import encrypt_message
from .db import db
from .ext import limiter
from .forms import ComplexPassword
from .model import InviteCode, Message, User
from .utils import require_2fa, send_email

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")


def valid_username(form, field):
    if not re.match(r"^[a-zA-Z0-9_-]+$", field.data):
        raise ValidationError(
            "Username must contain only letters, numbers, underscores, or hyphens."
        )


class TwoFactorForm(FlaskForm):
    verification_code = StringField("2FA Code", validators=[DataRequired(), Length(min=6, max=6)])


class MessageForm(FlaskForm):
    content = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=10000)],
        render_kw={"placeholder": "Include a contact method if you want a response..."},
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
            else:
                flash("🫥 User not found. Please log in again.")
                session.pop("user_id", None)  # Clear the invalid user_id from session
                return redirect(url_for("login"))
        else:
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
        # Initialize the form
        form = MessageForm()

        # Retrieve the user details
        user = User.query.filter_by(primary_username=username).first()
        if not user:
            flash("🫥 User not found.")
            return redirect(url_for("index"))

        # Decide the display name or username
        display_name_or_username = user.display_name or user.primary_username

        # Check if there is a prefill content
        prefill_content = request.args.get("prefill", "")
        if prefill_content:
            # Pre-fill the form with the content if provided
            form.content.data = prefill_content

        # Process form submission
        if form.validate_on_submit():
            content = form.content.data
            client_side_encrypted = request.form.get("client_side_encrypted", "false") == "true"

            # Handle encryption if necessary
            if not client_side_encrypted and user.pgp_key:
                encrypted_content = encrypt_message(content, user.pgp_key)
                email_content = encrypted_content if encrypted_content else content
                if not encrypted_content:
                    flash("⛔️ Failed to encrypt message with PGP key.", "error")
                    return redirect(url_for("submit_message", username=username))
            else:
                email_content = content

            # Save the new message
            new_message = Message(content=email_content, user_id=user.id)
            db.session.add(new_message)
            db.session.commit()

            # Attempt to send an email notification
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

        # Render the form page
        return render_template(
            "submit_message.html",
            form=form,
            user=user,
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
            return redirect(url_for("inbox", username=user.primary_username))
        else:
            flash("⛔️ Message not found or unauthorized access.")
            return redirect(url_for("inbox", username=user.primary_username))

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def register() -> Response | str:
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
                            "register.html", form=form, require_invite_code=require_invite_code
                        ),
                        400,
                    )

            if User.query.filter_by(primary_username=username).first():
                flash("💔 Username already taken.", "error")
                return (
                    render_template(
                        "register.html", form=form, require_invite_code=require_invite_code
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
        if request.method == "POST":
            if form.validate_on_submit():
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
                    else:
                        session["2fa_verified"] = True
                        return redirect(url_for("inbox", username=user.primary_username))
                else:
                    flash("⛔️ Invalid username or password")
        return render_template("login.html", form=form)

    @app.route("/verify-2fa-login", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    def verify_2fa_login() -> Response | str:
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
            else:
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
    def update_directory_visibility():
        if "user_id" in session:
            user = User.query.get(session["user_id"])
            user.show_in_directory = "show_in_directory" in request.form
            db.session.commit()
            flash("Directory visibility updated.")
        else:
            flash("You need to be logged in to update settings.")
        return redirect(url_for("settings.index"))

    def sort_users_by_display_name(users, admin_first=True):
        if admin_first:
            # Sorts admins to the top, then by display name or username
            return sorted(
                users,
                key=lambda u: (
                    not u.is_admin,
                    (u.display_name or u.primary_username).strip().lower(),
                ),
            )
        else:
            # Sorts only by display name or username
            return sorted(
                users, key=lambda u: (u.display_name or u.primary_username).strip().lower()
            )

    @app.route("/directory")
    def directory():
        logged_in = "user_id" in session
        users = User.query.all()  # Fetch all users
        sorted_users = sort_users_by_display_name(
            users, admin_first=True
        )  # Sort users in Python with admins first
        return render_template("directory.html", users=sorted_users, logged_in=logged_in)

    @app.route("/directory/search")
    @limiter.limit("500 per minute")
    def directory_search():
        query = request.args.get("query", "").strip()
        tab = request.args.get("tab", "all")

        try:
            general_filter = User.query.filter(
                db.or_(
                    User.primary_username.ilike(f"%{query}%"),
                    User.display_name.ilike(f"%{query}%"),
                    User.bio.ilike(f"%{query}%"),
                )
            )

            if tab == "verified":
                users = general_filter.filter(User.is_verified.is_(True)).all()
            else:
                users = general_filter.all()

            users_data = [
                {
                    "primary_username": user.primary_username,
                    "display_name": user.display_name or user.primary_username,
                    "is_verified": user.is_verified,
                    "is_admin": user.is_admin,  # Ensure this attribute is correctly being sent
                    "bio": user.bio,
                }
                for user in users
            ]

            return jsonify(users_data)
        except Exception as e:
            print(f"Error during search: {e}")
            return jsonify({"error": "Internal Server Error"}), 500

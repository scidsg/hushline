import base64
import io
from datetime import datetime

import pyotp
import qrcode
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from passlib.hash import scrypt
from wtforms import BooleanField, IntegerField, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length

from .crypto import is_valid_pgp_key
from .db import db
from .ext import limiter
from .forms import ComplexPassword, TwoFactorForm
from .model import Message, SecondaryUsername, User
from .utils import require_2fa


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("Old Password", validators=[DataRequired()])
    new_password = PasswordField(
        "New Password",
        validators=[
            DataRequired(),
            Length(min=18, max=128),
            ComplexPassword(),
        ],
    )


class ChangeUsernameForm(FlaskForm):
    new_username = StringField("New Username", validators=[DataRequired(), Length(min=4, max=25)])


class SMTPSettingsForm(FlaskForm):
    smtp_server = StringField("SMTP Server", validators=[DataRequired()])
    smtp_port = IntegerField("SMTP Port", validators=[DataRequired()])
    smtp_username = StringField("SMTP Username", validators=[DataRequired()])
    smtp_password = PasswordField("SMTP Password", validators=[DataRequired()])


class PGPKeyForm(FlaskForm):
    pgp_key = TextAreaField("PGP Key", validators=[Length(max=100000)])


class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Length(max=100)])


class DirectoryVisibilityForm(FlaskForm):
    show_in_directory = BooleanField("Show on public directory")


class ProfileForm(FlaskForm):
    bio = TextAreaField(
        "Bio",
        validators=[Length(max=250)],
        render_kw={"placeholder": "Write something about yourself up to 250 characters."},
    )


def create_blueprint() -> Blueprint:
    bp = Blueprint("settings", __file__, url_prefix="/settings")

    @bp.route("/", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def index() -> str | Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        if not user:
            flash("🫥 User not found.")
            return redirect(url_for("login"))

        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=user.show_in_directory
        )
        secondary_usernames = SecondaryUsername.query.filter_by(user_id=user.id).all()
        change_password_form = ChangePasswordForm()
        change_username_form = ChangeUsernameForm()
        smtp_settings_form = SMTPSettingsForm()
        pgp_key_form = PGPKeyForm()
        display_name_form = DisplayNameForm()
        directory_visibility_form = DirectoryVisibilityForm()

        if request.method == "POST":
            if "update_bio" in request.form:  # Check if the bio update form was submitted
                user.bio = request.form["bio"]
                db.session.commit()
                flash("👍 Bio updated successfully.")
                return redirect(url_for("settings.index"))

        if request.method == "POST":
            if (
                directory_visibility_form.validate_on_submit()
                and "update_directory_visibility" in request.form
            ):
                user.show_in_directory = directory_visibility_form.show_in_directory.data
                db.session.commit()
                flash("👍 Directory visibility updated successfully.")
                return redirect(url_for("settings.index"))

        # Additional admin-specific data initialization
        user_count = two_fa_count = pgp_key_count = two_fa_percentage = pgp_key_percentage = None
        all_users = []

        # Check if user is admin and add admin-specific data
        if user.is_admin:
            user_count = User.query.count()
            two_fa_count = User.query.filter(User._totp_secret.isnot(None)).count()
            pgp_key_count = (
                User.query.filter(User._pgp_key.isnot(None)).filter(User._pgp_key != "").count()
            )
            two_fa_percentage = (two_fa_count / user_count * 100) if user_count else 0
            pgp_key_percentage = (pgp_key_count / user_count * 100) if user_count else 0
            all_users = User.query.all()  # Fetch all users for admin

        # Handle form submissions
        if request.method == "POST":
            # Handle Display Name Form Submission
            if "update_display_name" in request.form and display_name_form.validate_on_submit():
                user.update_display_name(display_name_form.display_name.data.strip())
                db.session.commit()
                flash("👍 Display name updated successfully.")
                current_app.logger.debug(
                    f"Display name updated to {user.display_name}, "
                    f"Verification status: {user.is_verified}"
                )
                return redirect(url_for(".index"))

            # Handle Change Username Form Submission
            elif "change_username" in request.form and change_username_form.validate_on_submit():
                new_username = change_username_form.new_username.data
                existing_user = User.query.filter_by(primary_username=new_username).first()
                if existing_user:
                    flash("💔 This username is already taken.")
                else:
                    user.update_username(new_username)
                    db.session.commit()
                    session["username"] = new_username
                    flash("👍 Username changed successfully.")
                    current_app.logger.debug(
                        f"Username updated to {user.primary_username}, "
                        f"Verification status: {user.is_verified}"
                    )
                return redirect(url_for(".index"))

            # Handle SMTP Settings Form Submission
            elif smtp_settings_form.validate_on_submit():
                user.email = smtp_settings_form.smtp_username.data
                user.smtp_server = smtp_settings_form.smtp_server.data
                user.smtp_port = smtp_settings_form.smtp_port.data
                user.smtp_username = smtp_settings_form.smtp_username.data
                user.smtp_password = smtp_settings_form.smtp_password.data
                db.session.commit()
                flash("👍 SMTP settings updated successfully.")
                return redirect(url_for("settings"))

            # Handle PGP Key Form Submission
            elif pgp_key_form.validate_on_submit():
                user.pgp_key = pgp_key_form.pgp_key.data
                db.session.commit()
                flash("👍 PGP key updated successfully.")
                return redirect(url_for("settings"))

            # Handle Change Password Form Submission
            elif change_password_form.validate_on_submit():
                if scrypt.verify(change_password_form.old_password.data, user.password_hash):
                    # Hash the new password using scrypt and update the user object
                    user.password_hash = scrypt.hash(change_password_form.new_password.data)
                    db.session.commit()
                    flash("👍 Password changed successfully.")
                else:
                    flash("⛔️ Incorrect old password.")
                return redirect(url_for("settings"))

            # Check if user is admin and add admin-specific data
            is_admin = user.is_admin
            if is_admin:
                user_count = User.query.count()
                two_fa_count = User.query.filter(User._totp_secret.isnot(None)).count()
                pgp_key_count = (
                    User.query.filter(User._pgp_key.isnot(None)).filter(User._pgp_key != "").count()
                )
                two_fa_percentage = (two_fa_count / user_count * 100) if user_count else 0
                pgp_key_percentage = (pgp_key_count / user_count * 100) if user_count else 0
            else:
                user_count = two_fa_count = pgp_key_count = two_fa_percentage = (
                    pgp_key_percentage
                ) = None

        # Prepopulate form fields
        smtp_settings_form.smtp_server.data = user.smtp_server
        smtp_settings_form.smtp_port.data = user.smtp_port
        smtp_settings_form.smtp_username.data = user.smtp_username
        pgp_key_form.pgp_key.data = user.pgp_key
        display_name_form.display_name.data = user.display_name or user.primary_username
        directory_visibility_form.show_in_directory.data = user.show_in_directory

        return render_template(
            "settings.html",
            now=datetime.utcnow(),
            user=user,
            secondary_usernames=secondary_usernames,
            all_users=all_users,  # Pass to the template for admin view
            smtp_settings_form=smtp_settings_form,
            change_password_form=change_password_form,
            change_username_form=change_username_form,
            pgp_key_form=pgp_key_form,
            display_name_form=display_name_form,
            # Admin-specific data passed to the template
            is_admin=user.is_admin,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            two_fa_percentage=two_fa_percentage,
            pgp_key_percentage=pgp_key_percentage,
            directory_visibility_form=directory_visibility_form,
        )

    @bp.route("/toggle-2fa", methods=["POST"])
    @limiter.limit("120 per minute")
    def toggle_2fa() -> Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user.totp_secret:
            return redirect(url_for(".disable_2fa"))
        else:
            return redirect(url_for(".enable_2fa"))

    @bp.route("/change-password", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def change_password() -> str | Response:
        user_id = session.get("user_id")
        if not user_id:
            flash("Session expired, please log in again.", "info")
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("login"))

        change_password_form = ChangePasswordForm(request.form)
        if change_password_form.validate_on_submit():
            # Verify the old password
            if user.check_password(change_password_form.old_password.data):
                # Set the new password
                user.password_hash = change_password_form.new_password.data
                db.session.commit()
                session.clear()  # Clears the session, logging the user out
                flash(
                    "👍 Password successfully changed. Please log in again.",
                    "success",
                )
                return redirect(
                    url_for("login")
                )  # Redirect to the login page for re-authentication
            else:
                flash("Incorrect old password.", "error")

        # Render the settings page with all forms
        return render_template(
            "settings.html",
            change_password_form=change_password_form,
            change_username_form=ChangeUsernameForm(),
            smtp_settings_form=SMTPSettingsForm(),
            pgp_key_form=PGPKeyForm(),
            display_name_form=DisplayNameForm(),
            user=user,
        )

    @bp.route("/change-username", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def change_username() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))

        new_username = request.form.get("new_username").strip()
        if not new_username:
            flash("No new username provided.", "error")
            return redirect(url_for(".settings"))

        user = User.query.get(user_id)
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("login"))

        if user.primary_username == new_username:
            flash("New username is the same as the current username.", "info")
            return redirect(url_for(".settings"))

        existing_user = User.query.filter_by(primary_username=new_username).first()
        if existing_user:
            flash("This username is already taken.", "error")
            return redirect(url_for(".settings"))

        # Log before updating
        current_app.logger.debug(
            f"Updating username for user ID {user_id}: {user.primary_username} to {new_username}"
        )

        # Directly update the user's primary username
        user.primary_username = new_username
        try:
            db.session.commit()
            session["username"] = new_username
            flash("Username successfully changed.", "success")
            current_app.logger.debug(
                f"Username successfully updated for user ID {user_id} to {new_username}"
            )
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating username for user ID {user_id}: {e}")
            flash("An error occurred while updating the username.", "error")

        return redirect(url_for(".settings"))

    @bp.route("/enable-2fa", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def enable_2fa() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        form = TwoFactorForm()

        if form.validate_on_submit():
            temp_totp_secret = session.get("temp_totp_secret")
            verification_code = form.verification_code.data
            if (
                verification_code
                and temp_totp_secret
                and pyotp.TOTP(temp_totp_secret).verify(verification_code)
            ):
                user.totp_secret = temp_totp_secret
                db.session.commit()
                session.pop("temp_totp_secret", None)
                flash("👍 2FA setup successful. Please log in again with 2FA.")
                return redirect(url_for("logout"))  # Redirect to logout
            else:
                flash("⛔️ Invalid 2FA code. Please try again.")
                return redirect(url_for(".enable_2fa"))

        # Generate new 2FA secret and QR code
        temp_totp_secret = pyotp.random_base32()
        session["temp_totp_secret"] = temp_totp_secret
        session["is_setting_up_2fa"] = True
        totp_uri = pyotp.totp.TOTP(temp_totp_secret).provisioning_uri(
            name=user.primary_username, issuer_name="HushLine"
        )
        img = qrcode.make(totp_uri)
        buffered = io.BytesIO()
        img.save(buffered)
        qr_code_img = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

        # Pass the text-based pairing code and the user to the template
        return render_template(
            "enable_2fa.html",
            form=form,
            qr_code_img=qr_code_img,
            text_code=temp_totp_secret,
            user=user,
        )

    @bp.route("/disable-2fa", methods=["POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def disable_2fa():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        user.totp_secret = None
        db.session.commit()
        flash("🔓 2FA has been disabled.")
        return redirect(url_for(".index"))

    @bp.route("/confirm-disable-2fa", methods=["GET"])
    def confirm_disable_2fa():
        return render_template("confirm_disable_2fa.html")

    @bp.route("/show-qr-code")
    @limiter.limit("120 per minute")
    @require_2fa
    def show_qr_code():
        user = User.query.get(session["user_id"])
        if not user or not user.totp_secret:
            return redirect(url_for(".enable_2fa"))

        form = TwoFactorForm()

        totp_uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
            name=user.primary_username, issuer_name="Hush Line"
        )
        img = qrcode.make(totp_uri)

        # Convert QR code to a data URI
        buffered = io.BytesIO()
        img.save(buffered)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        qr_code_img = f"data:image/png;base64,{img_str}"

        return render_template(
            "show_qr_code.html",
            form=form,
            qr_code_img=qr_code_img,
            user_secret=user.totp_secret,
        )

    @bp.route("/verify-2fa-setup", methods=["POST"])
    @limiter.limit("120 per minute")
    def verify_2fa_setup():
        user = User.query.get(session["user_id"])
        if not user:
            return redirect(url_for("login"))

        verification_code = request.form["verification_code"]
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(verification_code):
            flash("👍 2FA setup successful. Please log in again.")
            session.pop("is_setting_up_2fa", None)
            return redirect(url_for("logout"))
        else:
            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for("show_qr_code"))

    @bp.route("/update_pgp_key", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def update_pgp_key():
        user_id = session.get("user_id")
        if not user_id:
            flash("⛔️ User not authenticated.")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        form = PGPKeyForm()
        if form.validate_on_submit():
            pgp_key = form.pgp_key.data

            if pgp_key.strip() == "":
                # If the field is empty, remove the PGP key
                user.pgp_key = None
            elif is_valid_pgp_key(pgp_key):
                # If the field is not empty and the key is valid, update the PGP key
                user.pgp_key = pgp_key
            else:
                # If the PGP key is invalid
                flash("⛔️ Invalid PGP key format or import failed.")
                return redirect(url_for(".index"))

            db.session.commit()
            flash("👍 PGP key updated successfully.")
            return redirect(url_for(".index"))
        return render_template("settings.html", form=form)

    @bp.route("/update_smtp_settings", methods=["GET", "POST"])
    @limiter.limit("120 per minute")
    @require_2fa
    def update_smtp_settings():
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("⛔️ User not found")
            return redirect(url_for(".index"))

        # Initialize forms
        change_password_form = ChangePasswordForm()
        change_username_form = ChangeUsernameForm()
        smtp_settings_form = SMTPSettingsForm()
        pgp_key_form = PGPKeyForm()

        # Handling SMTP settings form submission
        if smtp_settings_form.validate_on_submit():
            # Updating SMTP settings from form data
            user.email = smtp_settings_form.smtp_username.data
            user.smtp_server = smtp_settings_form.smtp_server.data
            user.smtp_port = smtp_settings_form.smtp_port.data
            user.smtp_username = smtp_settings_form.smtp_username.data
            user.smtp_password = smtp_settings_form.smtp_password.data

            db.session.commit()
            flash("👍 SMTP settings updated successfully")
            return redirect(url_for(".index"))

        # Prepopulate SMTP settings form fields
        smtp_settings_form.email.data = user.email
        smtp_settings_form.smtp_server.data = user.smtp_server
        smtp_settings_form.smtp_port.data = user.smtp_port
        smtp_settings_form.smtp_username.data = user.smtp_username
        # Note: Password fields are typically not prepopulated for security reasons

        pgp_key_form.pgp_key.data = user.pgp_key

        return render_template(
            "settings.html",
            user=user,
            smtp_settings_form=smtp_settings_form,
            change_password_form=change_password_form,
            change_username_form=change_username_form,
            pgp_key_form=pgp_key_form,
        )

    @bp.route("/delete-account", methods=["POST"])
    @require_2fa
    def delete_account():
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.")
            return redirect(url_for("login"))

        user = User.query.get(user_id)
        if user:
            # Explicitly delete messages for the user
            Message.query.filter_by(user_id=user.id).delete()

            # Explicitly delete secondary users if necessary
            SecondaryUsername.query.filter_by(user_id=user.id).delete()

            # Now delete the user
            db.session.delete(user)
            db.session.commit()

            session.clear()  # Clear the session
            flash("🔥 Your account and all related information have been deleted.")
            return redirect(url_for("index"))
        else:
            flash("User not found. Please log in again.")
            return redirect(url_for("login"))

    return bp

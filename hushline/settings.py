import base64
import io
import re
from datetime import UTC, datetime
from typing import Optional
from urllib.parse import urlparse

import pyotp
import qrcode
import requests
from flask import (
    Blueprint,
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
from wtforms import (
    BooleanField,
    Field,
    FormField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length
from wtforms.validators import Optional as OptionalField

from .crypto import is_valid_pgp_key
from .db import db
from .forms import ComplexPassword, TwoFactorForm
from .model import Message, SecondaryUsername, SMTPEncryption, User
from .utils import authentication_required, create_smtp_config


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
    class Meta:
        csrf = False

    smtp_server = StringField("SMTP Server", validators=[OptionalField(), Length(max=255)])
    smtp_port = IntegerField("SMTP Port", validators=[OptionalField()])
    smtp_username = StringField("SMTP Username", validators=[OptionalField(), Length(max=255)])
    smtp_password = PasswordField("SMTP Password", validators=[OptionalField(), Length(max=255)])
    smtp_encryption = SelectField(
        "SMTP Encryption Protocol", choices=[proto.value for proto in SMTPEncryption]
    )
    smtp_sender = StringField("SMTP Sender Address", validators=[Length(max=255)])


class EmailForwardingForm(FlaskForm):
    forwarding_enabled = BooleanField("Enable Forwarding", validators=[OptionalField()])
    email_address = StringField("Email Address", validators=[OptionalField(), Length(max=255)])
    custom_smtp_settings = BooleanField("Custom SMTP Settings", validators=[OptionalField()])
    smtp_settings = FormField(SMTPSettingsForm)

    def validate(self, extra_validators: list | None = None) -> bool:
        if not FlaskForm.validate(self, extra_validators):
            return False

        rv = True
        if self.forwarding_enabled.data:
            if not self.email_address.data:
                self.email_address.errors.append(
                    "Email address must be specified when forwarding is enabled."
                )
                rv = False
            if self.custom_smtp_settings.data or not current_app.config["NOTIFICATIONS_ADDRESS"]:
                smtp_fields = [
                    self.smtp_settings.smtp_sender,
                    self.smtp_settings.smtp_username,
                    self.smtp_settings.smtp_server,
                    self.smtp_settings.smtp_port,
                ]
                unset_smtp_fields = [field for field in smtp_fields if not field.data]

                def remove_tags(text: str) -> str:
                    return re.sub("<[^<]+?>", "", text)

                for field in unset_smtp_fields:
                    field.errors.append(
                        f"{remove_tags(field.label())} is"
                        " required if custom SMTP settings are enabled."
                    )
                    rv = False
        return rv

    def flattened_errors(self, input: Optional[dict | list] = None) -> list[str]:
        errors = input if input else self.errors
        if isinstance(errors, list):
            return errors
        ret = []
        if isinstance(errors, dict):
            for error in errors.values():
                ret.extend(self.flattened_errors(error))
        return ret


class PGPProtonForm(FlaskForm):
    email = StringField(
        "",
        validators=[DataRequired(), Email()],
        render_kw={
            "placeholder": "Search Proton email...",
            "id": "proton_email",
            "required": True,
        },
    )


class PGPKeyForm(FlaskForm):
    pgp_key = TextAreaField("Or, Add Your Public PGP Key Manually", validators=[Length(max=100000)])


class DisplayNameForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Length(max=100)])


class DirectoryVisibilityForm(FlaskForm):
    show_in_directory = BooleanField("Show on public directory")


class ProfileForm(FlaskForm):
    bio = TextAreaField("Bio", validators=[Length(max=250)])
    extra_field_label1 = StringField(
        "Extra Field Label 1", validators=[OptionalField(), Length(max=50)]
    )
    extra_field_value1 = StringField(
        "Extra Field Value 1", validators=[OptionalField(), Length(max=4096)]
    )
    extra_field_label2 = StringField(
        "Extra Field Label 2", validators=[OptionalField(), Length(max=50)]
    )
    extra_field_value2 = StringField(
        "Extra Field Value 2", validators=[OptionalField(), Length(max=4096)]
    )
    extra_field_label3 = StringField(
        "Extra Field Label 3", validators=[OptionalField(), Length(max=50)]
    )
    extra_field_value3 = StringField(
        "Extra Field Value 3", validators=[OptionalField(), Length(max=4096)]
    )
    extra_field_label4 = StringField(
        "Extra Field Label 4", validators=[OptionalField(), Length(max=50)]
    )
    extra_field_value4 = StringField(
        "Extra Field Value 4", validators=[OptionalField(), Length(max=4096)]
    )


def set_field_attribute(input_field: Field, attribute: str, value: str) -> None:
    if input_field.render_kw is None:
        input_field.render_kw = {}
    input_field.render_kw[attribute] = value


def unset_field_attribute(input_field: Field, attribute: str) -> None:
    if input_field.render_kw is not None:
        input_field.render_kw.pop(attribute)


def set_input_disabled(input_field: Field, disabled: bool = True) -> None:
    """
    disable the given input

    Args:
        inputField(Input): the WTForms input to disable
        disabled(bool): if true set the disabled attribute of the input
    """
    if disabled:
        set_field_attribute(input_field, "disabled", "disabled")
    else:
        unset_field_attribute(input_field, "disabled")


def is_safe_url(url: str) -> bool:
    """Validates if the provided URL is safe and within the expected domains."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ["http", "https"]:
        return False

    # Allow only the specific domain without wildcards for better security
    allowed_domains = ["hushline.app"]
    if parsed_url.netloc not in allowed_domains:
        return False
    return True


def create_blueprint() -> Blueprint:
    bp = Blueprint("settings", __file__, url_prefix="/settings")

    @bp.route("/", methods=["GET", "POST"])
    @authentication_required
    def index() -> str | Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("🫥 User not found.")
            return redirect(url_for("login"))

        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=user.show_in_directory
        )
        secondary_usernames = db.session.scalars(
            db.select(SecondaryUsername).filter_by(user_id=user.id)
        ).all()
        change_password_form = ChangePasswordForm()
        change_username_form = ChangeUsernameForm()
        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm()
        email_forwarding_form = EmailForwardingForm()
        display_name_form = DisplayNameForm()
        directory_visibility_form = DirectoryVisibilityForm()
        profile_form = ProfileForm()

        # Handle form submissions
        if request.method == "POST":
            # Update bio and custom fields
            if "update_bio" in request.form and profile_form.validate_on_submit():
                user.bio = request.form["bio"].strip()
                user.extra_field_label1 = profile_form.extra_field_label1.data.strip()
                user.extra_field_value1 = profile_form.extra_field_value1.data.strip()
                user.extra_field_label2 = profile_form.extra_field_label2.data.strip()
                user.extra_field_value2 = profile_form.extra_field_value2.data.strip()
                user.extra_field_label3 = profile_form.extra_field_label3.data.strip()
                user.extra_field_value3 = profile_form.extra_field_value3.data.strip()
                user.extra_field_label4 = profile_form.extra_field_label4.data.strip()
                user.extra_field_value4 = profile_form.extra_field_value4.data.strip()

                # Trigger the rel=me verification for each URL field
                for i in range(1, 5):
                    url_to_verify = getattr(user, f"extra_field_value{i}", "").strip()
                    if url_to_verify:
                        try:
                            response = requests.get(url_to_verify, timeout=5)
                            response.raise_for_status()
                            profile_url = f"https://tips.hushline.app/to/{user.primary_username}"
                            if re.search(
                                rf'<a[^>]+href="{re.escape(profile_url)}"[^>]*rel="me"[^>]*>',
                                response.text,
                            ):
                                setattr(user, f"extra_field_verified{i}", True)
                            else:
                                setattr(user, f"extra_field_verified{i}", False)
                        except requests.exceptions.RequestException as e:
                            current_app.logger.error(f"Error fetching URL for field {i}: {e}")
                            setattr(user, f"extra_field_verified{i}", False)

                db.session.commit()

                # Display flash message after successful update
                flash("👍 Bio and fields updated successfully.")
                return redirect(url_for("settings.index"))

            # Update directory visibility
            if (
                "update_directory_visibility" in request.form
                and directory_visibility_form.validate_on_submit()
            ):
                user.show_in_directory = directory_visibility_form.show_in_directory.data
                db.session.commit()
                flash("👍 Directory visibility updated successfully.")
                return redirect(url_for("settings.index"))

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
            if "change_username" in request.form and change_username_form.validate_on_submit():
                new_username = change_username_form.new_username.data
                existing_user = db.session.scalars(
                    db.select(User).filter_by(primary_username=new_username).limit(1)
                ).first()
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

        # Additional admin-specific data initialization
        user_count = two_fa_count = pgp_key_count = two_fa_percentage = pgp_key_percentage = None
        all_users = []

        # Check if user is admin and add admin-specific data
        if user.is_admin:
            user_count = db.session.scalar(db.func.count(User.id))
            two_fa_count = db.session.scalar(
                db.select(db.func.count(User.id).filter(User._totp_secret.isnot(None)))
            )
            pgp_key_count = db.session.scalar(
                db.select(
                    db.func.count(User.id)
                    .filter(User._pgp_key.isnot(None))
                    .filter(User._pgp_key != "")
                )
            )
            two_fa_percentage = (two_fa_count / user_count * 100) if user_count else 0
            pgp_key_percentage = (pgp_key_count / user_count * 100) if user_count else 0
            all_users = list(db.session.scalars(db.select(User)).all())  # Fetch all users for admin

        # Prepopulate form fields
        email_forwarding_form.forwarding_enabled.data = user.email is not None
        if not user.pgp_key:
            set_input_disabled(email_forwarding_form.forwarding_enabled)
        email_forwarding_form.email_address.data = user.email
        email_forwarding_form.custom_smtp_settings.data = user.smtp_server is not None
        email_forwarding_form.smtp_settings.smtp_server.data = user.smtp_server
        email_forwarding_form.smtp_settings.smtp_port.data = user.smtp_port
        email_forwarding_form.smtp_settings.smtp_username.data = user.smtp_username
        email_forwarding_form.smtp_settings.smtp_encryption.data = user.smtp_encryption.value
        email_forwarding_form.smtp_settings.smtp_sender.data = user.smtp_sender
        pgp_key_form.pgp_key.data = user.pgp_key
        display_name_form.display_name.data = user.display_name or user.primary_username
        directory_visibility_form.show_in_directory.data = user.show_in_directory

        return render_template(
            "settings.html",
            now=datetime.now(UTC),
            user=user,
            secondary_usernames=secondary_usernames,
            all_users=all_users,  # Pass to the template for admin view
            email_forwarding_form=email_forwarding_form,
            change_password_form=change_password_form,
            change_username_form=change_username_form,
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
            display_name_form=display_name_form,
            profile_form=profile_form,
            # Admin-specific data passed to the template
            is_admin=user.is_admin,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            two_fa_percentage=two_fa_percentage,
            pgp_key_percentage=pgp_key_percentage,
            directory_visibility_form=directory_visibility_form,
            is_personal_server=current_app.config["IS_PERSONAL_SERVER"],
            default_forwarding_enabled=bool(current_app.config["NOTIFICATIONS_ADDRESS"]),
        )

    @bp.route("/toggle-2fa", methods=["POST"])
    @authentication_required
    def toggle_2fa() -> Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user and user.totp_secret:
            return redirect(url_for(".disable_2fa"))

        return redirect(url_for(".enable_2fa"))

    @bp.route("/change-password", methods=["POST"])
    @authentication_required
    def change_password() -> str | Response:
        user_id = session.get("user_id")
        if not user_id:
            flash("Session expired, please log in again.", "info")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("User not found.", "error")
            return redirect(url_for("login"))

        change_password_form = ChangePasswordForm(request.form)
        if not change_password_form.validate_on_submit():
            flash("New password is invalid.")
            return redirect(url_for("settings.index"))

        # Verify the old password
        if not user.check_password(change_password_form.old_password.data):
            flash("Incorrect old password.", "error")
            return redirect(url_for("settings.index"))

        # Set the new password
        user.password_hash = change_password_form.new_password.data
        db.session.commit()
        session.clear()  # Clears the session, logging the user out
        flash(
            "👍 Password successfully changed. Please log in again.",
            "success",
        )
        return redirect(url_for("login"))  # Redirect to the login page for re-authentication

    @bp.route("/enable-2fa", methods=["GET", "POST"])
    @authentication_required
    def enable_2fa() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        form = TwoFactorForm()

        if form.validate_on_submit():
            temp_totp_secret = session.get("temp_totp_secret")
            verification_code = form.verification_code.data
            if (
                verification_code
                and temp_totp_secret
                and pyotp.TOTP(temp_totp_secret).verify(verification_code)
                and user
            ):
                user.totp_secret = temp_totp_secret
                db.session.commit()
                session.pop("temp_totp_secret", None)
                flash("👍 2FA setup successful. Please log in again with 2FA.")
                return redirect(url_for("logout"))  # Redirect to logout

            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for(".enable_2fa"))

        # Generate new 2FA secret and QR code
        temp_totp_secret = pyotp.random_base32()
        session["temp_totp_secret"] = temp_totp_secret
        session["is_setting_up_2fa"] = True
        if user:
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
    @authentication_required
    def disable_2fa() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user:
            user.totp_secret = None
        db.session.commit()
        flash("🔓 2FA has been disabled.")
        return redirect(url_for(".index"))

    @bp.route("/confirm-disable-2fa", methods=["GET"])
    @authentication_required
    def confirm_disable_2fa() -> Response | str:
        return render_template("confirm_disable_2fa.html")

    @bp.route("/verify-2fa-setup", methods=["POST"])
    @authentication_required
    def verify_2fa_setup() -> Response | str:
        user = db.session.get(User, session["user_id"])
        if not user:
            return redirect(url_for("login"))

        if not user.totp_secret:
            flash("⛔️ 2FA setup failed. Please try again.")
            return redirect(url_for("show_qr_code"))

        verification_code = request.form["verification_code"]
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(verification_code):
            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for("show_qr_code"))

        flash("👍 2FA setup successful. Please log in again.")
        session.pop("is_setting_up_2fa", None)
        return redirect(url_for("logout"))

    @bp.route("/update_pgp_key_proton", methods=["POST"])
    @authentication_required
    def update_pgp_key_proton() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("⛔️ User not authenticated.")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return redirect(url_for("login"))

        form = PGPProtonForm()

        if not form.validate_on_submit():
            flash("⛔️ Invalid email address.")
            return redirect(url_for(".index"))

        email = form.email.data

        # Try to fetch the PGP key from ProtonMail
        try:
            r = requests.get(
                f"https://mail-api.proton.me/pks/lookup?op=get&search={email}", timeout=5
            )
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error fetching PGP key from Proton Mail: {e}")
            flash("⛔️ Error fetching PGP key from Proton Mail.")
            return redirect(url_for(".index"))
        if r.status_code == 200:  # noqa: PLR2004
            pgp_key = r.text
            if is_valid_pgp_key(pgp_key):
                user.pgp_key = pgp_key
            else:
                flash("⛔️ No PGP key found for the email address.")
                return redirect(url_for(".index"))
        else:
            flash("⛔️ This isn't a Proton Mail email address.")
            return redirect(url_for(".index"))

        db.session.commit()
        flash("👍 PGP key updated successfully.")
        return redirect(url_for(".index"))

    @bp.route("/update-pgp-key", methods=["POST"])
    @authentication_required
    def update_pgp_key() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("⛔️ User not authenticated.")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return redirect(url_for("login"))

        form = PGPKeyForm()
        if form.validate_on_submit():
            pgp_key = form.pgp_key.data

            if pgp_key.strip() == "":
                # If the field is empty, remove the PGP key
                user.pgp_key = None
                user.email = None  # remove the forwarding email if the PGP key is removed
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

        return redirect(url_for(".index"))

    @bp.route("/update-smtp-settings", methods=["POST"])
    @authentication_required
    def update_smtp_settings() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("⛔️ User not found")
            return redirect(url_for(".index"))

        email_forwarding_form = EmailForwardingForm()
        default_forwarding_enabled = bool(current_app.config.get("NOTIFICATIONS_ADDRESS", False))

        # Handling SMTP settings form submission
        if not email_forwarding_form.validate_on_submit():
            flash(email_forwarding_form.flattened_errors().pop(0))
            return redirect(url_for(".index"))
        if email_forwarding_form.email_address.data and not user.pgp_key:
            flash("⛔️ Email forwarding requires a configured PGP key")
            return redirect(url_for(".index"))
        # Updating SMTP settings from form data
        forwarding_enabled = email_forwarding_form.forwarding_enabled.data
        custom_smtp_settings = forwarding_enabled and (
            email_forwarding_form.custom_smtp_settings.data or not default_forwarding_enabled
        )
        if custom_smtp_settings:
            try:
                smtp_config = create_smtp_config(
                    email_forwarding_form.smtp_settings.smtp_username.data,
                    email_forwarding_form.smtp_settings.smtp_server.data,
                    email_forwarding_form.smtp_settings.smtp_port.data,
                    email_forwarding_form.smtp_settings.smtp_password.data
                    or user.smtp_password
                    or "",
                    email_forwarding_form.smtp_settings.smtp_sender.data,
                    encryption=SMTPEncryption[
                        email_forwarding_form.smtp_settings.smtp_encryption.data
                    ],
                )
                with smtp_config.smtp_login():
                    pass
            except Exception as e:
                current_app.logger.debug(e)
                flash("⛔️ Unable to validate SMTP connection settings")
                return redirect(url_for(".index"))
        user.email = email_forwarding_form.email_address.data if forwarding_enabled else None
        user.smtp_server = (
            email_forwarding_form.smtp_settings.smtp_server.data if custom_smtp_settings else None
        )
        user.smtp_port = (
            email_forwarding_form.smtp_settings.smtp_port.data if custom_smtp_settings else None
        )
        user.smtp_username = (
            email_forwarding_form.smtp_settings.smtp_username.data if custom_smtp_settings else None
        )
        # Since passwords aren't pre-populated in the form, don't unset it if not provided
        user.smtp_password = (
            email_forwarding_form.smtp_settings.smtp_password.data
            if custom_smtp_settings and email_forwarding_form.smtp_settings.smtp_password.data
            else user.smtp_password
        )
        user.smtp_sender = (
            email_forwarding_form.smtp_settings.smtp_sender.data
            if custom_smtp_settings and email_forwarding_form.smtp_settings.smtp_sender.data
            else None
        )
        user.smtp_encryption = (
            email_forwarding_form.smtp_settings.smtp_encryption.data
            if custom_smtp_settings
            else SMTPEncryption.default()
        )

        db.session.commit()
        flash("👍 SMTP settings updated successfully")
        return redirect(url_for(".index"))

    @bp.route("/delete-account", methods=["POST"])
    @authentication_required
    def delete_account() -> Response | str:
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to continue.")
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if user:
            # Explicitly delete messages for the user
            db.session.execute(db.delete(Message).filter_by(user_id=user.id))

            # Explicitly delete secondary users if necessary
            db.session.execute(db.delete(SecondaryUsername).filter_by(user_id=user.id))

            # Now delete the user
            db.session.delete(user)
            db.session.commit()

            session.clear()  # Clear the session
            flash("🔥 Your account and all related information have been deleted.")
            return redirect(url_for("index"))

        flash("User not found. Please log in again.")
        return redirect(url_for("login"))

    @bp.route("/verify-rel-me/<int:field_index>", methods=["POST"])
    @authentication_required
    def verify_rel_me(field_index: int) -> Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("User not found.")
            return redirect(url_for("login"))

        url_to_verify = request.form.get(f"extra_field_value{field_index}", "").strip()
        if not url_to_verify:
            flash(f"No URL provided for field {field_index}.")
            return redirect(url_for(".index"))

        # Check if the URL is safe
        if not is_safe_url(url_to_verify):
            flash("The URL provided is not safe or is not within the allowed domains.")
            return redirect(url_for(".index"))

        try:
            response = requests.get(url_to_verify, timeout=5)
            response.raise_for_status()

            # Ensure content type is HTML
            if "text/html" not in response.headers.get("Content-Type", ""):
                flash("The URL provided does not return an HTML page.")
                return redirect(url_for(".index"))

            # Prevent SSRF via redirect
            if response.url != url_to_verify:
                flash("The URL provided redirects to a different domain.")
                return redirect(url_for(".index"))

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error fetching URL: {e}")
            flash(f"Failed to fetch the URL for field {field_index}.")
            return redirect(url_for(".index"))

        profile_url = f"https://hushline.app/user/{user.primary_username}"  # Adjust as necessary
        if re.search(rf'<a[^>]+href="{re.escape(profile_url)}"[^>]*rel="me"[^>]*>', response.text):
            flash(f"✅ Field {field_index} URL is verified.")
            setattr(user, f"extra_field_verified{field_index}", True)
        else:
            flash(f"❌ Field {field_index} URL verification failed.")
            setattr(user, f"extra_field_verified{field_index}", False)

        db.session.commit()
        return redirect(url_for(".index"))

    return bp

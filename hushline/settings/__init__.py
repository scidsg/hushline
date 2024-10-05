import asyncio
import base64
import io
from hmac import compare_digest as bytes_are_equal

import aiohttp
import pyotp
import qrcode
import requests
from bs4 import BeautifulSoup
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
from psycopg.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers.response import Response
from wtforms import Field

from ..crypto import is_valid_pgp_key
from ..db import db
from ..forms import TwoFactorForm
from ..model import HostOrganization, Message, SMTPEncryption, Tier, User, Username
from ..utils import (
    admin_authentication_required,
    authentication_required,
    create_smtp_config,
)
from .forms import (
    ChangePasswordForm,
    ChangeUsernameForm,
    DirectoryVisibilityForm,
    DisplayNameForm,
    EmailForwardingForm,
    NewAliasForm,
    PGPKeyForm,
    PGPProtonForm,
    ProfileForm,
    UpdateBrandAppNameForm,
    UpdateBrandPrimaryColorForm,
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


# Define the async function for URL verification
async def verify_url(
    session: aiohttp.ClientSession, username: Username, i: int, url_to_verify: str, profile_url: str
) -> None:
    try:
        async with session.get(url_to_verify, timeout=aiohttp.ClientTimeout(total=5)) as response:
            response.raise_for_status()
            html_content = await response.text()

            soup = BeautifulSoup(html_content, "html.parser")
            verified = False
            for link in soup.find_all("a"):
                href = link.get("href")
                rel = link.get("rel", [])
                if href == profile_url and "me" in rel:
                    verified = True
                    break

            setattr(username, f"extra_field_verified{i}", verified)
    except aiohttp.ClientError as e:
        current_app.logger.error(f"Error fetching URL for field {i}: {e}")
        setattr(username, f"extra_field_verified{i}", False)


async def handle_update_bio(username: Username, form: ProfileForm, redirect_url: str) -> Response:
    username.bio = form.bio.data.strip()

    # Define base_url from the environment or config
    profile_url = url_for("profile", _external=True, username=username._username)

    async with aiohttp.ClientSession() as client_session:
        tasks = []
        for i in range(1, 5):
            if (label_field := getattr(form, f"extra_field_label{i}", None)) and (
                label := getattr(label_field, "data", None)
            ):
                setattr(username, f"extra_field_label{i}", label)

            if (value_field := getattr(form, f"extra_field_value{i}", None)) and (
                value := getattr(value_field, "data", None)
            ):
                setattr(username, f"extra_field_value{i}", value)
            else:
                setattr(username, f"extra_field_verified{i}", False)
                continue

            # Verify the URL only if it starts with "https://"
            if value.startswith("https://"):
                task = verify_url(client_session, username, i, value, profile_url)
                tasks.append(task)

        # Run all the tasks concurrently
        if tasks:  # Only gather if there are tasks to run
            await asyncio.gather(*tasks)

    db.session.commit()
    flash("👍 Bio and fields updated successfully.")
    return redirect(redirect_url)


def handle_update_directory_visibility(
    user: Username, form: DirectoryVisibilityForm, redirect_url: str
) -> Response:
    user.show_in_directory = form.show_in_directory.data
    db.session.commit()
    flash("👍 Directory visibility updated successfully.")
    return redirect(redirect_url)


def handle_display_name_form(
    username: Username, form: DisplayNameForm, redirect_url: str
) -> Response:
    username.display_name = form.display_name.data.strip()
    db.session.commit()

    flash("👍 Display name updated successfully.")
    current_app.logger.debug(
        f"Display name updated to {username.display_name}, "
        f"Verification status: {username.is_verified}"
    )
    return redirect(redirect_url)


def handle_change_username_form(
    username: Username, form: ChangeUsernameForm, redirect_url: str
) -> Response:
    new_username = form.new_username.data

    # TODO a better pattern would be to try to commit, catch the exception, and match
    # on the name of the unique index that errored
    if db.session.scalar(db.exists(Username).where(Username._username == new_username).select()):
        flash("💔 This username is already taken.")
    else:
        username.username = new_username
        db.session.commit()

        session["username"] = new_username
        flash("👍 Username changed successfully.")
        current_app.logger.debug(
            f"Username updated to {username.username}, "
            f"Verification status: {username.is_verified}"
        )
    return redirect(redirect_url)


def handle_new_alias_form(user: User, new_alias_form: NewAliasForm, redirect_url: str) -> Response:
    current_app.logger.debug(f"Creating alias for {user.primary_username.username}")
    # TODO check that users are allowed to add aliases here (is premium, not too many)
    uname = Username(_username=new_alias_form.username.data, user_id=user.id, is_primary=False)
    db.session.add(uname)
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        if isinstance(e.orig, UniqueViolation) and '"uq_usernames_username"' in str(e.orig):
            flash("💔 This username is already taken.")
        else:
            flash("⛔️ Internal server error. Alias not created.")
    else:
        flash("👍 Alias created successfully.")
    return redirect(redirect_url)


def create_blueprint() -> Blueprint:
    bp = Blueprint("settings", __file__, url_prefix="/settings")

    @authentication_required
    @bp.route("/", methods=["GET", "POST"])
    async def index() -> str | Response:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login"))

        user = db.session.get(User, user_id)
        if not user:
            flash("🫥 User not found.")
            return redirect(url_for("login"))

        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=user.primary_username.show_in_directory
        )
        change_password_form = ChangePasswordForm()
        change_username_form = ChangeUsernameForm()
        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm()
        email_forwarding_form = EmailForwardingForm()
        display_name_form = DisplayNameForm()
        directory_visibility_form = DirectoryVisibilityForm()
        new_alias_form = NewAliasForm()
        profile_form = ProfileForm()
        update_brand_primary_color_form = UpdateBrandPrimaryColorForm()
        update_brand_app_name_form = UpdateBrandAppNameForm()

        if request.method == "POST":
            if "update_bio" in request.form and profile_form.validate_on_submit():
                return await handle_update_bio(
                    user.primary_username, profile_form, url_for(".index")
                )
            if (
                "update_directory_visibility" in request.form
                and directory_visibility_form.validate_on_submit()
            ):
                return handle_update_directory_visibility(
                    user.primary_username, directory_visibility_form, url_for(".index")
                )
            if "update_display_name" in request.form and display_name_form.validate_on_submit():
                return handle_display_name_form(
                    user.primary_username, display_name_form, url_for(".index")
                )
            if "change_username" in request.form and change_username_form.validate_on_submit():
                return handle_change_username_form(
                    user.primary_username, change_username_form, url_for(".index")
                )
            if "new_alias" in request.form and new_alias_form.validate_on_submit():
                return handle_new_alias_form(user, new_alias_form, url_for(".index"))
            current_app.logger.error(
                f"Unable to handle form submission on endpoint {request.endpoint!r}, "
                f"form fields: {request.form.keys()}"
            )
            flash("Uh oh. There was an error handling your data. Please notify the admin.")

        aliases = db.session.scalars(
            db.select(Username)
            .filter_by(is_primary=False, user_id=user.id)
            .order_by(db.func.coalesce(Username._display_name, Username._username))
        ).all()
        # Additional admin-specific data initialization
        user_count = two_fa_count = pgp_key_count = two_fa_percentage = pgp_key_percentage = None
        all_users: list[User] = []

        # Check if user is admin and add admin-specific data
        if user.is_admin:
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
            all_users = list(
                db.session.scalars(
                    db.select(User).join(Username).order_by(Username._username)
                ).all()
            )
            user_count = len(all_users)

        # Load the business tier price
        business_tier = Tier.business_tier()
        business_tier_display_price = ""
        if business_tier:
            price_usd = business_tier.monthly_amount / 100
            if price_usd % 1 == 0:
                business_tier_display_price = str(int(price_usd))
            else:
                business_tier_display_price = f"{price_usd:.2f}"

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
        display_name_form.display_name.data = (
            user.primary_username.display_name or user.primary_username.username
        )
        directory_visibility_form.show_in_directory.data = user.primary_username.show_in_directory

        return render_template(
            "settings/index.html",
            user=user,
            all_users=all_users,
            update_brand_primary_color_form=update_brand_primary_color_form,
            update_brand_app_name_form=update_brand_app_name_form,
            email_forwarding_form=email_forwarding_form,
            change_password_form=change_password_form,
            change_username_form=change_username_form,
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
            display_name_form=display_name_form,
            profile_form=profile_form,
            new_alias_form=new_alias_form,
            aliases=aliases,
            max_aliases=5,  # TODO hardcoded for now
            # Admin-specific data passed to the template
            is_admin=user.is_admin,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            two_fa_percentage=two_fa_percentage,
            pgp_key_percentage=pgp_key_percentage,
            directory_visibility_form=directory_visibility_form,
            default_forwarding_enabled=bool(current_app.config["NOTIFICATIONS_ADDRESS"]),
            # Premium-specific data
            business_tier_display_price=business_tier_display_price,
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
            flash("⛔️ Invalid form data. Please try again.", "error")
            return redirect(url_for("settings.index"))

        if not user.check_password(change_password_form.old_password.data):
            flash("⛔️ Incorrect old password.", "error")
            return redirect(url_for("settings.index"))

        # SECURITY: only check equality after successful old password check
        if bytes_are_equal(
            change_password_form.old_password.data.encode(),
            change_password_form.new_password.data.encode(),
        ):
            flash("⛔️ Cannot choose a repeat password.", "error")
            return redirect(url_for("settings.index"))

        user.password_hash = change_password_form.new_password.data
        db.session.commit()
        session.clear()
        flash("👍 Password successfully changed. Please log in again.", "success")
        return redirect(url_for("login"))

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
                and pyotp.TOTP(temp_totp_secret).verify(verification_code, valid_window=1)
                and user
            ):
                user.totp_secret = temp_totp_secret
                db.session.commit()
                session.pop("temp_totp_secret", None)
                flash("👍 2FA setup successful. Please log in again with 2FA.")
                return redirect(url_for("logout"))

            flash("⛔️ Invalid 2FA code. Please try again.")
            return redirect(url_for(".enable_2fa"))

        # Generate new 2FA secret and QR code
        temp_totp_secret = pyotp.random_base32()
        session["temp_totp_secret"] = temp_totp_secret
        session["is_setting_up_2fa"] = True
        if user:
            totp_uri = pyotp.totp.TOTP(temp_totp_secret).provisioning_uri(
                name=user.primary_username.username, issuer_name="HushLine"
            )
        img = qrcode.make(totp_uri)
        buffered = io.BytesIO()
        img.save(buffered)
        qr_code_img = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

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
        if not totp.verify(verification_code, valid_window=1):
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

            if pgp_key is None or pgp_key.strip() == "":
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

    @bp.route("/update-brand-primary-color", methods=["POST"])
    @admin_authentication_required
    def update_brand_primary_color() -> Response | str:
        host_org = HostOrganization.fetch_or_default()
        form = UpdateBrandPrimaryColorForm()
        if form.validate_on_submit():
            host_org.brand_primary_hex_color = form.brand_primary_hex_color.data
            db.session.add(host_org)  # explicitly add because instance might be new
            db.session.commit()
            flash("👍 Brand primary color updated successfully.")
            return redirect(url_for(".index"))

        flash("⛔ Invalid form data. Please try again.")
        return redirect(url_for(".index"))

    @bp.route("/update-brand-app-name", methods=["POST"])
    @admin_authentication_required
    def update_brand_app_name() -> Response | str:
        host_org = HostOrganization.fetch_or_default()
        form = UpdateBrandAppNameForm()
        if form.validate_on_submit():
            host_org.brand_app_name = form.brand_app_name.data
            db.session.add(host_org)  # explicitly add because instance might be new
            db.session.commit()
            flash("👍 Brand app name updated successfully.")
            return redirect(url_for(".index"))

        flash("⛔ Invalid form data. Please try again.")
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
            db.session.execute(
                db.delete(Message).filter(
                    Message.username_id.in_(db.select(Username.id).filter_by(user_id=user.id))
                )
            )
            db.session.execute(db.delete(Username).filter_by(user_id=user.id))
            db.session.delete(user)
            db.session.commit()

            session.clear()
            flash("🔥 Your account and all related information have been deleted.")
            return redirect(url_for("index"))

        flash("User not found. Please log in again.")
        return redirect(url_for("login"))

    @authentication_required
    @bp.route("/alias/<int:username_id>", methods=["GET", "POST"])
    async def alias(username_id: int) -> Response | str:
        alias = db.session.scalars(
            db.select(Username).filter_by(
                id=username_id, user_id=session["user_id"], is_primary=False
            )
        ).one_or_none()
        if not alias:
            flash("Alias not found.")
            return redirect(url_for(".index"))

        display_name_form = DisplayNameForm()
        profile_form = ProfileForm()
        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=alias.show_in_directory
        )

        if request.method == "POST":
            if "update_bio" in request.form and profile_form.validate_on_submit():
                return await handle_update_bio(
                    alias, profile_form, url_for(".alias", username_id=username_id)
                )
            if (
                "update_directory_visibility" in request.form
                and directory_visibility_form.validate_on_submit()
            ):
                return handle_update_directory_visibility(
                    alias, directory_visibility_form, url_for(".alias", username_id=username_id)
                )
            if "update_display_name" in request.form and display_name_form.validate_on_submit():
                return handle_display_name_form(
                    alias, display_name_form, url_for(".alias", username_id=username_id)
                )

            current_app.logger.error(
                f"Unable to handle form submission on endpoint {request.endpoint!r}, "
                f"form fields: {request.form.keys()}"
            )
            flash("Uh oh. There was an error handling your data. Please notify the admin.")

        return render_template(
            "settings/alias.html",
            user=alias.user,
            alias=alias,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
        )

    return bp

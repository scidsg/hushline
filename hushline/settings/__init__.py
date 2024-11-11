import asyncio
import base64
import io
import re
from hmac import compare_digest as bytes_are_equal
from typing import Optional, Tuple

import aiohttp
import bleach
import pyotp
import qrcode
import requests
from bleach import clean
from bs4 import BeautifulSoup
from flask import (
    Blueprint,
    abort,
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

from ..auth import admin_authentication_required, authentication_required
from ..crypto import is_valid_pgp_key
from ..db import db
from ..email import create_smtp_config
from ..forms import TwoFactorForm
from ..model import (
    AuthenticationLog,
    Message,
    OrganizationSetting,
    SMTPEncryption,
    Tier,
    User,
    Username,
)
from ..storage import public_store
from ..utils import redirect_to_self
from .forms import (
    ChangePasswordForm,
    ChangeUsernameForm,
    DeleteBrandLogoForm,
    DirectoryVisibilityForm,
    DisplayNameForm,
    EmailForwardingForm,
    NewAliasForm,
    PGPKeyForm,
    PGPProtonForm,
    ProfileForm,
    UpdateBrandAppNameForm,
    UpdateBrandLogoForm,
    UpdateBrandPrimaryColorForm,
    UpdateDirectoryIntroTextForm,
)


def form_error() -> None:
    flash("Your submitted form could not be processed.")


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


async def handle_update_bio(username: Username, form: ProfileForm) -> Response:
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
    return redirect_to_self()


def handle_update_directory_visibility(user: Username, form: DirectoryVisibilityForm) -> Response:
    user.show_in_directory = form.show_in_directory.data
    db.session.commit()
    flash("👍 Directory visibility updated successfully.")
    return redirect_to_self()


def handle_display_name_form(username: Username, form: DisplayNameForm) -> Response:
    username.display_name = (form.display_name.data or "").strip() or None
    db.session.commit()

    flash("👍 Display name updated successfully.")
    current_app.logger.debug(
        f"Display name updated to {username.display_name}, "
        f"Verification status: {username.is_verified}"
    )
    return redirect_to_self()


def handle_change_username_form(username: Username, form: ChangeUsernameForm) -> Response:
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
    return redirect_to_self()


def handle_new_alias_form(user: User, new_alias_form: NewAliasForm) -> Optional[Response]:
    current_app.logger.debug(f"Attempting to create alias for user_id={user.id}")

    count = db.session.scalar(
        db.select(
            db.func.count(Username.id).filter(
                Username.user_id == user.id, Username.is_primary.is_(False)
            )
        )
    )
    if count >= user.max_aliases:
        flash("Your current subscription level does not allow the creation of more aliases.")
        return None

    uname = Username(_username=new_alias_form.username.data, user_id=user.id, is_primary=False)
    db.session.add(uname)
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        if isinstance(e.orig, UniqueViolation) and '"uq_usernames_username"' in str(e.orig):
            flash("💔 This username is already taken.")
            return None
        current_app.logger.error("Error creating username", exc_info=True)
        flash("⛔️ Internal server error. Alias not created.")
        return None
    else:
        flash("👍 Alias created successfully.")
    return redirect_to_self()


def handle_change_password_form(
    user: User, change_password_form: ChangePasswordForm
) -> Optional[Response]:
    if not user.check_password(change_password_form.old_password.data):
        change_password_form.old_password.errors.append("Incorrect old password.")
        return None

    # SECURITY: only check equality after successful old password check
    if bytes_are_equal(
        change_password_form.old_password.data.encode(),
        change_password_form.new_password.data.encode(),
    ):
        change_password_form.new_password.errors.append("Cannot choose a repeat password.")
        return None

    user.password_hash = change_password_form.new_password.data
    db.session.commit()
    session.clear()
    flash("👍 Password successfully changed. Please log in again.", "success")
    return redirect(url_for("login"))


def handle_pgp_key_form(user: User, form: PGPKeyForm) -> Response:
    if not (pgp_key := (form.pgp_key.data or "").strip()):
        user.pgp_key = None
        user.email = None
        db.session.commit()
    elif is_valid_pgp_key(pgp_key):
        user.pgp_key = pgp_key
        db.session.commit()
    else:
        flash("⛔️ Invalid PGP key format or import failed.")
        return redirect(url_for(".email"))

    flash("👍 PGP key updated successfully.")
    return redirect(url_for(".email"))


def handle_email_forwarding_form(
    user: User, form: EmailForwardingForm, default_forwarding_enabled: bool
) -> Optional[Response]:
    if form.email_address.data and not user.pgp_key:
        flash("⛔️ Email forwarding requires a configured PGP key")
        return None

    forwarding_enabled = form.forwarding_enabled.data
    custom_smtp_settings = forwarding_enabled and (
        form.custom_smtp_settings.data or not default_forwarding_enabled
    )

    if custom_smtp_settings:
        try:
            smtp_config = create_smtp_config(
                form.smtp_settings.smtp_username.data,
                form.smtp_settings.smtp_server.data,
                form.smtp_settings.smtp_port.data,
                form.smtp_settings.smtp_password.data or user.smtp_password or "",
                form.smtp_settings.smtp_sender.data,
                encryption=SMTPEncryption[form.smtp_settings.smtp_encryption.data],
            )
            with smtp_config.smtp_login():
                pass
        except Exception as e:
            current_app.logger.debug(e)
            flash("⛔️ Unable to validate SMTP connection settings")
            return None

    user.email = form.email_address.data if forwarding_enabled else None
    user.smtp_server = form.smtp_settings.smtp_server.data if custom_smtp_settings else None
    user.smtp_port = form.smtp_settings.smtp_port.data if custom_smtp_settings else None
    user.smtp_username = form.smtp_settings.smtp_username.data if custom_smtp_settings else None

    # Since passwords aren't pre-populated in the form, don't unset it if not provided
    user.smtp_password = (
        form.smtp_settings.smtp_password.data
        if custom_smtp_settings and form.smtp_settings.smtp_password.data
        else user.smtp_password
    )
    user.smtp_sender = (
        form.smtp_settings.smtp_sender.data
        if custom_smtp_settings and form.smtp_settings.smtp_sender.data
        else None
    )
    user.smtp_encryption = (
        form.smtp_settings.smtp_encryption.data
        if custom_smtp_settings
        else SMTPEncryption.default()
    )

    db.session.commit()
    flash("👍 SMTP settings updated successfully")
    return redirect_to_self()


def create_blueprint() -> Blueprint:
    bp = Blueprint("settings", __file__, url_prefix="/settings")

    @authentication_required
    @bp.route("/profile", methods=["GET", "POST"])
    async def profile() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        username = user.primary_username

        # hush, mypy.
        if username is None:
            raise Exception("Username was unexpectedly none")

        # Fetch the directory intro setting once and use a temporary variable
        directory_intro_setting = OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO)
        directory_intro_text_value = (
            directory_intro_setting.value if directory_intro_setting else ""
        )

        update_directory_intro_text_form = UpdateDirectoryIntroTextForm(
            directory_intro_text=directory_intro_text_value
        )
        directory_visibility_form = DirectoryVisibilityForm(
            show_in_directory=username.show_in_directory
        )
        profile_form = ProfileForm(obj=user)

        status_code = 200
        if request.method == "POST":
            if display_name_form.submit.name in request.form and display_name_form.validate():
                return handle_display_name_form(username, display_name_form)
            elif (
                directory_visibility_form.submit.name in request.form
                and directory_visibility_form.validate()
            ):
                return handle_update_directory_visibility(username, directory_visibility_form)
            elif profile_form.submit.name in request.form and profile_form.validate():
                return await handle_update_bio(username, profile_form)
            else:
                form_error()
                status_code = 400

        business_tier = Tier.business_tier()
        business_tier_display_price = ""
        if business_tier:
            price_usd = business_tier.monthly_amount / 100
            if price_usd % 1 == 0:
                business_tier_display_price = str(int(price_usd))
            else:
                business_tier_display_price = f"{price_usd:.2f}"

        return render_template(
            "settings/profile.html",
            username=username,
            display_name_form=display_name_form,
            directory_visibility_form=directory_visibility_form,
            profile_form=profile_form,
            business_tier_display_price=business_tier_display_price,
        ), status_code

    @authentication_required
    @bp.route("/aliases", methods=["GET", "POST"])
    def aliases() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        new_alias_form = NewAliasForm()

        status_code = 200
        if request.method == "POST":
            if new_alias_form.validate() and (resp := handle_new_alias_form(user, new_alias_form)):
                return resp
            else:
                form_error()
                status_code = 400

        aliases = db.session.scalars(
            db.select(Username)
            .filter_by(is_primary=False, user_id=user.id)
            .order_by(db.func.coalesce(Username._display_name, Username._username))
        ).all()

        return render_template(
            "settings/aliases.html",
            user=user,
            aliases=aliases,
            new_alias_form=new_alias_form,
        ), status_code

    @authentication_required
    @bp.route("/auth", methods=["GET", "POST"])
    def auth() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        change_username_form = ChangeUsernameForm()
        change_password_form = ChangePasswordForm()

        status_code = 200
        if request.method == "POST":
            if change_username_form.submit.name in request.form and change_username_form.validate():
                return handle_change_username_form(user.primary_username, change_username_form)
            elif (
                change_password_form.submit.name in request.form
                and change_password_form.validate()
                and (resp := handle_change_password_form(user, change_password_form))
            ):
                return resp
            else:
                form_error()
                status_code = 400

        return render_template(
            "settings/auth.html",
            user=user,
            change_username_form=change_username_form,
            change_password_form=change_password_form,
        ), status_code

    @authentication_required
    @bp.route("/email", methods=["GET", "POST"])
    def email() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        default_forwarding_enabled = bool(current_app.config.get("NOTIFICATIONS_ADDRESS"))

        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm(pgp_key=user.pgp_key)

        email_forwarding_form = EmailForwardingForm(
            data=dict(
                email_address=user.email,
                custom_smtp_settings=user.smtp_server or None,
            )
        )

        status_code = 200
        if request.method == "POST":
            if pgp_key_form.submit.name in request.form and pgp_key_form.validate():
                return handle_pgp_key_form(user, pgp_key_form)
            elif (
                email_forwarding_form.submit.name in request.form
                and email_forwarding_form.validate()
                and (
                    resp := handle_email_forwarding_form(
                        user, email_forwarding_form, default_forwarding_enabled
                    )
                )
            ):
                return resp
            else:
                form_error()
                status_code = 400
        else:
            # we have to manually populate this because of subforms.
            # only when request isn't a POST so that failed submissions can be easily recreated
            email_forwarding_form.forwarding_enabled.data = user.email is not None
            if not user.pgp_key:
                set_input_disabled(email_forwarding_form.forwarding_enabled)
            email_forwarding_form.custom_smtp_settings.data = user.smtp_server is not None
            email_forwarding_form.smtp_settings.smtp_server.data = user.smtp_server
            email_forwarding_form.smtp_settings.smtp_port.data = user.smtp_port
            email_forwarding_form.smtp_settings.smtp_username.data = user.smtp_username
            email_forwarding_form.smtp_settings.smtp_encryption.data = user.smtp_encryption.value
            email_forwarding_form.smtp_settings.smtp_sender.data = user.smtp_sender

        return render_template(
            "settings/email.html",
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
            email_forwarding_form=email_forwarding_form,
            default_forwarding_enabled=default_forwarding_enabled,
        ), status_code

    @admin_authentication_required
    @bp.route("/branding", methods=["GET", "POST"])
    def branding() -> Tuple[str, int]:
        update_brand_logo_form = UpdateBrandLogoForm()
        delete_brand_logo_form = DeleteBrandLogoForm()
        update_brand_primary_color_form = UpdateBrandPrimaryColorForm()
        update_brand_app_name_form = UpdateBrandAppNameForm()

        status_code = 200
        if request.method == "POST":
            if (
                update_brand_logo_form.submit.name in request.form
                and update_brand_logo_form.validate()
            ):
                public_store.put(
                    OrganizationSetting.BRAND_LOGO_VALUE, update_brand_logo_form.logo.data
                )
                OrganizationSetting.upsert(
                    key=OrganizationSetting.BRAND_LOGO,
                    value=OrganizationSetting.BRAND_LOGO_VALUE,
                )
                flash("👍 Brand logo updated successfully.")
            elif (
                delete_brand_logo_form.submit.name in request.form
                and delete_brand_logo_form.validate()
            ):
                row_count = db.session.execute(
                    db.delete(OrganizationSetting).where(
                        OrganizationSetting.key == OrganizationSetting.BRAND_LOGO
                    )
                ).rowcount
                if row_count > 1:
                    current_app.logger.error(
                        "Would have deleted multiple rows for OrganizationSetting key="
                        + OrganizationSetting.BRAND_LOGO
                    )
                    db.session.rollback()
                    abort(503)
                db.session.commit()
                public_store.delete(OrganizationSetting.BRAND_LOGO_VALUE)
                flash("👍 Brand logo deleted.")
            elif (
                update_brand_primary_color_form.submit.name in request.form
                and update_brand_primary_color_form.validate()
            ):
                OrganizationSetting.upsert(
                    key=OrganizationSetting.BRAND_PRIMARY_COLOR,
                    value=update_brand_primary_color_form.brand_primary_hex_color.data,
                )
                flash("👍 Brand primary color updated successfully.")
            elif (
                update_brand_app_name_form.submit.name in request.form
                and update_brand_app_name_form.validate()
            ):
                OrganizationSetting.upsert(
                    key=OrganizationSetting.BRAND_NAME,
                    value=update_brand_app_name_form.brand_app_name.data,
                )
                flash("👍 Brand app name updated successfully.")
            else:
                form_error()
                status_code = 400

        return render_template(
            "settings/branding.html",
            update_brand_logo_form=update_brand_logo_form,
            delete_brand_logo_form=delete_brand_logo_form,
            update_brand_primary_color_form=update_brand_primary_color_form,
            update_brand_app_name_form=update_brand_app_name_form,
        ), status_code

    @authentication_required
    @bp.route("/advanced")
    def advanced() -> str:
        return render_template("settings/advanced.html")

    @admin_authentication_required
    @bp.route("/admin")
    def admin() -> str:
        all_users = list(
            db.session.scalars(db.select(User).join(Username).order_by(Username._username)).all()
        )
        user_count = len(all_users)
        two_fa_count = sum(1 for _ in filter(lambda x: x._totp_secret, all_users))
        pgp_key_count = sum(1 for _ in filter(lambda x: x._pgp_key, all_users))

        return render_template(
            "settings/admin.html",
            all_users=all_users,
            user_count=user_count,
            two_fa_count=two_fa_count,
            pgp_key_count=pgp_key_count,
            two_fa_percentage=two_fa_percentage,
            pgp_key_percentage=pgp_key_percentage,
            directory_visibility_form=directory_visibility_form,
            default_forwarding_enabled=bool(current_app.config.get("NOTIFICATIONS_ADDRESS")),
            # Premium-specific data
            business_tier_display_price=business_tier_display_price,
            update_directory_intro_text_form=update_directory_intro_text_form,
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
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = PGPProtonForm()

        if not form.validate_on_submit():
            flash("⛔️ Invalid email address.")
            return redirect(url_for(".index"))

        email = form.email.data

        # Try to fetch the PGP key from ProtonMail
        try:
            resp = requests.get(
                # TODO email needs to be URL escaped
                f"https://mail-api.proton.me/pks/lookup?op=get&search={email}",
                timeout=5,
            )
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error fetching PGP key from Proton Mail: {e}")
            flash("⛔️ Error fetching PGP key from Proton Mail.")
            return redirect(url_for(".email"))

        if resp.status_code == 200:  # noqa: PLR2004
            pgp_key = resp.text
            if is_valid_pgp_key(pgp_key):
                user.pgp_key = pgp_key
                db.session.commit()
            else:
                flash("⛔️ No PGP key found for the email address.")
                return redirect(url_for(".email"))
        else:
            flash("⛔️ This isn't a Proton Mail email address.")
            return redirect(url_for(".email"))

        flash("👍 PGP key updated successfully.")
        return redirect(url_for(".email"))

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
            db.session.execute(db.delete(AuthenticationLog).filter_by(user_id=user.id))
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
                return await handle_update_bio(alias, profile_form)
            elif (
                "update_directory_visibility" in request.form
                and directory_visibility_form.validate_on_submit()
            ):
                return handle_update_directory_visibility(alias, directory_visibility_form)
            elif "update_display_name" in request.form and display_name_form.validate_on_submit():
                return handle_display_name_form(alias, display_name_form)
            else:
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


    def sanitize_input(input_text: str) -> str:
        sanitized_text = re.sub(r'<script.*?>.*?</script>', '', input_text, flags=re.DOTALL)
        return clean(
            sanitized_text,
            tags=["b", "i", "u", "em", "strong", "p", "br", "a"],
            attributes={"a": ["href"]},
            strip=True,
        )

    @bp.route("/update-directory-intro", methods=["POST"])
    @admin_authentication_required
    def update_directory_intro_text() -> Response:
        form = UpdateDirectoryIntroTextForm()
        if form.validate_on_submit():
            intro_text = sanitize_input(form.directory_intro_text.data)
            OrganizationSetting.upsert(key=OrganizationSetting.DIRECTORY_INTRO, value=intro_text)
            db.session.commit()
            flash("✅ Directory introduction text updated successfully.", "success")
        else:
            flash("❌ Failed to update introduction text. Please check your input.", "error")

        return redirect(url_for("settings.index"))

    return bp

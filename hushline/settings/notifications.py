import smtplib
from typing import Optional, Tuple

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
from flask_wtf import FlaskForm
from werkzeug.wrappers.response import Response
from wtforms import BooleanField, SubmitField
from wtforms.validators import Optional as OptionalField

from hushline.auth import authentication_required
from hushline.crypto import can_encrypt_with_pgp_key, is_valid_pgp_key
from hushline.db import db
from hushline.email import create_smtp_config, is_safe_smtp_host
from hushline.forms import DisplayNoneButton
from hushline.model import NotificationRecipient, SMTPEncryption, User
from hushline.settings.common import form_error
from hushline.settings.forms import (
    DeleteNotificationRecipientForm,
    EmailForwardingForm,
    NotificationRecipientForm,
    PGPProtonForm,
)
from hushline.settings.proton import lookup_proton_pgp_key
from hushline.utils import redirect_to_self

RECIPIENT_PROTON_LOOKUP_SUBMIT = "search_notification_recipient_proton"


class ToggleNotificationsForm(FlaskForm):
    enable_email_notifications = BooleanField("Tip Notifications", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_notifications", widget=DisplayNoneButton())


class ToggleIncludeContentForm(FlaskForm):
    include_content = BooleanField("Include Message Contents", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_include_content", widget=DisplayNoneButton())


class ToggleEncryptEntireBodyForm(FlaskForm):
    encrypt_entire_body = BooleanField("Encrypt Entire Body", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_encrypt_entire_body", widget=DisplayNoneButton())


class ToggleRecipientEnabledForm(FlaskForm):
    recipient_enabled = BooleanField("Recipient Enabled", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_recipient_enabled", widget=DisplayNoneButton())


def _normalize_recipient_positions(user: User) -> None:
    for index, recipient in enumerate(
        sorted(user.notification_recipients, key=lambda row: (row.position, row.id))
    ):
        recipient.position = index


def _normalize_notification_state(user: User) -> None:
    user.sync_legacy_notification_email()
    if user.enabled_notification_recipients:
        return
    user.enable_email_notifications = False
    user.email_include_message_content = False


def _recipient_key_is_encryptable(pgp_key: str) -> bool:
    return is_valid_pgp_key(pgp_key) and can_encrypt_with_pgp_key(pgp_key)


def _enabled_recipients_support_content(user: User) -> bool:
    recipients = user.enabled_notification_recipients
    if not recipients:
        return False
    return all(
        recipient.pgp_key and _recipient_key_is_encryptable(recipient.pgp_key)
        for recipient in recipients
    )


def _validate_recipient_form(
    user: User,
    form: NotificationRecipientForm,
) -> bool:
    pgp_key = (form.recipient_pgp_key.data or "").strip()
    if pgp_key and not is_valid_pgp_key(pgp_key):
        form.recipient_pgp_key.errors.append("Invalid PGP key format or import failed.")
        return False
    if pgp_key and not can_encrypt_with_pgp_key(pgp_key):
        form.recipient_pgp_key.errors.append(
            "PGP key cannot be used for encryption. Please provide a key with an encryption subkey."
        )
        return False
    if user.email_include_message_content and form.recipient_enabled.data and not pgp_key:
        form.recipient_pgp_key.errors.append(
            "An encryptable PGP key is required for enabled recipients when email content "
            "is included."
        )
        return False
    return True


def _save_recipient(
    user: User,
    form: NotificationRecipientForm,
    recipient: NotificationRecipient | None = None,
) -> Response | None:
    if not form.validate() or not _validate_recipient_form(user, form):
        return None

    if recipient is None:
        recipient = NotificationRecipient(
            user=user,
            enabled=True,
            position=user.next_notification_recipient_position,
        )
        db.session.add(recipient)
        recipient.enabled = bool(form.recipient_enabled.data)

    recipient.email = (form.recipient_email.data or "").strip()
    recipient.pgp_key = (form.recipient_pgp_key.data or "").strip() or None
    if recipient is not None and form.recipient_enabled.name in request.form:
        recipient.enabled = bool(form.recipient_enabled.data)

    _normalize_recipient_positions(user)
    _normalize_notification_state(user)
    db.session.commit()
    flash("👍 Notification recipient updated successfully.")
    return redirect(url_for(".notifications"))


def _delete_recipient(user: User, recipient: NotificationRecipient) -> Response:
    if recipient in user.notification_recipients:
        user.notification_recipients.remove(recipient)
    db.session.flush()
    _normalize_recipient_positions(user)
    _normalize_notification_state(user)
    db.session.commit()
    flash("🗑️ Notification recipient removed.")
    return redirect(url_for(".notifications"))


def _toggle_recipient_enabled(
    user: User,
    recipient: NotificationRecipient,
    form: ToggleRecipientEnabledForm,
) -> Response | None:
    enabled = bool(form.recipient_enabled.data)
    if (
        enabled
        and user.email_include_message_content
        and not (recipient.pgp_key and _recipient_key_is_encryptable(recipient.pgp_key))
    ):
        flash(
            "⛔️ Add an encryptable PGP key before enabling a recipient while message content "
            "is included."
        )
        return None

    recipient.enabled = enabled
    _normalize_notification_state(user)
    db.session.commit()
    if enabled:
        flash("👍 Notification recipient enabled.")
    else:
        flash("👍 Notification recipient disabled.")
    return redirect(url_for(".notification_recipient", recipient_id=recipient.id))


def handle_email_forwarding_form(user: User, form: EmailForwardingForm) -> Optional[Response]:
    default_forwarding_enabled = bool(current_app.config.get("NOTIFICATIONS_ADDRESS"))
    custom_smtp_settings = form.custom_smtp_settings.data or not default_forwarding_enabled

    if custom_smtp_settings:
        try:
            if not is_safe_smtp_host(form.smtp_settings.smtp_server.data or ""):
                flash("⛔️ SMTP server must resolve to a public IP address.")
                return None
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
        except (OSError, ValueError, smtplib.SMTPException) as e:
            current_app.logger.debug(e)
            flash("⛔️ Unable to validate SMTP connection settings.")
            return None

    user.smtp_server = form.smtp_settings.smtp_server.data if custom_smtp_settings else None
    user.smtp_port = form.smtp_settings.smtp_port.data if custom_smtp_settings else None
    user.smtp_username = form.smtp_settings.smtp_username.data if custom_smtp_settings else None
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
    flash("👍 SMTP settings updated successfully.")
    return redirect_to_self()


def _build_recipient_form(
    recipient: NotificationRecipient | None,
    *,
    use_request_data: bool = True,
) -> NotificationRecipientForm:
    if request.method == "POST" and use_request_data:
        return NotificationRecipientForm()

    data = {"recipient_enabled": True}
    if recipient is not None:
        data.update(
            {
                "recipient_email": recipient.email,
                "recipient_pgp_key": recipient.pgp_key,
                "recipient_enabled": recipient.enabled,
            }
        )
    return NotificationRecipientForm(data=data)


def _build_recipient_proton_form(
    recipient: NotificationRecipient | None,
    *,
    use_request_data: bool = True,
) -> PGPProtonForm:
    if request.method == "POST" and use_request_data:
        return PGPProtonForm()

    data = {"email": recipient.email} if recipient is not None and recipient.email else None
    return PGPProtonForm(data=data)


def _handle_recipient_proton_lookup(
    *,
    recipient: NotificationRecipient | None,
    pgp_proton_form: PGPProtonForm,
) -> tuple[NotificationRecipientForm, bool]:
    recipient_form = _build_recipient_form(recipient, use_request_data=False)

    if not pgp_proton_form.validate():
        flash("⛔️ Invalid email address.")
        return recipient_form, False

    email = (pgp_proton_form.email.data or "").strip()
    recipient_form.recipient_email.data = email
    pgp_key, error_message = lookup_proton_pgp_key(email)
    if error_message:
        flash(error_message)
        return recipient_form, False

    recipient_form.recipient_pgp_key.data = pgp_key
    flash("👍 Proton PGP key imported. Review and save the recipient.")
    return recipient_form, True


def _recipient_summary(recipient: NotificationRecipient) -> dict[str, int | str | bool]:
    return {
        "id": recipient.id,
        "email": recipient.email or "No email address",
        "enabled": recipient.enabled,
        "has_pgp_key": bool(recipient.pgp_key),
    }


def _recipient_not_found() -> Response:
    flash("⛔️ Notification recipient not found.")
    return redirect(url_for(".notifications"))


def _recipient_for_user(user: User, recipient_id: int) -> NotificationRecipient | None:
    return next((item for item in user.notification_recipients if item.id == recipient_id), None)


def register_notifications_routes(bp: Blueprint) -> None:
    @bp.route("/notifications", methods=["GET", "POST"])
    @authentication_required
    def notifications() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        toggle_notifications_form = ToggleNotificationsForm()
        toggle_include_content_form = ToggleIncludeContentForm()
        toggle_encrypt_entire_body_form = ToggleEncryptEntireBodyForm()
        email_forwarding_form = EmailForwardingForm(
            data=dict(custom_smtp_settings=user.smtp_server or None)
        )

        submitted_form = None
        for form in (
            toggle_notifications_form,
            toggle_include_content_form,
            toggle_encrypt_entire_body_form,
            email_forwarding_form,
        ):
            submit_field = getattr(form, "submit", None)
            if submit_field is not None and submit_field.name in request.form:
                submitted_form = form
                break

        status_code = 200
        if request.method == "POST":
            if submitted_form is toggle_notifications_form and toggle_notifications_form.validate():
                user.enable_email_notifications = bool(
                    toggle_notifications_form.enable_email_notifications.data
                )
                db.session.commit()
                if toggle_notifications_form.enable_email_notifications.data:
                    flash("👍 Email notifications enabled.")
                else:
                    flash("👍 Email notifications disabled.")
                return redirect_to_self()
            if (
                submitted_form is toggle_include_content_form
                and toggle_include_content_form.validate()
            ):
                if (
                    toggle_include_content_form.include_content.data
                    and not _enabled_recipients_support_content(user)
                ):
                    flash(
                        "⛔️ Add at least one enabled recipient with an encryptable PGP key "
                        "before including message content."
                    )
                    status_code = 400
                else:
                    user.email_include_message_content = bool(
                        toggle_include_content_form.include_content.data
                    )
                    db.session.commit()
                    if toggle_include_content_form.include_content.data:
                        flash("👍 Email message content enabled.")
                    else:
                        flash("👍 Email message content disabled.")
                    return redirect_to_self()
            elif (
                submitted_form is toggle_encrypt_entire_body_form
                and toggle_encrypt_entire_body_form.validate()
            ):
                user.email_encrypt_entire_body = bool(
                    toggle_encrypt_entire_body_form.encrypt_entire_body.data
                )
                db.session.commit()
                if toggle_encrypt_entire_body_form.encrypt_entire_body.data:
                    flash("👍 The entire body of email messages will be encrypted.")
                else:
                    flash("👍 Only encrypted fields of email messages will be encrypted.")
                return redirect_to_self()
            elif (
                submitted_form is email_forwarding_form
                and email_forwarding_form.validate()
                and (resp := handle_email_forwarding_form(user, email_forwarding_form))
            ):
                return resp
            else:
                form_error()
                status_code = 400
        else:
            email_forwarding_form.custom_smtp_settings.data = user.smtp_server is not None
            email_forwarding_form.smtp_settings.smtp_server.data = user.smtp_server
            email_forwarding_form.smtp_settings.smtp_port.data = user.smtp_port
            email_forwarding_form.smtp_settings.smtp_username.data = user.smtp_username
            email_forwarding_form.smtp_settings.smtp_encryption.data = user.smtp_encryption.value
            email_forwarding_form.smtp_settings.smtp_sender.data = user.smtp_sender

        toggle_notifications_form.enable_email_notifications.data = user.enable_email_notifications
        toggle_include_content_form.include_content.data = user.email_include_message_content
        toggle_encrypt_entire_body_form.encrypt_entire_body.data = user.email_encrypt_entire_body

        return render_template(
            "settings/notifications.html",
            user=user,
            recipient_summaries=[
                _recipient_summary(recipient) for recipient in user.notification_recipients
            ],
            default_forwarding_enabled=bool(current_app.config.get("NOTIFICATIONS_ADDRESS")),
            custom_smtp_settings=bool(user.smtp_username),
            toggle_notifications_form=toggle_notifications_form,
            toggle_include_content_form=toggle_include_content_form,
            toggle_encrypt_entire_body_form=toggle_encrypt_entire_body_form,
            email_forwarding_form=email_forwarding_form,
        ), status_code

    @bp.route("/notifications/recipients/new", methods=["GET", "POST"])
    @authentication_required
    def new_notification_recipient() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        recipient_form = _build_recipient_form(None)
        pgp_proton_form = _build_recipient_proton_form(None)
        status_code = 200

        if request.method == "POST":
            if RECIPIENT_PROTON_LOOKUP_SUBMIT in request.form:
                recipient_form, lookup_succeeded = _handle_recipient_proton_lookup(
                    recipient=None,
                    pgp_proton_form=pgp_proton_form,
                )
                status_code = 200 if lookup_succeeded else 400
            elif resp := _save_recipient(user, recipient_form):
                return resp
            else:
                form_error()
                status_code = 400

        return render_template(
            "settings/notification-recipient.html",
            user=user,
            recipient=None,
            recipient_form=recipient_form,
            pgp_proton_form=pgp_proton_form,
            delete_recipient_form=None,
            toggle_recipient_enabled_form=None,
            toggle_include_content_form=None,
            toggle_encrypt_entire_body_form=None,
            page_title="Add Recipient",
            submit_label="Add Recipient",
        ), status_code

    @bp.route("/notifications/recipients/<int:recipient_id>", methods=["GET", "POST"])
    @authentication_required
    def notification_recipient(recipient_id: int) -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        recipient = _recipient_for_user(user, recipient_id)
        if recipient is None:
            return _recipient_not_found()

        recipient_form = _build_recipient_form(recipient)
        pgp_proton_form = _build_recipient_proton_form(recipient)
        toggle_recipient_enabled_form = ToggleRecipientEnabledForm()
        toggle_include_content_form = ToggleIncludeContentForm()
        toggle_encrypt_entire_body_form = ToggleEncryptEntireBodyForm()
        status_code = 200

        if request.method == "POST":
            if RECIPIENT_PROTON_LOOKUP_SUBMIT in request.form:
                recipient_form, lookup_succeeded = _handle_recipient_proton_lookup(
                    recipient=recipient,
                    pgp_proton_form=pgp_proton_form,
                )
                status_code = 200 if lookup_succeeded else 400
            elif (
                toggle_recipient_enabled_form.submit.name in request.form
                and toggle_recipient_enabled_form.validate()
            ):
                if resp := _toggle_recipient_enabled(
                    user, recipient, toggle_recipient_enabled_form
                ):
                    return resp
                form_error()
                status_code = 400
            elif (
                toggle_include_content_form.submit.name in request.form
                and toggle_include_content_form.validate()
            ):
                if (
                    toggle_include_content_form.include_content.data
                    and not _enabled_recipients_support_content(user)
                ):
                    flash(
                        "⛔️ Add at least one enabled recipient with an encryptable PGP key "
                        "before including message content."
                    )
                    status_code = 400
                else:
                    user.email_include_message_content = bool(
                        toggle_include_content_form.include_content.data
                    )
                    db.session.commit()
                    if toggle_include_content_form.include_content.data:
                        flash("👍 Email message content enabled.")
                    else:
                        flash("👍 Email message content disabled.")
                    return redirect(url_for(".notification_recipient", recipient_id=recipient.id))
            elif (
                toggle_encrypt_entire_body_form.submit.name in request.form
                and toggle_encrypt_entire_body_form.validate()
            ):
                user.email_encrypt_entire_body = bool(
                    toggle_encrypt_entire_body_form.encrypt_entire_body.data
                )
                db.session.commit()
                if toggle_encrypt_entire_body_form.encrypt_entire_body.data:
                    flash("👍 The entire body of email messages will be encrypted.")
                else:
                    flash("👍 Only encrypted fields of email messages will be encrypted.")
                return redirect(url_for(".notification_recipient", recipient_id=recipient.id))
            elif resp := _save_recipient(user, recipient_form, recipient):
                return resp
            else:
                form_error()
                status_code = 400

        toggle_recipient_enabled_form.recipient_enabled.data = recipient.enabled
        toggle_include_content_form.include_content.data = user.email_include_message_content
        toggle_encrypt_entire_body_form.encrypt_entire_body.data = user.email_encrypt_entire_body

        return render_template(
            "settings/notification-recipient.html",
            user=user,
            recipient=recipient,
            recipient_form=recipient_form,
            pgp_proton_form=pgp_proton_form,
            delete_recipient_form=DeleteNotificationRecipientForm(),
            toggle_recipient_enabled_form=toggle_recipient_enabled_form,
            toggle_include_content_form=toggle_include_content_form,
            toggle_encrypt_entire_body_form=toggle_encrypt_entire_body_form,
            page_title="Edit Recipient",
            submit_label="Save Recipient",
        ), status_code

    @bp.route("/notifications/recipients/<int:recipient_id>/delete", methods=["POST"])
    @authentication_required
    def delete_notification_recipient(recipient_id: int) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        recipient = _recipient_for_user(user, recipient_id)
        if recipient is None:
            flash("⛔️ Notification recipient not found.")
            return abort(404)

        recipient_form = DeleteNotificationRecipientForm()
        if (
            recipient_form.submit.name not in request.form
            or not recipient_form.validate_on_submit()
        ):
            return abort(400)

        return _delete_recipient(user, recipient)

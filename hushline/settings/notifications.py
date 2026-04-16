import smtplib
from typing import Optional, Tuple

from flask import (
    Blueprint,
    current_app,
    flash,
    render_template,
    request,
    session,
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
from hushline.settings.forms import EmailForwardingForm, NotificationRecipientForm
from hushline.utils import redirect_to_self


class ToggleNotificationsForm(FlaskForm):
    enable_email_notifications = BooleanField("Tip Notifications", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_notifications", widget=DisplayNoneButton())


class ToggleIncludeContentForm(FlaskForm):
    include_content = BooleanField("Include Message Contents", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_include_content", widget=DisplayNoneButton())


class ToggleEncryptEntireBodyForm(FlaskForm):
    encrypt_entire_body = BooleanField("Encrypt Entire Body", validators=[OptionalField()])
    submit = SubmitField("Submit", name="toggle_encrypt_entire_body", widget=DisplayNoneButton())


def _recipient_form_prefix(recipient: NotificationRecipient | None) -> str:
    if recipient is None:
        return "new-recipient"
    return f"recipient-{recipient.id}"


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

    recipient.email = (form.recipient_email.data or "").strip()
    recipient.pgp_key = (form.recipient_pgp_key.data or "").strip() or None
    recipient.enabled = bool(form.recipient_enabled.data)

    _normalize_recipient_positions(user)
    _normalize_notification_state(user)
    db.session.commit()
    flash("👍 Notification recipient updated successfully.")
    return redirect_to_self()


def _delete_recipient(user: User, recipient: NotificationRecipient) -> Response:
    if recipient in user.notification_recipients:
        user.notification_recipients.remove(recipient)
    db.session.flush()
    _normalize_recipient_positions(user)
    _normalize_notification_state(user)
    db.session.commit()
    flash("🗑️ Notification recipient removed.")
    return redirect_to_self()


def _submitted_notifications_form(
    forms: tuple[FlaskForm, ...],
    recipient_forms: list[tuple[NotificationRecipient, NotificationRecipientForm]],
) -> FlaskForm | None:
    for form in forms:
        for field_name in ("submit", "delete_submit"):
            field = getattr(form, field_name, None)
            if field is not None and field.name in request.form:
                return form

    for _, form in recipient_forms:
        for field_name in ("submit", "delete_submit"):
            field = getattr(form, field_name, None)
            if field is not None and field.name in request.form:
                return form

    return None


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
    bind_from_request: bool,
) -> NotificationRecipientForm:
    prefix = _recipient_form_prefix(recipient)
    if bind_from_request:
        return NotificationRecipientForm(prefix=prefix)

    data = None
    if recipient is not None:
        data = {
            "recipient_email": recipient.email,
            "recipient_pgp_key": recipient.pgp_key,
            "recipient_enabled": recipient.enabled,
        }
    return NotificationRecipientForm(prefix=prefix, data=data)


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

        submitted_prefix: str | None = None
        if request.method == "POST":
            if "new-recipient-save_notification_recipient" in request.form:
                submitted_prefix = "new-recipient"
            else:
                for recipient in user.notification_recipients:
                    prefix = _recipient_form_prefix(recipient)
                    if (
                        f"{prefix}-save_notification_recipient" in request.form
                        or f"{prefix}-delete_notification_recipient" in request.form
                    ):
                        submitted_prefix = prefix
                        break

        new_recipient_form = _build_recipient_form(
            None,
            bind_from_request=submitted_prefix == "new-recipient",
        )
        recipient_forms = [
            (
                recipient,
                _build_recipient_form(
                    recipient,
                    bind_from_request=submitted_prefix == _recipient_form_prefix(recipient),
                ),
            )
            for recipient in user.notification_recipients
        ]

        submitted_form = _submitted_notifications_form(
            (
                toggle_notifications_form,
                toggle_include_content_form,
                toggle_encrypt_entire_body_form,
                email_forwarding_form,
                new_recipient_form,
            ),
            recipient_forms,
        )

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
                (
                    submitted_form is email_forwarding_form
                    and email_forwarding_form.validate()
                    and (resp := handle_email_forwarding_form(user, email_forwarding_form))
                )
                or submitted_form is new_recipient_form
                and (resp := _save_recipient(user, new_recipient_form))
            ):
                return resp
            else:
                for recipient, form in recipient_forms:
                    if submitted_form is not form:
                        continue
                    if form.delete_submit.name in request.form:
                        return _delete_recipient(user, recipient)
                    if resp := _save_recipient(user, form, recipient):
                        return resp
                    break

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
            default_forwarding_enabled=bool(current_app.config.get("NOTIFICATIONS_ADDRESS")),
            custom_smtp_settings=bool(user.smtp_username),
            toggle_notifications_form=toggle_notifications_form,
            toggle_include_content_form=toggle_include_content_form,
            toggle_encrypt_entire_body_form=toggle_encrypt_entire_body_form,
            email_forwarding_form=email_forwarding_form,
            new_recipient_form=new_recipient_form,
            recipient_forms=recipient_forms,
        ), status_code

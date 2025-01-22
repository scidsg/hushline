from typing import Optional, Tuple

from flask import (
    Blueprint,
    current_app,
    flash,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.email import create_smtp_config
from hushline.model import (
    SMTPEncryption,
    User,
)
from hushline.settings.common import form_error, set_input_disabled
from hushline.settings.forms import EmailForwardingForm
from hushline.utils import redirect_to_self


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


def register_notifications_routes(bp: Blueprint) -> None:
    @bp.route("/notifications", methods=["GET", "POST"])
    @authentication_required
    def notifications() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        default_forwarding_enabled = bool(current_app.config.get("NOTIFICATIONS_ADDRESS"))

        email_forwarding_form = EmailForwardingForm(
            data=dict(
                email_address=user.email,
                custom_smtp_settings=user.smtp_server or None,
            )
        )

        status_code = 200
        if request.method == "POST":
            if (
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
            "settings/notifications.html",
            user=user,
            email_forwarding_form=email_forwarding_form,
            default_forwarding_enabled=default_forwarding_enabled,
        ), status_code

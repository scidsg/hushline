from typing import Tuple

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import User
from hushline.settings.common import (
    form_error,
    handle_email_forwarding_form,
    set_input_disabled,
)
from hushline.settings.forms import EmailForwardingForm


def register_notifications_routes(bp: Blueprint) -> None:
    @bp.route("/email", methods=["GET", "POST"])
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

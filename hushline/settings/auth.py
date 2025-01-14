from typing import Tuple

from flask import (
    Blueprint,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    User,
)
from hushline.settings.common import (
    form_error,
    handle_change_password_form,
    handle_change_username_form,
)
from hushline.settings.forms import (
    ChangePasswordForm,
    ChangeUsernameForm,
)


def register_auth_routes(bp: Blueprint) -> None:
    @bp.route("/auth", methods=["GET", "POST"])
    @authentication_required
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

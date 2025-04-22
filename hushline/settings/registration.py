import json
from typing import Tuple

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
from werkzeug.wrappers.response import Response

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import (
    OrganizationSetting,
    User,
)
from hushline.settings.common import (
    form_error,
)
from hushline.settings.forms import (
    UserGuidanceAddPromptForm,
    UserGuidanceEmergencyExitForm,
    UserGuidanceForm,
    UserGuidancePromptContentForm,
)


def register_registration_routes(bp: Blueprint) -> None:
    @bp.route("/registration", methods=["GET", "POST"])
    @admin_authentication_required
    def registration() -> Tuple[str, int] | Response:
        return render_template(
            "settings/registration.html",
        ), 200

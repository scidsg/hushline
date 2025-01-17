from typing import Tuple

from flask import (
    Blueprint,
    render_template,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required


def register_fields_routes(bp: Blueprint) -> None:
    @bp.route("/fields", methods=["GET", "POST"])
    @authentication_required
    def fields() -> Response | Tuple[str, int]:
        return render_template(
            "settings/fields.html",
        ), 200

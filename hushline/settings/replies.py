from typing import Tuple

from flask import (
    Blueprint,
    flash,
    render_template,
    request,
    session,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import MessageStatus, MessageStatusText
from hushline.settings.common import form_error
from hushline.settings.forms import (
    SetMessageStatusTextForm,
)
from hushline.utils import redirect_to_self


def register_replies_routes(bp: Blueprint) -> None:
    @bp.route("/replies", methods=["GET", "POST"])
    @authentication_required
    def replies() -> Response | Tuple[str, int]:
        form = SetMessageStatusTextForm()
        status_code = 200
        if request.method == "POST":
            if form.validate():
                MessageStatusText.upsert(
                    session["user_id"], MessageStatus[form.status.data.upper()], form.markdown.data
                )
                db.session.commit()
                flash("👍 Reply text set.")
                return redirect_to_self()
            else:
                flash(f"⛔️ {form.errors}.")
                form_error()
                status_code = 400

        return render_template(
            "settings/replies.html",
            form_maker=lambda status, text: SetMessageStatusTextForm(
                status=status.value, markdown=text
            ),
            status_tuples=MessageStatusText.statuses_for_user(session["user_id"]),
        ), status_code

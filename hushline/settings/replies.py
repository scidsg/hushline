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


def _status_text_forms(
    user_id: int, submitted_form: SetMessageStatusTextForm | None = None
) -> list[tuple[MessageStatus, SetMessageStatusTextForm]]:
    status_forms = []
    for status, msg_status_text in MessageStatusText.statuses_for_user(user_id):
        if submitted_form is not None and submitted_form.status.data == status.value:
            form = submitted_form
        else:
            form = SetMessageStatusTextForm(
                formdata=None,
                status=status.value,
                markdown=msg_status_text.markdown
                if msg_status_text and msg_status_text.markdown
                else "",
            )
        status_forms.append((status, form))
    return status_forms


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
            status_forms=_status_text_forms(
                session["user_id"], submitted_form=form if request.method == "POST" else None
            ),
        ), status_code

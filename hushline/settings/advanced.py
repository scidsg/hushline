from flask import (
    Blueprint,
    render_template,
    session,
)

from hushline.auth import authentication_required
from hushline.db import db
from hushline.model import (
    User,
)
from hushline.settings.forms import DataExportForm


def register_advanced_routes(bp: Blueprint) -> None:
    @bp.route("/advanced")
    @authentication_required
    def advanced() -> str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        data_export_form = DataExportForm()
        data_export_form.encrypt_export.data = bool(user.pgp_key)
        return render_template(
            "settings/advanced.html",
            user=user,
            data_export_form=data_export_form,
        )

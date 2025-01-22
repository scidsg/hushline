from typing import Tuple

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.crypto import is_valid_pgp_key
from hushline.db import db
from hushline.model import User
from hushline.settings.common import form_error
from hushline.settings.forms import (
    PGPKeyForm,
    PGPProtonForm,
)


def register_encryption_routes(bp: Blueprint) -> None:
    @bp.route("/encryption", methods=["GET", "POST"])
    @authentication_required
    def encryption() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm(pgp_key=user.pgp_key)

        status_code = 200
        if request.method == "POST":
            if pgp_key_form.submit.name in request.form and pgp_key_form.validate():
                if not (pgp_key := (pgp_key_form.pgp_key.data or "").strip()):
                    user.pgp_key = None
                    user.email = None
                    db.session.commit()
                elif is_valid_pgp_key(pgp_key):
                    user.pgp_key = pgp_key
                    db.session.commit()
                else:
                    flash("⛔️ Invalid PGP key format or import failed.")
                    return redirect(url_for(".encryption"))
                flash("👍 PGP key updated successfully.")
                return redirect(url_for(".encryption"))
            else:
                form_error()
                status_code = 400

        return render_template(
            "settings/encryption.html",
            user=user,
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
        ), status_code

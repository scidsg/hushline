import requests
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.crypto import can_encrypt_with_pgp_key, is_valid_pgp_key
from hushline.db import db
from hushline.model import User
from hushline.settings.forms import PGPProtonForm

HTTP_OK = 200


def lookup_proton_pgp_key(email: str) -> tuple[str | None, str | None]:
    try:
        resp = requests.get(
            "https://mail-api.proton.me/pks/lookup",
            params={"op": "get", "search": email},
            timeout=5,
        )
    except requests.exceptions.RequestException as exc:
        current_app.logger.error("Error fetching PGP key from Proton Mail: %s", exc)
        return None, "⛔️ Error fetching PGP key from Proton Mail."

    if resp.status_code != HTTP_OK:
        return None, "⛔️ This isn't a Proton Mail email address."

    pgp_key = resp.text
    if not is_valid_pgp_key(pgp_key):
        return None, "⛔️ No PGP key found for the email address."
    if not can_encrypt_with_pgp_key(pgp_key):
        return (
            None,
            "⛔️ PGP key cannot be used for encryption. Please provide a key with an "
            "encryption subkey.",
        )

    return pgp_key, None


def register_proton_routes(bp: Blueprint) -> None:
    @bp.route("/update_pgp_key_proton", methods=["POST"])
    @authentication_required
    def update_pgp_key_proton() -> Response | str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = PGPProtonForm()

        if not form.validate_on_submit():
            flash("⛔️ Invalid email address.")
            return redirect(url_for(".encryption"))

        email = form.email.data
        pgp_key, error_message = lookup_proton_pgp_key(email)
        if error_message:
            flash(error_message)
            return redirect(url_for(".encryption"))

        user.pgp_key = pgp_key
        db.session.commit()
        flash("👍 PGP key updated successfully.")
        return redirect(url_for(".encryption"))

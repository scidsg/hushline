from datetime import UTC, datetime
from typing import Any, Tuple

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    session,
)
from flask_wtf.csrf import generate_csrf, validate_csrf
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import authentication_required
from hushline.chat_key_lifecycle import (
    chat_key_fingerprint,
    rewrap_active_chat_key,
    validate_chat_key_payload,
)
from hushline.db import db
from hushline.model import ChatKey, User
from hushline.settings.common import (
    form_error,
    handle_pgp_key_form,
)
from hushline.settings.forms import (
    PGPKeyForm,
    PGPProtonForm,
)


def _submitted_encryption_form(pgp_key_form: PGPKeyForm) -> PGPKeyForm | None:
    if pgp_key_form.submit.name in request.form:
        return pgp_key_form
    return None


def _validate_json_csrf() -> str | None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None

    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError:
        return "Invalid CSRF token."
    return None


def _chat_key_response(chat_key: ChatKey | None) -> dict[str, Any]:
    if chat_key is None:
        return {"chat_key": None}

    return {
        "chat_key": {
            "id": chat_key.id,
            "key_version": chat_key.key_version,
            "public_key": chat_key.public_key,
            "public_key_fingerprint": chat_key_fingerprint(chat_key.public_key),
            "public_signing_key": chat_key.public_signing_key,
            "public_signing_key_fingerprint": chat_key_fingerprint(chat_key.public_signing_key),
            "encrypted_private_key": chat_key.encrypted_private_key,
            "kdf_algorithm": chat_key.kdf_algorithm,
            "kdf_params": chat_key.kdf_params,
            "kdf_salt": chat_key.kdf_salt,
            "wrapping_algorithm": chat_key.wrapping_algorithm,
            "created_at": chat_key.created_at.isoformat(),
            "rotated_at": chat_key.rotated_at.isoformat() if chat_key.rotated_at else None,
            "disabled_at": chat_key.disabled_at.isoformat() if chat_key.disabled_at else None,
            "recovery_state": chat_key.recovery_state,
        }
    }


def register_encryption_routes(bp: Blueprint) -> None:
    @bp.route("/encryption", methods=["GET", "POST"])
    @authentication_required
    def encryption() -> Response | Tuple[str, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        pgp_proton_form = PGPProtonForm()
        pgp_key_form = PGPKeyForm(pgp_key=user.pgp_key)
        submitted_form = _submitted_encryption_form(pgp_key_form)

        status_code = 200
        if request.method == "POST":
            if submitted_form is pgp_key_form and pgp_key_form.validate():
                return handle_pgp_key_form(user, pgp_key_form)
            else:
                form_error()
                status_code = 400

        return render_template(
            "settings/encryption.html",
            user=user,
            pgp_proton_form=pgp_proton_form,
            pgp_key_form=pgp_key_form,
            chat_key=user.active_chat_key,
            chat_key_fingerprint=chat_key_fingerprint,
            chat_key_history=[
                chat_key for chat_key in user.chat_keys if chat_key.disabled_at is not None
            ],
            locked_chat_key=next(
                (
                    chat_key
                    for chat_key in user.chat_keys
                    if chat_key.recovery_state == "password_reset_locked"
                ),
                None,
            ),
            chat_key_csrf_token=generate_csrf(),
        ), status_code

    @bp.route("/chat-key.json", methods=["GET", "POST"])
    @authentication_required
    def chat_key() -> Response | tuple[Response, int]:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        if request.method == "GET":
            return jsonify(_chat_key_response(user.active_chat_key))

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return jsonify({"error": csrf_error}), 400

        payload = request.get_json(silent=True)
        cleaned_payload, error = validate_chat_key_payload(payload, current_user_id=user.id)
        if error:
            status_code = 403 if error.startswith("Chat keys can only") else 400
            return jsonify({"error": error}), status_code

        now = datetime.now(UTC)
        active_key = user.active_chat_key
        new_chat_key = rewrap_active_chat_key(user, cleaned_payload, when=now)
        if new_chat_key is None:
            next_version = max((chat_key.key_version for chat_key in user.chat_keys), default=0) + 1
            new_chat_key = ChatKey(
                user=user,
                key_version=next_version,
                public_key=cleaned_payload["public_key"],
                public_signing_key=cleaned_payload["public_signing_key"],
                encrypted_private_key=cleaned_payload["encrypted_private_key"],
                kdf_algorithm=cleaned_payload["kdf_algorithm"],
                kdf_params=cleaned_payload["kdf_params"],
                kdf_salt=cleaned_payload["kdf_salt"],
                wrapping_algorithm=cleaned_payload["wrapping_algorithm"],
                recovery_state=cleaned_payload["recovery_state"],
            )
        elif active_key is not None:
            active_key.recovery_state = "rotated"
        db.session.add(new_chat_key)
        db.session.commit()

        return jsonify(_chat_key_response(new_chat_key)), 201

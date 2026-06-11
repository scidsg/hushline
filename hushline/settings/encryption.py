import json
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

CHAT_KEY_STRING_MAX_LENGTH = 200_000
CHAT_KEY_METADATA_MAX_LENGTH = 20_000
CHAT_KEY_RECOVERY_STATE_MAX_LENGTH = 64
CHAT_KEY_FORBIDDEN_SECRET_FIELDS = {
    "decrypted_message_text",
    "decrypted_private_key",
    "derived_key",
    "password",
    "plaintext_private_key",
    "private_key",
    "unlock_key",
    "wrapping_key",
}


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


def _normalized_payload_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _payload_contains_forbidden_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if (
                isinstance(key, str)
                and _normalized_payload_key(key) in CHAT_KEY_FORBIDDEN_SECRET_FIELDS
            ):
                return True
            if _payload_contains_forbidden_secret_field(nested_value):
                return True
    elif isinstance(value, list):
        return any(_payload_contains_forbidden_secret_field(item) for item in value)
    return False


def _payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _validate_chat_key_payload(payload: Any, *, current_user_id: int) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        return {}, "Expected a JSON object."

    if _payload_contains_forbidden_secret_field(payload):
        return {}, "Plaintext chat key material is not accepted."

    payload_user_id = payload.get("user_id")
    if payload_user_id is not None and payload_user_id != current_user_id:
        return {}, "Chat keys can only be provisioned for the authenticated user."

    public_key = _payload_text(payload, "public_key", "chat_public_key")
    encrypted_private_key = _payload_text(
        payload,
        "encrypted_private_key",
        "encrypted_private_key_blob",
    )
    kdf_algorithm = _payload_text(payload, "kdf_algorithm")
    kdf_salt = _payload_text(payload, "kdf_salt", "salt")
    wrapping_algorithm = _payload_text(payload, "wrapping_algorithm") or "AES-GCM"
    kdf_params = payload.get("kdf_params")

    kdf = payload.get("kdf")
    if isinstance(kdf, dict):
        if kdf_algorithm is None:
            kdf_algorithm = _payload_text(kdf, "algorithm")
        if kdf_salt is None:
            kdf_salt = _payload_text(kdf, "salt")
        if kdf_params is None:
            kdf_params = kdf.get("params")

    if not public_key:
        return {}, "public_key is required."
    if not encrypted_private_key:
        return {}, "encrypted_private_key is required."
    if not kdf_algorithm:
        return {}, "kdf_algorithm is required."
    if not kdf_salt:
        return {}, "kdf_salt is required."
    if not isinstance(kdf_params, dict) or not kdf_params:
        return {}, "kdf_params must be a non-empty object."

    string_fields = {
        "public_key": public_key,
        "encrypted_private_key": encrypted_private_key,
        "kdf_algorithm": kdf_algorithm,
        "kdf_salt": kdf_salt,
        "wrapping_algorithm": wrapping_algorithm,
    }
    if any(len(value) > CHAT_KEY_STRING_MAX_LENGTH for value in string_fields.values()):
        return {}, "Chat key payload is too large."

    try:
        serialized_kdf_params = json.dumps(kdf_params, sort_keys=True)
    except (TypeError, ValueError):
        return {}, "kdf_params must be JSON serializable."
    if len(serialized_kdf_params) > CHAT_KEY_METADATA_MAX_LENGTH:
        return {}, "kdf_params is too large."

    recovery_state = _payload_text(payload, "recovery_state")
    if recovery_state is not None and len(recovery_state) > CHAT_KEY_RECOVERY_STATE_MAX_LENGTH:
        return {}, "recovery_state is too large."

    return {
        "public_key": public_key,
        "encrypted_private_key": encrypted_private_key,
        "kdf_algorithm": kdf_algorithm,
        "kdf_params": kdf_params,
        "kdf_salt": kdf_salt,
        "wrapping_algorithm": wrapping_algorithm,
        "recovery_state": recovery_state,
    }, ""


def _chat_key_response(chat_key: ChatKey | None) -> dict[str, Any]:
    if chat_key is None:
        return {"chat_key": None}

    return {
        "chat_key": {
            "id": chat_key.id,
            "key_version": chat_key.key_version,
            "public_key": chat_key.public_key,
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
        cleaned_payload, error = _validate_chat_key_payload(payload, current_user_id=user.id)
        if error:
            status_code = 403 if error.startswith("Chat keys can only") else 400
            return jsonify({"error": error}), status_code

        now = datetime.now(UTC)
        active_key = user.active_chat_key
        next_version = max((chat_key.key_version for chat_key in user.chat_keys), default=0) + 1
        if active_key is not None:
            active_key.disabled_at = now
            active_key.recovery_state = "rotated"

        new_chat_key = ChatKey(
            user=user,
            key_version=next_version,
            public_key=cleaned_payload["public_key"],
            encrypted_private_key=cleaned_payload["encrypted_private_key"],
            kdf_algorithm=cleaned_payload["kdf_algorithm"],
            kdf_params=cleaned_payload["kdf_params"],
            kdf_salt=cleaned_payload["kdf_salt"],
            wrapping_algorithm=cleaned_payload["wrapping_algorithm"],
            rotated_at=now if active_key is not None else None,
            recovery_state=cleaned_payload["recovery_state"],
        )
        db.session.add(new_chat_key)
        db.session.commit()

        return jsonify(_chat_key_response(new_chat_key)), 201

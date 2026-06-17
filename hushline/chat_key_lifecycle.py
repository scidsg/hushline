import base64
import binascii
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from hushline.db import db
from hushline.model import ChatKey, User

CHAT_KEY_STRING_MAX_LENGTH = 200_000
CHAT_KEY_METADATA_MAX_LENGTH = 20_000
CHAT_KEY_RECOVERY_STATE_MAX_LENGTH = 64
CHAT_KEY_KDF_ALGORITHM = "PBKDF2-SHA-256"
CHAT_KEY_KDF_HASH = "SHA-256"
CHAT_KEY_KDF_MIN_ITERATIONS = 310_000
CHAT_KEY_KDF_SALT_BYTES = 16
CHAT_KEY_WRAPPING_ALGORITHM = "AES-GCM"
CHAT_KEY_WRAPPING_IV_BYTES = 12
CHAT_KEY_WRAPPED_PRIVATE_KEY_FIELDS = {"algorithm", "iv", "ciphertext"}
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


def normalized_payload_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def payload_contains_forbidden_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if (
                isinstance(key, str)
                and normalized_payload_key(key) in CHAT_KEY_FORBIDDEN_SECRET_FIELDS
            ):
                return True
            if payload_contains_forbidden_secret_field(nested_value):
                return True
    elif isinstance(value, list):
        return any(payload_contains_forbidden_secret_field(item) for item in value)
    return False


def payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def chat_key_fingerprint(public_key: str | None) -> str | None:
    if not public_key:
        return None

    try:
        parsed = json.loads(public_key)
        key_material = _canonical_json(parsed)
    except (TypeError, ValueError):
        key_material = public_key.strip()

    digest = sha256(key_material.encode("utf-8")).hexdigest().upper()
    return ":".join(digest[index : index + 4] for index in range(0, 32, 4))


def _valid_public_jwk(value: str, *, expected_use: str) -> bool:
    try:
        jwk = json.loads(value)
    except (TypeError, ValueError):
        return False

    if not isinstance(jwk, dict):
        return False
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        return False
    if not all(isinstance(jwk.get(field), str) and jwk[field] for field in ("x", "y")):
        return False
    key_ops = jwk.get("key_ops")
    if key_ops is not None and not (
        isinstance(key_ops, list) and all(isinstance(item, str) for item in key_ops)
    ):
        return False
    if expected_use == "signing" and key_ops and "verify" not in key_ops:
        return False
    if expected_use == "agreement" and key_ops and "deriveKey" not in key_ops:
        return False
    return True


def _base64_bytes(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    return decoded or None


def _validate_wrapped_private_key(value: str) -> str:
    try:
        wrapped_private_key = json.loads(value)
    except (TypeError, ValueError):
        return "encrypted_private_key must be a JSON object."

    if not isinstance(wrapped_private_key, dict):
        return "encrypted_private_key must be a JSON object."
    if set(wrapped_private_key) != CHAT_KEY_WRAPPED_PRIVATE_KEY_FIELDS:
        return "encrypted_private_key contains unsupported fields."
    if wrapped_private_key.get("algorithm") != CHAT_KEY_WRAPPING_ALGORITHM:
        return "encrypted_private_key algorithm must be AES-GCM."
    iv = _base64_bytes(wrapped_private_key.get("iv"))
    if iv is None:
        return "encrypted_private_key iv must be non-empty base64."
    if len(iv) != CHAT_KEY_WRAPPING_IV_BYTES:
        return "encrypted_private_key iv must be 12 bytes."
    if _base64_bytes(wrapped_private_key.get("ciphertext")) is None:
        return "encrypted_private_key ciphertext must be non-empty base64."
    return ""


def validate_chat_key_payload(payload: Any, *, current_user_id: int) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        return {}, "Expected a JSON object."

    if payload_contains_forbidden_secret_field(payload):
        return {}, "Plaintext chat key material is not accepted."

    payload_user_id = payload.get("user_id")
    if payload_user_id is not None and payload_user_id != current_user_id:
        return {}, "Chat keys can only be provisioned for the authenticated user."

    public_key = payload_text(payload, "public_key", "chat_public_key")
    public_signing_key = payload_text(payload, "public_signing_key", "signing_public_key")
    encrypted_private_key = payload_text(
        payload,
        "encrypted_private_key",
        "encrypted_private_key_blob",
    )
    kdf_algorithm = payload_text(payload, "kdf_algorithm")
    kdf_salt = payload_text(payload, "kdf_salt", "salt")
    wrapping_algorithm = payload_text(payload, "wrapping_algorithm") or CHAT_KEY_WRAPPING_ALGORITHM
    kdf_params = payload.get("kdf_params")

    kdf = payload.get("kdf")
    if isinstance(kdf, dict):
        if kdf_algorithm is None:
            kdf_algorithm = payload_text(kdf, "algorithm")
        if kdf_salt is None:
            kdf_salt = payload_text(kdf, "salt")
        if kdf_params is None:
            kdf_params = kdf.get("params")

    if not public_key:
        return {}, "public_key is required."
    if not _valid_public_jwk(public_key, expected_use="agreement"):
        return {}, "public_key must be a P-256 ECDH public JWK."
    if public_signing_key and not _valid_public_jwk(public_signing_key, expected_use="signing"):
        return {}, "public_signing_key must be a P-256 ECDSA public JWK."
    if not encrypted_private_key:
        return {}, "encrypted_private_key is required."
    if not kdf_algorithm:
        return {}, "kdf_algorithm is required."
    if kdf_algorithm != CHAT_KEY_KDF_ALGORITHM:
        return {}, "kdf_algorithm must be PBKDF2-SHA-256."
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
    if public_signing_key:
        string_fields["public_signing_key"] = public_signing_key
    if any(len(value) > CHAT_KEY_STRING_MAX_LENGTH for value in string_fields.values()):
        return {}, "Chat key payload is too large."

    if kdf_params.get("hash") != CHAT_KEY_KDF_HASH:
        return {}, "kdf_params.hash must be SHA-256."
    iterations = kdf_params.get("iterations")
    if not isinstance(iterations, int) or isinstance(iterations, bool):
        return {}, "kdf_params.iterations must be an integer."
    if iterations < CHAT_KEY_KDF_MIN_ITERATIONS:
        return {}, "kdf_params.iterations is below the minimum."
    salt = _base64_bytes(kdf_salt)
    if salt is None:
        return {}, "kdf_salt must be non-empty base64."
    if len(salt) != CHAT_KEY_KDF_SALT_BYTES:
        return {}, "kdf_salt must be 16 bytes."
    if wrapping_algorithm != CHAT_KEY_WRAPPING_ALGORITHM:
        return {}, "wrapping_algorithm must be AES-GCM."
    wrapped_private_key_error = _validate_wrapped_private_key(encrypted_private_key)
    if wrapped_private_key_error:
        return {}, wrapped_private_key_error

    try:
        serialized_kdf_params = json.dumps(kdf_params, sort_keys=True)
    except (TypeError, ValueError):
        return {}, "kdf_params must be JSON serializable."
    if len(serialized_kdf_params) > CHAT_KEY_METADATA_MAX_LENGTH:
        return {}, "kdf_params is too large."

    recovery_state = payload_text(payload, "recovery_state")
    if recovery_state is not None and len(recovery_state) > CHAT_KEY_RECOVERY_STATE_MAX_LENGTH:
        return {}, "recovery_state is too large."

    return {
        "public_key": public_key,
        "public_signing_key": public_signing_key,
        "encrypted_private_key": encrypted_private_key,
        "kdf_algorithm": kdf_algorithm,
        "kdf_params": kdf_params,
        "kdf_salt": kdf_salt,
        "wrapping_algorithm": wrapping_algorithm,
        "recovery_state": recovery_state,
    }, ""


def retire_active_chat_key(
    user: User, *, recovery_state: str, when: datetime | None = None
) -> bool:
    active_key = user.active_chat_key
    if active_key is None:
        return False

    active_key.disabled_at = when or datetime.now(UTC)
    active_key.recovery_state = recovery_state
    return True


def rewrap_active_chat_key(
    user: User, payload: dict[str, Any], *, when: datetime | None = None
) -> ChatKey | None:
    active_key = user.active_chat_key
    if active_key is None:
        return None

    now = when or datetime.now(UTC)
    active_key.disabled_at = now
    active_key.recovery_state = "rewrapped"

    next_version = max((chat_key.key_version for chat_key in user.chat_keys), default=0) + 1
    new_chat_key = ChatKey(
        user=user,
        key_version=next_version,
        public_key=payload["public_key"],
        public_signing_key=payload["public_signing_key"],
        encrypted_private_key=payload["encrypted_private_key"],
        kdf_algorithm=payload["kdf_algorithm"],
        kdf_params=payload["kdf_params"],
        kdf_salt=payload["kdf_salt"],
        wrapping_algorithm=payload["wrapping_algorithm"],
        rotated_at=now,
        recovery_state=payload["recovery_state"],
    )
    db.session.add(new_chat_key)
    return new_chat_key

import json
from datetime import UTC, datetime
from typing import Any

from hushline.db import db
from hushline.model import ChatKey, User

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


def validate_chat_key_payload(payload: Any, *, current_user_id: int) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        return {}, "Expected a JSON object."

    if payload_contains_forbidden_secret_field(payload):
        return {}, "Plaintext chat key material is not accepted."

    payload_user_id = payload.get("user_id")
    if payload_user_id is not None and payload_user_id != current_user_id:
        return {}, "Chat keys can only be provisioned for the authenticated user."

    public_key = payload_text(payload, "public_key", "chat_public_key")
    encrypted_private_key = payload_text(
        payload,
        "encrypted_private_key",
        "encrypted_private_key_blob",
    )
    kdf_algorithm = payload_text(payload, "kdf_algorithm")
    kdf_salt = payload_text(payload, "kdf_salt", "salt")
    wrapping_algorithm = payload_text(payload, "wrapping_algorithm") or "AES-GCM"
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

    recovery_state = payload_text(payload, "recovery_state")
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

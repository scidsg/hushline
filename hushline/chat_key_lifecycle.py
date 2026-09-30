import base64
import binascii
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from hushline.db import db
from hushline.model import (
    ChatAccount,
    ChatArchiveEpoch,
    ChatDevice,
    ChatKey,
    ChatOneTimePrekey,
    ChatSignedPrekey,
    User,
)

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

PQ_CHAT_PROTOCOL = "HL-PQCHAT-1"
PQ_CHAT_PROTOCOL_VERSION = 1
PQ_CHAT_TRANSPORT_SUITE = "SIGNAL-PQXDH3-KYBER1024-SPQR1"
PQ_CHAT_ARCHIVE_SUITE = "MLKEM768-X25519-HKDF-SHA256-AES256GCM"
PQ_CHAT_ARCHIVE_MIN_BYTES = 1136
PQ_CHAT_CIPHERTEXT_MAX_BYTES = 200_000
PQ_CHAT_MIN_COPIES = 2
PQ_CHAT_MAX_COPIES = 202
PQ_CHAT_MANIFEST_MAX_BYTES = 100_000
PQ_CHAT_REQUEST_MAX_BYTES = 55_000_000
PQ_CHAT_ZERO_DEVICE_ID = "00000000-0000-0000-0000-000000000000"
PQ_CHAT_SIGNATURE_DOMAIN = b"HushLine/HL-PQCHAT-1/manifest-signature/v1"
_ED25519_PUBLIC_KEY_BYTES = 32
_ED25519_SIGNATURE_BYTES = 64
_PQ_CHAT_HEX_256 = re.compile(r"^[0-9a-f]{64}$")
_PQ_CHAT_CONTEXT_FIELDS = {
    "account_recipient_id",
    "archive_epoch",
    "capability_offer",
    "capability_selection",
    "conversation_id",
    "device_recipient_id",
    "key_version",
    "message_id",
    "protocol",
    "purpose",
    "recipient_membership_sequence",
    "sender_account_id",
    "sender_device_id",
    "sender_membership_sequence",
    "suite",
}
_PQ_CHAT_MANIFEST_FIELDS = {
    "capability_offer",
    "capability_selection",
    "conversation_id",
    "copies",
    "created_at",
    "message_id",
    "protocol",
    "sender_account_id",
    "sender_device_id",
    "sender_membership_sha256",
}
_PQ_CHAT_MANIFEST_COPY_FIELDS = {
    "account_recipient_id",
    "archive_epoch",
    "ciphertext_length",
    "ciphertext_sha256",
    "context_sha256",
    "device_recipient_id",
    "key_version",
    "purpose",
}


class PqChatPackageError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ValidatedPqChatCopy:
    context: dict[str, Any]
    ciphertext: str
    ciphertext_bytes: bytes
    context_sha256: str
    ciphertext_sha256: str


@dataclass(frozen=True)
class ValidatedPqChatPackage:
    manifest: dict[str, Any]
    signature: str
    signature_bytes: bytes
    copies: tuple[ValidatedPqChatCopy, ...]
    idempotency_key: str
    request_sha256: str


def canonical_chat_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PqChatPackageError("MALFORMED_WIRE") from error


def chat_session_binding(session_id: str) -> str:
    return sha256(("hushline:pq-chat-session:" + session_id).encode()).hexdigest()


def invalidate_pq_account_after_password_reset(user: User, *, when: datetime) -> None:
    """Invalidate public device state when the old account root is unavailable."""

    account = db.session.scalars(
        db.select(ChatAccount).where(ChatAccount.user_id == user.id).with_for_update()
    ).one_or_none()
    if account is None:
        return
    account.identity_version += 1
    account.membership_sequence += 1
    account.identity_public_key = None
    device_ids = db.select(ChatDevice.id).where(ChatDevice.account_id == account.id)
    db.session.execute(
        db.update(ChatDevice)
        .where(ChatDevice.account_id == account.id, ChatDevice.revoked_at.is_(None))
        .values(revoked_at=when)
    )
    db.session.execute(
        db.update(ChatSignedPrekey)
        .where(
            ChatSignedPrekey.device_id.in_(device_ids),
            ChatSignedPrekey.retired_at.is_(None),
        )
        .values(retired_at=when)
    )
    db.session.execute(
        db.update(ChatOneTimePrekey)
        .where(
            ChatOneTimePrekey.device_id.in_(device_ids),
            ChatOneTimePrekey.consumed_at.is_(None),
        )
        .values(expires_at=when)
    )
    db.session.execute(
        db.update(ChatArchiveEpoch)
        .where(ChatArchiveEpoch.account_id == account.id, ChatArchiveEpoch.retired_at.is_(None))
        .values(retired_at=when)
    )


def _pq_chat_base64url(value: Any) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise PqChatPackageError("MALFORMED_WIRE")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise PqChatPackageError("MALFORMED_WIRE") from error
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise PqChatPackageError("MALFORMED_WIRE")
    return decoded


def _pq_chat_uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise PqChatPackageError("MALFORMED_WIRE")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise PqChatPackageError("MALFORMED_WIRE") from error
    if str(parsed) != value:
        raise PqChatPackageError("MALFORMED_WIRE")
    return value


def _pq_chat_uint(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**53 - 1:
        raise PqChatPackageError("MALFORMED_WIRE")
    return value


def _validate_pq_chat_context(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict) or set(context) != _PQ_CHAT_CONTEXT_FIELDS:
        raise PqChatPackageError("MALFORMED_WIRE")
    for field in (
        "account_recipient_id",
        "conversation_id",
        "device_recipient_id",
        "message_id",
        "sender_account_id",
        "sender_device_id",
    ):
        _pq_chat_uuid(context[field])
    for field in (
        "archive_epoch",
        "key_version",
        "recipient_membership_sequence",
        "sender_membership_sequence",
    ):
        _pq_chat_uint(context[field])
    if (
        context["protocol"] != PQ_CHAT_PROTOCOL
        or context["capability_offer"] != [PQ_CHAT_PROTOCOL]
        or context["capability_selection"] != PQ_CHAT_PROTOCOL
    ):
        raise PqChatPackageError("SUITE_MISMATCH")
    purpose = context["purpose"]
    if purpose == "archive":
        if (
            context["suite"] != PQ_CHAT_ARCHIVE_SUITE
            or context["device_recipient_id"] != PQ_CHAT_ZERO_DEVICE_ID
            or context["archive_epoch"] == 0
        ):
            raise PqChatPackageError("SUITE_MISMATCH")
    elif purpose == "transport":
        if (
            context["suite"] != PQ_CHAT_TRANSPORT_SUITE
            or context["device_recipient_id"] == PQ_CHAT_ZERO_DEVICE_ID
            or context["archive_epoch"] != 0
        ):
            raise PqChatPackageError("SUITE_MISMATCH")
    else:
        raise PqChatPackageError("SUITE_MISMATCH")
    return context


def _validate_pq_chat_created_at(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z") or "." in value:
        raise PqChatPackageError("MALFORMED_WIRE")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise PqChatPackageError("MALFORMED_WIRE") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PqChatPackageError("MALFORMED_WIRE")


def validate_pq_chat_package(
    payload: Any, *, sender_signing_public_key: str
) -> ValidatedPqChatPackage:
    if not isinstance(payload, dict) or set(payload) != {"manifest", "signature", "copies"}:
        raise PqChatPackageError("MALFORMED_WIRE")
    request_bytes = canonical_chat_json(payload)
    if len(request_bytes) > PQ_CHAT_REQUEST_MAX_BYTES:
        raise PqChatPackageError("MALFORMED_WIRE")

    manifest = payload["manifest"]
    request_copies = payload["copies"]
    if not isinstance(manifest, dict) or set(manifest) != _PQ_CHAT_MANIFEST_FIELDS:
        raise PqChatPackageError("MALFORMED_WIRE")
    if (
        not isinstance(request_copies, list)
        or not PQ_CHAT_MIN_COPIES <= len(request_copies) <= PQ_CHAT_MAX_COPIES
    ):
        raise PqChatPackageError("STATE_CONFLICT")
    manifest_copies = manifest["copies"]
    if not isinstance(manifest_copies, list) or len(manifest_copies) != len(request_copies):
        raise PqChatPackageError("STATE_CONFLICT")
    if (
        manifest["protocol"] != PQ_CHAT_PROTOCOL
        or manifest["capability_offer"] != [PQ_CHAT_PROTOCOL]
        or manifest["capability_selection"] != PQ_CHAT_PROTOCOL
    ):
        raise PqChatPackageError("SUITE_MISMATCH")
    for field in ("conversation_id", "message_id", "sender_account_id", "sender_device_id"):
        _pq_chat_uuid(manifest[field])
    if not isinstance(manifest["sender_membership_sha256"], str) or not _PQ_CHAT_HEX_256.fullmatch(
        manifest["sender_membership_sha256"]
    ):
        raise PqChatPackageError("MALFORMED_WIRE")
    _validate_pq_chat_created_at(manifest["created_at"])

    manifest_bytes = canonical_chat_json(manifest)
    if len(manifest_bytes) > PQ_CHAT_MANIFEST_MAX_BYTES:
        raise PqChatPackageError("MALFORMED_WIRE")
    signature = payload["signature"]
    signature_bytes = _pq_chat_base64url(signature)
    if len(signature_bytes) != _ED25519_SIGNATURE_BYTES:
        raise PqChatPackageError("MALFORMED_WIRE")
    public_key_bytes = _pq_chat_base64url(sender_signing_public_key)
    if len(public_key_bytes) != _ED25519_PUBLIC_KEY_BYTES:
        raise PqChatPackageError("MALFORMED_WIRE")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            PQ_CHAT_SIGNATURE_DOMAIN + b"\x00" + manifest_bytes,
        )
    except (InvalidSignature, ValueError) as error:
        raise PqChatPackageError("AUTHENTICATION_FAILED") from error

    validated_copies: list[ValidatedPqChatCopy] = []
    copy_order: list[tuple[str, str, str]] = []
    for manifest_copy, request_copy in zip(manifest_copies, request_copies, strict=True):
        if (
            not isinstance(manifest_copy, dict)
            or set(manifest_copy) != _PQ_CHAT_MANIFEST_COPY_FIELDS
        ):
            raise PqChatPackageError("MALFORMED_WIRE")
        if not isinstance(request_copy, dict) or set(request_copy) != {"context", "ciphertext"}:
            raise PqChatPackageError("MALFORMED_WIRE")
        context = _validate_pq_chat_context(request_copy["context"])
        ciphertext = request_copy["ciphertext"]
        ciphertext_bytes = _pq_chat_base64url(ciphertext)
        if not ciphertext_bytes or len(ciphertext_bytes) > PQ_CHAT_CIPHERTEXT_MAX_BYTES:
            raise PqChatPackageError("MALFORMED_WIRE")
        if context["purpose"] == "archive" and len(ciphertext_bytes) < PQ_CHAT_ARCHIVE_MIN_BYTES:
            raise PqChatPackageError("MALFORMED_WIRE")
        context_hash = sha256(canonical_chat_json(context)).hexdigest()
        ciphertext_hash = sha256(ciphertext_bytes).hexdigest()
        expected = {
            "account_recipient_id": context["account_recipient_id"],
            "archive_epoch": context["archive_epoch"],
            "ciphertext_length": len(ciphertext_bytes),
            "ciphertext_sha256": ciphertext_hash,
            "context_sha256": context_hash,
            "device_recipient_id": context["device_recipient_id"],
            "key_version": context["key_version"],
            "purpose": context["purpose"],
        }
        if not hmac.compare_digest(
            canonical_chat_json(manifest_copy), canonical_chat_json(expected)
        ):
            raise PqChatPackageError("AUTHENTICATION_FAILED")
        if any(
            context[field] != manifest[field]
            for field in (
                "capability_offer",
                "capability_selection",
                "conversation_id",
                "message_id",
                "protocol",
                "sender_account_id",
                "sender_device_id",
            )
        ):
            raise PqChatPackageError("AUTHENTICATION_FAILED")
        copy_order.append(
            (context["purpose"], context["account_recipient_id"], context["device_recipient_id"])
        )
        validated_copies.append(
            ValidatedPqChatCopy(
                context=context,
                ciphertext=ciphertext,
                ciphertext_bytes=ciphertext_bytes,
                context_sha256=context_hash,
                ciphertext_sha256=ciphertext_hash,
            )
        )
    if copy_order != sorted(copy_order) or len(set(copy_order)) != len(copy_order):
        raise PqChatPackageError("STATE_CONFLICT")

    return ValidatedPqChatPackage(
        manifest=manifest,
        signature=signature,
        signature_bytes=signature_bytes,
        copies=tuple(validated_copies),
        idempotency_key=sha256(manifest_bytes + signature_bytes).hexdigest(),
        request_sha256=sha256(request_bytes).hexdigest(),
    )


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
    if not public_signing_key:
        return {}, "public_signing_key is required."
    if not _valid_public_jwk(public_signing_key, expected_use="signing"):
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

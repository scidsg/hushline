import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from flask import Flask, current_app, jsonify, request, session
from flask_wtf.csrf import validate_csrf
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import CHAT_KEY_SESSION_ID_SESSION_KEY, authentication_required
from hushline.chat_key_lifecycle import (
    PQ_CHAT_ARCHIVE_SUITE,
    PQ_CHAT_PROTOCOL,
    canonical_chat_json,
    chat_session_binding,
)
from hushline.db import db
from hushline.model import (
    ChatAccount,
    ChatArchiveEpoch,
    ChatDevice,
    ChatOneTimePrekey,
    ChatPqRateLimitAttempt,
    ChatPrekeyClaim,
    ChatSignedPrekey,
    ConversationMessageTransportCopy,
    User,
)

MEMBERSHIP_SIGNATURE_DOMAIN = b"HushLine/HL-PQCHAT-1/device-membership/v1"
UNLOCK_SIGNATURE_DOMAIN = b"HushLine/HL-PQCHAT-1/unlock-enrollment/v1"
PREKEY_SIGNATURE_DOMAIN = b"HushLine/HL-PQCHAT-1/prekey-publication/v1"
REVOCATION_SIGNATURE_DOMAIN = b"HushLine/HL-PQCHAT-1/device-revocation/v1"
DEVICE_MEMBERSHIP_LIFETIME = timedelta(days=30)
SIGNED_PREKEY_LIFETIME = timedelta(days=7)
SIGNED_PREKEY_OVERLAP = timedelta(hours=48)
ONE_TIME_PREKEY_LIFETIME = timedelta(days=30)
PREKEY_RESERVATION_LIFETIME = timedelta(minutes=5)
PREKEY_TOMBSTONE_LIFETIME = timedelta(days=7)
PREKEY_TARGET = 100
PREKEY_LOW_WATERMARK = 20
MAX_ACTIVE_DEVICES = 5
MAX_STALE_DEVICES = 20
MAX_TOMBSTONES_PER_DEVICE = 10_080
_CLOCK_SKEW = timedelta(minutes=5)
_ED25519_PUBLIC_BYTES = 32
_ED25519_SIGNATURE_BYTES = 64
_LIBSIGNAL_PUBLIC_BYTES = 33
_LIBSIGNAL_PUBLIC_TYPE = 0x05
_KYBER1024_PUBLIC_BYTES = 1569
_KYBER1024_PUBLIC_TYPE = 0x08
_ARCHIVE_PUBLIC_BYTES = 1216
_ENCRYPTED_ARCHIVE_MAX_LENGTH = 200_000
_P256_SIGNATURE_BYTES = 64
_HEX_SHA256_LENGTH = 64
_LIBSIGNAL_MAX_REGISTRATION_ID = 16_380
_MEMBERSHIP_FIELDS = {
    "account_id",
    "archive_epoch",
    "archive_public_key_sha256",
    "archive_suites",
    "capabilities",
    "device_id",
    "device_signing_public_key",
    "expires_at",
    "identity_version",
    "issued_at",
    "membership_sequence",
    "one_time_prekey_end",
    "one_time_prekey_start",
    "protocol_identity_public_key",
    "protocol_registration_id",
    "signed_prekey_id",
    "status",
}
_SIGNED_PREKEY_FIELDS = {
    "classical_public_key",
    "classical_signature",
    "device_signature",
    "expires_at",
    "key_id",
    "pq_public_key",
    "pq_signature",
}
_ONE_TIME_PREKEY_FIELDS = {
    "classical_public_key",
    "device_signature",
    "expires_at",
    "key_id",
    "pq_public_key",
    "pq_signature",
}
_PUBLICATION_FIELDS = {
    "device_id",
    "membership_sequence",
    "one_time_prekeys",
    "protocol",
    "signed_prekey",
}
_RATE_LIMITS = {
    "device_create": ("PQ_DEVICE_CREATION_RATE_LIMIT_MAX", 5),
    "prekey_publish": ("PQ_PREKEY_PUBLICATION_RATE_LIMIT_MAX", 12),
    "prekey_claim": ("PQ_PREKEY_CLAIM_RATE_LIMIT_MAX", 60),
}


class PqDeviceError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _json_error(error: PqDeviceError) -> tuple[Response, int]:
    return jsonify({"error": error.code}), error.status


def _validate_json_csrf() -> None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return
    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError as error:
        raise PqDeviceError("AUTHENTICATION_FAILED", 400) from error


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise PqDeviceError("MALFORMED_WIRE")
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError) as error:
        raise PqDeviceError("MALFORMED_WIRE") from error
    if str(parsed) != value:
        raise PqDeviceError("MALFORMED_WIRE")
    return value


def _uint(value: Any, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > 2**53 - 1
    ):
        raise PqDeviceError("MALFORMED_WIRE")
    return value


def _b64url(value: Any, *, length: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise PqDeviceError("MALFORMED_WIRE")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise PqDeviceError("MALFORMED_WIRE") from error
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        raise PqDeviceError("MALFORMED_WIRE")
    if length is not None and len(decoded) != length:
        raise PqDeviceError("MALFORMED_WIRE")
    return decoded


def _typed_public_key(value: Any, *, length: int, key_type: int) -> bytes:
    decoded = _b64url(value, length=length)
    if decoded[0] != key_type:
        raise PqDeviceError("SUITE_MISMATCH")
    return decoded


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z") or "." in value:
        raise PqDeviceError("MALFORMED_WIRE")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise PqDeviceError("MALFORMED_WIRE") from error
    if parsed.utcoffset() != timedelta(0) or parsed.isoformat().replace("+00:00", "Z") != value:
        raise PqDeviceError("MALFORMED_WIRE")
    return parsed


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _verify_ed25519(public_key: str, signature: Any, domain: bytes, value: Any) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(
            _b64url(public_key, length=_ED25519_PUBLIC_BYTES)
        ).verify(
            _b64url(signature, length=_ED25519_SIGNATURE_BYTES),
            domain + b"\x00" + canonical_chat_json(value),
        )
    except (InvalidSignature, ValueError) as error:
        raise PqDeviceError("AUTHENTICATION_FAILED", 403) from error


def _verify_unlock_signature(user: User, signature: Any, value: Any) -> None:
    chat_key = user.active_chat_key
    if chat_key is None or not chat_key.public_signing_key:
        raise PqDeviceError("CAPABILITY_UNAVAILABLE", 409)
    try:
        jwk = json.loads(chat_key.public_signing_key)
        x_value = _b64url(jwk["x"], length=32)
        y_value = _b64url(jwk["y"], length=32)
        verification_key = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x_value, "big"),
            int.from_bytes(y_value, "big"),
            ec.SECP256R1(),
        ).public_key()
        raw_signature = _b64url(signature, length=_P256_SIGNATURE_BYTES)
        der_signature = encode_dss_signature(
            int.from_bytes(raw_signature[:32], "big"),
            int.from_bytes(raw_signature[32:], "big"),
        )
        verification_key.verify(
            der_signature,
            UNLOCK_SIGNATURE_DOMAIN + b"\x00" + canonical_chat_json(value),
            ec.ECDSA(hashes.SHA256()),
        )
    except (InvalidSignature, KeyError, TypeError, ValueError, PqDeviceError) as error:
        raise PqDeviceError("AUTHENTICATION_FAILED", 403) from error


def _authenticated_user() -> User:
    return db.session.scalars(db.select(User).where(User.id == session["user_id"])).one()


def _session_binding() -> str:
    session_id = session.get(CHAT_KEY_SESSION_ID_SESSION_KEY)
    if not isinstance(session_id, str) or not session_id:
        raise PqDeviceError("AUTHENTICATION_FAILED", 403)
    return chat_session_binding(session_id)


def _current_device(user: User, device_public_id: Any, *, lock: bool = False) -> ChatDevice:
    device_id = _uuid(device_public_id)
    statement = (
        db.select(ChatDevice)
        .join(ChatAccount)
        .where(
            ChatAccount.user_id == user.id,
            ChatDevice.public_id == device_id,
            ChatDevice.session_id_hash == _session_binding(),
            ChatDevice.revoked_at.is_(None),
            ChatDevice.expires_at > datetime.now(UTC),
        )
    )
    if lock:
        statement = statement.with_for_update()
    device = db.session.scalars(statement).one_or_none()
    if device is None:
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    return device


def _rate_limit_value(config_name: str, default: int) -> int:
    try:
        return max(0, int(current_app.config.get(config_name, default)))
    except (TypeError, ValueError):
        return default


def _consume_rate_limit(user: User, action: str) -> None:
    config_name, default = _RATE_LIMITS[action]
    limit = _rate_limit_value(config_name, default)
    if limit == 0:
        return
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=1)
    bind = db.session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        lock_payload = f"hushline:pq-device-rate-limit:{user.id}:{action}".encode()
        lock_key = int.from_bytes(
            hashlib.blake2b(lock_payload, digest_size=8).digest(), "big", signed=True
        )
        db.session.execute(db.select(db.func.pg_advisory_xact_lock(lock_key)))
    db.session.execute(
        db.delete(ChatPqRateLimitAttempt).where(ChatPqRateLimitAttempt.created_at < window_start)
    )
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ChatPqRateLimitAttempt)
        .where(
            ChatPqRateLimitAttempt.user_id == user.id,
            ChatPqRateLimitAttempt.action == action,
            ChatPqRateLimitAttempt.created_at >= window_start,
        )
    )
    if count is not None and count >= limit:
        raise PqDeviceError("RATE_LIMITED", 429)
    db.session.add(ChatPqRateLimitAttempt(user_id=user.id, action=action, created_at=now))


def _cleanup_prekeys(now: datetime) -> None:
    db.session.execute(
        db.delete(ChatPrekeyClaim).where(ChatPrekeyClaim.tombstone_expires_at <= now)
    )
    db.session.execute(
        db.delete(ChatOneTimePrekey).where(
            or_(
                ChatOneTimePrekey.tombstone_expires_at <= now,
                (
                    (ChatOneTimePrekey.consumed_at.is_(None))
                    & (ChatOneTimePrekey.expires_at <= now)
                    & ~db.exists().where(
                        ChatPrekeyClaim.prekey_id == ChatOneTimePrekey.id,
                        ChatPrekeyClaim.tombstone_expires_at > now,
                    )
                ),
            )
        )
    )
    db.session.execute(
        db.delete(ChatSignedPrekey).where(
            or_(
                ChatSignedPrekey.expires_at <= now - SIGNED_PREKEY_OVERLAP,
                ChatSignedPrekey.retired_at <= now - SIGNED_PREKEY_OVERLAP,
            )
        )
    )


def _prune_unreferenced_stale_devices(account: ChatAccount, now: datetime) -> None:
    stale = list(
        db.session.scalars(
            db.select(ChatDevice)
            .where(
                ChatDevice.account_id == account.id,
                or_(
                    ChatDevice.revoked_at.is_not(None),
                    ChatDevice.expires_at <= now,
                ),
                ~db.exists().where(ChatOneTimePrekey.device_id == ChatDevice.id),
                ~db.exists().where(ChatSignedPrekey.device_id == ChatDevice.id),
                ~db.exists().where(
                    ConversationMessageTransportCopy.recipient_device_id == ChatDevice.id
                ),
            )
            .order_by(ChatDevice.created_at.desc())
            .offset(MAX_STALE_DEVICES)
        )
    )
    for device in stale:
        db.session.delete(device)


def _membership_response(device: ChatDevice) -> dict[str, Any]:
    return {
        "membership": device.membership,
        "membership_sha256": device.membership_sha256,
        "membership_signature": device.membership_signature,
    }


def _archive_epoch_response(epoch: ChatArchiveEpoch) -> dict[str, Any]:
    return {
        "encrypted_private_key": epoch.encrypted_private_key,
        "epoch": epoch.epoch,
        "public_key": epoch.public_key,
        "retired_at": (
            _as_utc(epoch.retired_at).isoformat().replace("+00:00", "Z")
            if epoch.retired_at is not None
            else None
        ),
        "suite": PQ_CHAT_ARCHIVE_SUITE,
    }


def _prekey_response(claim: ChatPrekeyClaim, signed_prekey: ChatSignedPrekey) -> dict[str, Any]:
    prekey = claim.prekey
    return {
        "account_identity_public_key": prekey.device.account.identity_public_key,
        "claim_id": claim.claim_id,
        "claim_expires_at": _as_utc(claim.reservation_expires_at)
        .isoformat()
        .replace("+00:00", "Z"),
        "device": _membership_response(prekey.device),
        "one_time_prekey": {
            "classical_public_key": prekey.classical_public_key,
            "device_signature": prekey.publication_signature,
            "expires_at": _as_utc(prekey.expires_at).isoformat().replace("+00:00", "Z"),
            "key_id": prekey.key_id,
            "pq_public_key": prekey.pq_public_key,
            "pq_signature": prekey.pq_signature,
        },
        "signed_prekey": {
            "classical_public_key": signed_prekey.classical_public_key,
            "classical_signature": signed_prekey.classical_signature,
            "device_signature": signed_prekey.publication_signature,
            "expires_at": _as_utc(signed_prekey.expires_at).isoformat().replace("+00:00", "Z"),
            "key_id": signed_prekey.key_id,
            "pq_public_key": signed_prekey.pq_public_key,
            "pq_signature": signed_prekey.pq_signature,
        },
    }


def _validate_membership(
    payload: Any,
    account: ChatAccount,
    *,
    expected_sequence: int,
    now: datetime,
) -> tuple[dict[str, Any], datetime]:
    membership = payload.get("membership") if isinstance(payload, dict) else None
    if not isinstance(membership, dict) or set(membership) != _MEMBERSHIP_FIELDS:
        raise PqDeviceError("MALFORMED_WIRE")
    for field in ("account_id", "device_id"):
        _uuid(membership[field])
    for field in (
        "archive_epoch",
        "identity_version",
        "membership_sequence",
        "one_time_prekey_end",
        "one_time_prekey_start",
        "protocol_registration_id",
        "signed_prekey_id",
    ):
        _uint(membership[field], positive=True)
    issued_at = _timestamp(membership["issued_at"])
    expires_at = _timestamp(membership["expires_at"])
    if (
        membership["account_id"] != account.public_id
        or membership["identity_version"] != max(1, account.identity_version)
        or membership["membership_sequence"] != expected_sequence
        or membership["status"] != "active"
        or membership["capabilities"] != [PQ_CHAT_PROTOCOL]
        or membership["archive_suites"] != [PQ_CHAT_ARCHIVE_SUITE]
        or membership["one_time_prekey_start"] > membership["one_time_prekey_end"]
        or membership["one_time_prekey_end"] - membership["one_time_prekey_start"] + 1
        > PREKEY_TARGET
        or membership["protocol_registration_id"] > _LIBSIGNAL_MAX_REGISTRATION_ID
        or abs(now - issued_at) > _CLOCK_SKEW
        or expires_at <= now
        or expires_at > issued_at + DEVICE_MEMBERSHIP_LIFETIME
    ):
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    _b64url(membership["device_signing_public_key"], length=_ED25519_PUBLIC_BYTES)
    _typed_public_key(
        membership["protocol_identity_public_key"],
        length=_LIBSIGNAL_PUBLIC_BYTES,
        key_type=_LIBSIGNAL_PUBLIC_TYPE,
    )
    archive_digest = membership["archive_public_key_sha256"]
    if (
        not isinstance(archive_digest, str)
        or len(archive_digest) != _HEX_SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in archive_digest)
    ):
        raise PqDeviceError("MALFORMED_WIRE")
    return membership, expires_at


def _validate_archive(
    payload: Any,
    account: ChatAccount,
    membership: dict[str, Any],
    *,
    now: datetime,
) -> None:
    current_epoch = db.session.scalars(
        db.select(ChatArchiveEpoch).where(
            ChatArchiveEpoch.account_id == account.id,
            ChatArchiveEpoch.retired_at.is_(None),
        )
    ).one_or_none()
    archive = payload.get("archive") if isinstance(payload, dict) else None
    if current_epoch is not None and archive is None:
        if (
            membership["archive_epoch"] != current_epoch.epoch
            or hashlib.sha256(_b64url(current_epoch.public_key)).hexdigest()
            != membership["archive_public_key_sha256"]
        ):
            raise PqDeviceError("STALE_MEMBERSHIP", 409)
        return
    if not isinstance(archive, dict) or set(archive) != {
        "encrypted_private_key",
        "epoch",
        "public_key",
    }:
        raise PqDeviceError("CAPABILITY_UNAVAILABLE", 409)
    latest_epoch = db.session.scalar(
        db.select(db.func.max(ChatArchiveEpoch.epoch)).where(
            ChatArchiveEpoch.account_id == account.id
        )
    )
    if current_epoch is not None and (
        archive["epoch"] == current_epoch.epoch
        and archive["public_key"] == current_epoch.public_key
        and archive["encrypted_private_key"] == current_epoch.encrypted_private_key
    ):
        if (
            membership["archive_epoch"] != current_epoch.epoch
            or hashlib.sha256(_b64url(current_epoch.public_key)).hexdigest()
            != membership["archive_public_key_sha256"]
        ):
            raise PqDeviceError("STALE_MEMBERSHIP", 409)
        return
    expected_epoch = (latest_epoch or 0) + 1
    if archive["epoch"] != expected_epoch or membership["archive_epoch"] != expected_epoch:
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    public_key = _b64url(archive["public_key"], length=_ARCHIVE_PUBLIC_BYTES)
    if hashlib.sha256(public_key).hexdigest() != membership["archive_public_key_sha256"]:
        raise PqDeviceError("AUTHENTICATION_FAILED", 403)
    encrypted_private_key = archive["encrypted_private_key"]
    if (
        not isinstance(encrypted_private_key, str)
        or not encrypted_private_key
        or len(encrypted_private_key) > _ENCRYPTED_ARCHIVE_MAX_LENGTH
    ):
        raise PqDeviceError("MALFORMED_WIRE")
    _b64url(encrypted_private_key)
    if current_epoch is not None:
        current_epoch.retired_at = now
        prior_device_ids = list(
            db.session.scalars(
                db.select(ChatDevice.id).where(
                    ChatDevice.account_id == account.id,
                    ChatDevice.revoked_at.is_(None),
                )
            )
        )
        db.session.execute(
            db.update(ChatDevice).where(ChatDevice.id.in_(prior_device_ids)).values(revoked_at=now)
        )
        db.session.execute(
            db.update(ChatSignedPrekey)
            .where(
                ChatSignedPrekey.device_id.in_(prior_device_ids),
                ChatSignedPrekey.retired_at.is_(None),
            )
            .values(retired_at=now)
        )
        db.session.execute(
            db.update(ChatOneTimePrekey)
            .where(
                ChatOneTimePrekey.device_id.in_(prior_device_ids),
                ChatOneTimePrekey.consumed_at.is_(None),
            )
            .values(expires_at=now)
        )
        db.session.flush()
    account.archive_epochs.append(
        ChatArchiveEpoch(
            epoch=expected_epoch,
            public_key=archive["public_key"],
            encrypted_private_key=encrypted_private_key,
        )
    )


def _prekey_proof_value(*, device: ChatDevice, kind: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": device.public_id,
        "key": {key: nested for key, nested in value.items() if key != "device_signature"},
        "kind": kind,
        "membership_sequence": device.membership_sequence,
        "protocol": PQ_CHAT_PROTOCOL,
    }


def _validate_signed_prekey(
    value: Any, device: ChatDevice, now: datetime
) -> tuple[dict[str, Any], datetime]:
    if not isinstance(value, dict) or set(value) != _SIGNED_PREKEY_FIELDS:
        raise PqDeviceError("MALFORMED_WIRE")
    _uint(value["key_id"], positive=True)
    _typed_public_key(
        value["classical_public_key"],
        length=_LIBSIGNAL_PUBLIC_BYTES,
        key_type=_LIBSIGNAL_PUBLIC_TYPE,
    )
    _b64url(value["classical_signature"], length=_ED25519_SIGNATURE_BYTES)
    _typed_public_key(
        value["pq_public_key"],
        length=_KYBER1024_PUBLIC_BYTES,
        key_type=_KYBER1024_PUBLIC_TYPE,
    )
    _b64url(value["pq_signature"], length=_ED25519_SIGNATURE_BYTES)
    _verify_ed25519(
        device.signing_public_key,
        value["device_signature"],
        PREKEY_SIGNATURE_DOMAIN,
        _prekey_proof_value(device=device, kind="signed", value=value),
    )
    expires_at = _timestamp(value["expires_at"])
    if expires_at <= now or expires_at > now + SIGNED_PREKEY_LIFETIME + _CLOCK_SKEW:
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    return value, expires_at


def _validate_one_time_prekey(
    value: Any, device: ChatDevice, now: datetime
) -> tuple[dict[str, Any], datetime]:
    if not isinstance(value, dict) or set(value) != _ONE_TIME_PREKEY_FIELDS:
        raise PqDeviceError("MALFORMED_WIRE")
    key_id = _uint(value["key_id"], positive=True)
    if (
        not device.membership["one_time_prekey_start"]
        <= key_id
        <= device.membership["one_time_prekey_end"]
    ):
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    _typed_public_key(
        value["classical_public_key"],
        length=_LIBSIGNAL_PUBLIC_BYTES,
        key_type=_LIBSIGNAL_PUBLIC_TYPE,
    )
    _typed_public_key(
        value["pq_public_key"],
        length=_KYBER1024_PUBLIC_BYTES,
        key_type=_KYBER1024_PUBLIC_TYPE,
    )
    _b64url(value["pq_signature"], length=_ED25519_SIGNATURE_BYTES)
    _verify_ed25519(
        device.signing_public_key,
        value["device_signature"],
        PREKEY_SIGNATURE_DOMAIN,
        _prekey_proof_value(device=device, kind="one-time", value=value),
    )
    expires_at = _timestamp(value["expires_at"])
    if expires_at <= now or expires_at > now + ONE_TIME_PREKEY_LIFETIME + _CLOCK_SKEW:
        raise PqDeviceError("STALE_MEMBERSHIP", 409)
    return value, expires_at


def register_pq_device_routes(app: Flask) -> None:
    @app.after_request
    def pq_device_no_store(response: Response) -> Response:
        if request.path.startswith("/api/pq/"):
            response.cache_control.no_store = True
            response.cache_control.private = True
        return response

    @app.route("/api/pq/account", methods=["POST"])
    @authentication_required
    def pq_account_bootstrap() -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            account = db.session.scalars(
                db.select(ChatAccount).where(ChatAccount.user_id == user.id).with_for_update()
            ).one_or_none()
            if account is None:
                account = ChatAccount(user=user)
                db.session.add(account)
                db.session.flush()
            db.session.commit()
            return (
                jsonify(
                    {
                        "account_id": account.public_id,
                        "archive_epochs": [
                            _archive_epoch_response(epoch)
                            for epoch in sorted(
                                account.archive_epochs, key=lambda value: value.epoch
                            )
                        ],
                        "identity_public_key": account.identity_public_key,
                        "identity_version": account.identity_version,
                        "membership_sequence": account.membership_sequence,
                        "protocol": PQ_CHAT_PROTOCOL,
                    }
                ),
                200,
            )
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)
        except IntegrityError:
            db.session.rollback()
            return _json_error(PqDeviceError("STATE_CONFLICT", 409))

    @app.route("/api/pq/devices", methods=["POST"])
    @authentication_required
    def pq_enroll_device() -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) != {
                "account_identity_public_key",
                "archive",
                "membership",
                "membership_signature",
                "unlock_signature",
            }:
                raise PqDeviceError("MALFORMED_WIRE")
            account = db.session.scalars(
                db.select(ChatAccount).where(ChatAccount.user_id == user.id).with_for_update()
            ).one_or_none()
            if account is None:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            now = datetime.now(UTC)
            raw_membership = payload.get("membership")
            is_retry = (
                isinstance(raw_membership, dict)
                and raw_membership.get("membership_sequence") == account.membership_sequence
                and account.membership_sequence > 0
            )
            membership, expires_at = _validate_membership(
                payload,
                account,
                expected_sequence=(
                    account.membership_sequence if is_retry else account.membership_sequence + 1
                ),
                now=now,
            )
            identity_public_key = payload["account_identity_public_key"]
            _b64url(identity_public_key, length=_ED25519_PUBLIC_BYTES)
            if account.identity_public_key is not None and not hmac.compare_digest(
                account.identity_public_key, identity_public_key
            ):
                raise PqDeviceError("AUTHENTICATION_FAILED", 403)
            _verify_ed25519(
                identity_public_key,
                payload["membership_signature"],
                MEMBERSHIP_SIGNATURE_DOMAIN,
                membership,
            )
            _verify_unlock_signature(
                user,
                payload["unlock_signature"],
                {
                    "account_identity_public_key": identity_public_key,
                    "membership": membership,
                },
            )
            membership_sha256 = hashlib.sha256(canonical_chat_json(membership)).hexdigest()
            if is_retry:
                device = db.session.scalars(
                    db.select(ChatDevice).where(
                        ChatDevice.account_id == account.id,
                        ChatDevice.public_id == membership["device_id"],
                        ChatDevice.session_id_hash == _session_binding(),
                        ChatDevice.membership_sha256 == membership_sha256,
                        ChatDevice.membership_signature == payload["membership_signature"],
                        ChatDevice.revoked_at.is_(None),
                    )
                ).one_or_none()
                if device is None:
                    raise PqDeviceError("STATE_CONFLICT", 409)
                db.session.commit()
                return jsonify({"device": _membership_response(device)}), 200
            _validate_archive(payload, account, membership, now=now)
            _consume_rate_limit(user, "device_create")
            _cleanup_prekeys(now)
            _prune_unreferenced_stale_devices(account, now)
            device = db.session.scalars(
                db.select(ChatDevice).where(
                    ChatDevice.account_id == account.id,
                    ChatDevice.public_id == membership["device_id"],
                )
            ).one_or_none()
            reused_identity = db.session.scalar(
                db.select(
                    db.exists().where(
                        ChatDevice.account_id == account.id,
                        ChatDevice.public_id != membership["device_id"],
                        or_(
                            ChatDevice.signing_public_key
                            == membership["device_signing_public_key"],
                            ChatDevice.protocol_identity_public_key
                            == membership["protocol_identity_public_key"],
                        ),
                    )
                )
            )
            if reused_identity:
                raise PqDeviceError("STATE_CONFLICT", 409)
            total_count = db.session.scalar(
                db.select(db.func.count())
                .select_from(ChatDevice)
                .where(ChatDevice.account_id == account.id)
            )
            active_count = db.session.scalar(
                db.select(db.func.count())
                .select_from(ChatDevice)
                .where(
                    ChatDevice.account_id == account.id,
                    ChatDevice.revoked_at.is_(None),
                    ChatDevice.expires_at > now,
                )
            )
            if device is None and active_count is not None and active_count >= MAX_ACTIVE_DEVICES:
                raise PqDeviceError("DEVICE_LIMIT_REACHED", 409)
            if (
                device is None
                and total_count is not None
                and total_count >= MAX_ACTIVE_DEVICES + MAX_STALE_DEVICES
            ):
                raise PqDeviceError("DEVICE_LIMIT_REACHED", 409)
            if device is None:
                device = ChatDevice(account=account, public_id=membership["device_id"])
            elif device.revoked_at is not None:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            elif (
                membership["signed_prekey_id"] <= device.key_version
                or membership["one_time_prekey_start"] <= device.membership["one_time_prekey_end"]
            ):
                raise PqDeviceError("PREKEY_REPLAY", 409)
            else:
                db.session.execute(
                    db.update(ChatSignedPrekey)
                    .where(
                        ChatSignedPrekey.device_id == device.id,
                        ChatSignedPrekey.retired_at.is_(None),
                    )
                    .values(retired_at=now)
                )
                db.session.execute(
                    db.update(ChatOneTimePrekey)
                    .where(
                        ChatOneTimePrekey.device_id == device.id,
                        ChatOneTimePrekey.consumed_at.is_(None),
                    )
                    .values(expires_at=now)
                )
            device.session_id_hash = _session_binding()
            device.membership_sequence = membership["membership_sequence"]
            device.key_version = membership["signed_prekey_id"]
            device.membership_sha256 = membership_sha256
            device.signing_public_key = membership["device_signing_public_key"]
            device.protocol_identity_public_key = membership["protocol_identity_public_key"]
            device.membership = membership
            device.membership_signature = payload["membership_signature"]
            device.expires_at = expires_at
            account.identity_public_key = identity_public_key
            account.identity_version = membership["identity_version"]
            account.membership_sequence = membership["membership_sequence"]
            db.session.add(device)
            db.session.commit()
            return jsonify({"device": _membership_response(device)}), 201
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)
        except IntegrityError:
            db.session.rollback()
            return _json_error(PqDeviceError("STATE_CONFLICT", 409))

    @app.route("/api/pq/devices/<device_id>/prekeys", methods=["POST"])
    @authentication_required
    def pq_publish_prekeys(device_id: str) -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            device = _current_device(user, device_id, lock=True)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) != {"publication", "signature"}:
                raise PqDeviceError("MALFORMED_WIRE")
            publication = payload["publication"]
            if not isinstance(publication, dict) or set(publication) != _PUBLICATION_FIELDS:
                raise PqDeviceError("MALFORMED_WIRE")
            if (
                publication["protocol"] != PQ_CHAT_PROTOCOL
                or publication["device_id"] != device.public_id
                or publication["membership_sequence"] != device.membership_sequence
            ):
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            prekeys = publication["one_time_prekeys"]
            if not isinstance(prekeys, list) or not 1 <= len(prekeys) <= PREKEY_TARGET:
                raise PqDeviceError("MALFORMED_WIRE")
            _verify_ed25519(
                device.signing_public_key,
                payload["signature"],
                PREKEY_SIGNATURE_DOMAIN,
                publication,
            )
            now = datetime.now(UTC)
            _cleanup_prekeys(now)
            signed_value, signed_expires_at = _validate_signed_prekey(
                publication["signed_prekey"], device, now
            )
            if signed_value["key_id"] != device.membership["signed_prekey_id"]:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            validated = [_validate_one_time_prekey(value, device, now) for value in prekeys]
            key_ids = [value[0]["key_id"] for value in validated]
            if len(set(key_ids)) != len(key_ids):
                raise PqDeviceError("MALFORMED_WIRE")
            existing = {
                prekey.key_id: prekey
                for prekey in db.session.scalars(
                    db.select(ChatOneTimePrekey).where(
                        ChatOneTimePrekey.device_id == device.id,
                        ChatOneTimePrekey.key_id.in_(key_ids),
                    )
                )
            }
            usable_count = db.session.scalar(
                db.select(db.func.count())
                .select_from(ChatOneTimePrekey)
                .where(
                    ChatOneTimePrekey.device_id == device.id,
                    ChatOneTimePrekey.consumed_at.is_(None),
                    ChatOneTimePrekey.expires_at > now,
                )
            )
            new_count = sum(value[0]["key_id"] not in existing for value in validated)
            if usable_count is not None and usable_count + new_count > PREKEY_TARGET:
                raise PqDeviceError("PREKEY_LIMIT_REACHED", 409)
            publication_sha256 = hashlib.sha256(canonical_chat_json(signed_value)).hexdigest()
            signed_prekey = db.session.scalars(
                db.select(ChatSignedPrekey).where(
                    ChatSignedPrekey.device_id == device.id,
                    ChatSignedPrekey.key_id == signed_value["key_id"],
                )
            ).one_or_none()
            if signed_prekey is None:
                db.session.execute(
                    db.update(ChatSignedPrekey)
                    .where(
                        ChatSignedPrekey.device_id == device.id,
                        ChatSignedPrekey.retired_at.is_(None),
                    )
                    .values(retired_at=now)
                )
                signed_prekey = ChatSignedPrekey(
                    device=device,
                    key_id=signed_value["key_id"],
                    membership_sequence=device.membership_sequence,
                    classical_public_key=signed_value["classical_public_key"],
                    classical_signature=signed_value["classical_signature"],
                    pq_public_key=signed_value["pq_public_key"],
                    pq_signature=signed_value["pq_signature"],
                    publication_sha256=publication_sha256,
                    publication_signature=signed_value["device_signature"],
                    expires_at=signed_expires_at,
                )
                db.session.add(signed_prekey)
            elif not hmac.compare_digest(signed_prekey.publication_sha256, publication_sha256):
                raise PqDeviceError("STATE_CONFLICT", 409)
            if signed_prekey.id is None or new_count:
                _consume_rate_limit(user, "prekey_publish")
            created = 0
            for value, expires_at in validated:
                prior = existing.get(value["key_id"])
                if prior is not None:
                    if (
                        prior.classical_public_key != value["classical_public_key"]
                        or prior.pq_public_key != value["pq_public_key"]
                        or prior.pq_signature != value["pq_signature"]
                        or prior.publication_signature != value["device_signature"]
                    ):
                        raise PqDeviceError("STATE_CONFLICT", 409)
                    continue
                device.one_time_prekeys.append(
                    ChatOneTimePrekey(
                        key_id=value["key_id"],
                        membership_sequence=device.membership_sequence,
                        classical_public_key=value["classical_public_key"],
                        pq_public_key=value["pq_public_key"],
                        pq_signature=value["pq_signature"],
                        publication_signature=value["device_signature"],
                        expires_at=expires_at,
                    )
                )
                created += 1
            db.session.commit()
            available = db.session.scalar(
                db.select(db.func.count())
                .select_from(ChatOneTimePrekey)
                .where(
                    ChatOneTimePrekey.device_id == device.id,
                    ChatOneTimePrekey.consumed_at.is_(None),
                    ChatOneTimePrekey.expires_at > now,
                    ~db.exists().where(
                        ChatPrekeyClaim.prekey_id == ChatOneTimePrekey.id,
                        ChatPrekeyClaim.consumed_at.is_(None),
                        ChatPrekeyClaim.reservation_expires_at > now,
                    ),
                )
            )
            return (
                jsonify(
                    {
                        "available": available or 0,
                        "created": created,
                        "replenish_below": PREKEY_LOW_WATERMARK,
                        "target": PREKEY_TARGET,
                    }
                ),
                201,
            )
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)
        except IntegrityError:
            db.session.rollback()
            return _json_error(PqDeviceError("STATE_CONFLICT", 409))

    @app.route(
        "/api/pq/accounts/<account_id>/devices/<device_id>/prekeys/claim",
        methods=["POST"],
    )
    @authentication_required
    def pq_claim_prekey(account_id: str, device_id: str) -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            claimant_id = request.headers.get("X-Hushline-Device-ID")
            claimant = _current_device(user, claimant_id, lock=True)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) != {"claim_id"}:
                raise PqDeviceError("MALFORMED_WIRE")
            claim_id = _uuid(payload["claim_id"])
            target_account_id = _uuid(account_id)
            target_device_id = _uuid(device_id)
            now = datetime.now(UTC)
            _cleanup_prekeys(now)
            existing_claim = db.session.scalars(
                db.select(ChatPrekeyClaim)
                .where(ChatPrekeyClaim.claim_id == claim_id)
                .with_for_update()
            ).one_or_none()
            if existing_claim is not None:
                existing = existing_claim.prekey
                if existing_claim.claimed_by_device_id != claimant.id:
                    raise PqDeviceError("STATE_CONFLICT", 409)
                target = db.session.scalars(
                    db.select(ChatDevice)
                    .join(ChatAccount)
                    .where(
                        ChatDevice.id == existing.device_id,
                        ChatAccount.public_id == target_account_id,
                        ChatDevice.public_id == target_device_id,
                        ChatDevice.revoked_at.is_(None),
                        ChatDevice.expires_at > now,
                    )
                    .with_for_update()
                ).one_or_none()
                if target is None:
                    raise PqDeviceError("STALE_MEMBERSHIP", 409)
                if existing_claim.consumed_at is not None or existing.consumed_at is not None:
                    raise PqDeviceError("PREKEY_REPLAY", 409)
                if (
                    _as_utc(existing_claim.reservation_expires_at) <= now
                    or _as_utc(existing.expires_at) <= now
                    or existing.membership_sequence != target.membership_sequence
                ):
                    raise PqDeviceError("STATE_CONFLICT", 409)
                signed_prekey = db.session.scalars(
                    db.select(ChatSignedPrekey).where(
                        ChatSignedPrekey.device_id == target.id,
                        ChatSignedPrekey.membership_sequence == existing.membership_sequence,
                        ChatSignedPrekey.retired_at.is_(None),
                        ChatSignedPrekey.expires_at > now,
                    )
                ).one_or_none()
                if signed_prekey is None:
                    raise PqDeviceError("STALE_MEMBERSHIP", 409)
                db.session.commit()
                return jsonify(_prekey_response(existing_claim, signed_prekey)), 200
            _consume_rate_limit(user, "prekey_claim")
            target = db.session.scalars(
                db.select(ChatDevice)
                .join(ChatAccount)
                .where(
                    ChatAccount.public_id == target_account_id,
                    ChatDevice.public_id == target_device_id,
                    ChatDevice.revoked_at.is_(None),
                    ChatDevice.expires_at > now,
                )
                .with_for_update()
            ).one_or_none()
            if target is None:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            signed_prekey = db.session.scalars(
                db.select(ChatSignedPrekey).where(
                    ChatSignedPrekey.device_id == target.id,
                    ChatSignedPrekey.membership_sequence == target.membership_sequence,
                    ChatSignedPrekey.retired_at.is_(None),
                    ChatSignedPrekey.expires_at > now,
                )
            ).one_or_none()
            if signed_prekey is None:
                raise PqDeviceError("PREKEY_DEPLETED", 409)
            claim_record_count = db.session.scalar(
                db.select(db.func.count())
                .select_from(ChatPrekeyClaim)
                .join(ChatOneTimePrekey)
                .where(
                    ChatOneTimePrekey.device_id == target.id,
                    ChatPrekeyClaim.tombstone_expires_at > now,
                )
            )
            if claim_record_count is not None and claim_record_count >= MAX_TOMBSTONES_PER_DEVICE:
                raise PqDeviceError("PREKEY_LIMIT_REACHED", 409)
            prekey = db.session.scalars(
                db.select(ChatOneTimePrekey)
                .where(
                    ChatOneTimePrekey.device_id == target.id,
                    ChatOneTimePrekey.membership_sequence == target.membership_sequence,
                    ChatOneTimePrekey.consumed_at.is_(None),
                    ChatOneTimePrekey.expires_at > now,
                    ~db.exists().where(
                        ChatPrekeyClaim.prekey_id == ChatOneTimePrekey.id,
                        ChatPrekeyClaim.consumed_at.is_(None),
                        ChatPrekeyClaim.reservation_expires_at > now,
                    ),
                )
                .order_by(ChatOneTimePrekey.key_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).one_or_none()
            if prekey is None:
                raise PqDeviceError("PREKEY_DEPLETED", 409)
            claim = ChatPrekeyClaim(
                claim_id=claim_id,
                prekey=prekey,
                claimed_by_device=claimant,
                reservation_expires_at=now + PREKEY_RESERVATION_LIFETIME,
                tombstone_expires_at=now + PREKEY_RESERVATION_LIFETIME + PREKEY_TOMBSTONE_LIFETIME,
            )
            db.session.add(claim)
            db.session.commit()
            return jsonify(_prekey_response(claim, signed_prekey)), 201
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)
        except IntegrityError:
            db.session.rollback()
            return _json_error(PqDeviceError("STATE_CONFLICT", 409))

    @app.route("/api/pq/prekey-claims/<claim_id>/consume", methods=["POST"])
    @authentication_required
    def pq_consume_prekey_claim(claim_id: str) -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            claimant = _current_device(user, request.headers.get("X-Hushline-Device-ID"), lock=True)
            claim_public_id = _uuid(claim_id)
            now = datetime.now(UTC)
            claim = db.session.scalars(
                db.select(ChatPrekeyClaim)
                .where(ChatPrekeyClaim.claim_id == claim_public_id)
                .with_for_update()
            ).one_or_none()
            if claim is None or claim.claimed_by_device_id != claimant.id:
                raise PqDeviceError("AUTHENTICATION_FAILED", 403)
            prekey = claim.prekey
            if claim.consumed_at is not None and prekey.consumed_at is not None:
                return jsonify({"claim_id": claim_public_id, "consumed": True}), 200
            target = db.session.scalars(
                db.select(ChatDevice)
                .join(ChatAccount)
                .where(ChatDevice.id == prekey.device_id)
                .with_for_update()
            ).one()
            if (
                _as_utc(claim.reservation_expires_at) <= now
                or prekey.consumed_at is not None
                or _as_utc(prekey.expires_at) <= now
                or target.revoked_at is not None
                or _as_utc(target.expires_at) <= now
                or prekey.membership_sequence != target.membership_sequence
            ):
                raise PqDeviceError("STATE_CONFLICT", 409)
            prekey.consumed_at = now
            prekey.tombstone_expires_at = now + PREKEY_TOMBSTONE_LIFETIME
            claim.consumed_at = now
            claim.tombstone_expires_at = now + PREKEY_TOMBSTONE_LIFETIME
            db.session.commit()
            return jsonify({"claim_id": claim_public_id, "consumed": True}), 200
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)

    @app.route("/api/pq/devices/<device_id>/revoke", methods=["POST"])
    @authentication_required
    def pq_revoke_device(device_id: str) -> tuple[Response, int]:
        try:
            _validate_json_csrf()
            user = _authenticated_user()
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or set(payload) != {"revocation", "signature"}:
                raise PqDeviceError("MALFORMED_WIRE")
            account = db.session.scalars(
                db.select(ChatAccount).where(ChatAccount.user_id == user.id).with_for_update()
            ).one_or_none()
            if account is None or account.identity_public_key is None:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            revocation = payload["revocation"]
            if not isinstance(revocation, dict) or set(revocation) != {
                "account_id",
                "device_id",
                "membership_sequence",
                "revoked_at",
                "status",
            }:
                raise PqDeviceError("MALFORMED_WIRE")
            now = datetime.now(UTC)
            revoked_at = _timestamp(revocation["revoked_at"])
            if (
                revocation["account_id"] != account.public_id
                or revocation["device_id"] != _uuid(device_id)
                or revocation["membership_sequence"] != account.membership_sequence + 1
                or revocation["status"] != "revoked"
                or abs(now - revoked_at) > _CLOCK_SKEW
            ):
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            _verify_ed25519(
                account.identity_public_key,
                payload["signature"],
                REVOCATION_SIGNATURE_DOMAIN,
                revocation,
            )
            device = db.session.scalars(
                db.select(ChatDevice)
                .where(
                    ChatDevice.account_id == account.id,
                    ChatDevice.public_id == revocation["device_id"],
                    ChatDevice.revoked_at.is_(None),
                )
                .with_for_update()
            ).one_or_none()
            if device is None:
                raise PqDeviceError("STALE_MEMBERSHIP", 409)
            device.revoked_at = now
            account.membership_sequence = revocation["membership_sequence"]
            db.session.execute(
                db.update(ChatSignedPrekey)
                .where(
                    ChatSignedPrekey.device_id == device.id,
                    ChatSignedPrekey.retired_at.is_(None),
                )
                .values(retired_at=now)
            )
            db.session.execute(
                db.update(ChatOneTimePrekey)
                .where(
                    ChatOneTimePrekey.device_id == device.id,
                    ChatOneTimePrekey.consumed_at.is_(None),
                )
                .values(expires_at=now)
            )
            db.session.commit()
            return jsonify({"device_id": device.public_id, "revoked": True}), 200
        except PqDeviceError as error:
            db.session.rollback()
            return _json_error(error)

    @app.route("/api/pq/accounts/<account_id>/devices", methods=["GET"])
    @authentication_required
    def pq_account_devices(account_id: str) -> tuple[Response, int]:
        try:
            user = _authenticated_user()
            _current_device(user, request.headers.get("X-Hushline-Device-ID"))
            account = db.session.scalars(
                db.select(ChatAccount).where(ChatAccount.public_id == _uuid(account_id))
            ).one_or_none()
            if account is None or account.identity_public_key is None:
                raise PqDeviceError("CAPABILITY_UNAVAILABLE", 409)
            now = datetime.now(UTC)
            devices = list(
                db.session.scalars(
                    db.select(ChatDevice)
                    .where(
                        ChatDevice.account_id == account.id,
                        ChatDevice.revoked_at.is_(None),
                        ChatDevice.expires_at > now,
                    )
                    .order_by(ChatDevice.public_id)
                )
            )
            if not devices:
                raise PqDeviceError("CAPABILITY_UNAVAILABLE", 409)
            archive_epoch = db.session.scalars(
                db.select(ChatArchiveEpoch).where(
                    ChatArchiveEpoch.account_id == account.id,
                    ChatArchiveEpoch.retired_at.is_(None),
                )
            ).one_or_none()
            if archive_epoch is None:
                raise PqDeviceError("CAPABILITY_UNAVAILABLE", 409)
            return (
                jsonify(
                    {
                        "account_id": account.public_id,
                        "archive": {
                            "epoch": archive_epoch.epoch,
                            "public_key": archive_epoch.public_key,
                            "suite": PQ_CHAT_ARCHIVE_SUITE,
                        },
                        "devices": [_membership_response(device) for device in devices],
                        "identity_public_key": account.identity_public_key,
                        "identity_version": account.identity_version,
                        "membership_sequence": account.membership_sequence,
                        "protocol": PQ_CHAT_PROTOCOL,
                    }
                ),
                200,
            )
        except PqDeviceError as error:
            return _json_error(error)

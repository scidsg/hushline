import base64
import binascii
import hashlib
import hmac
import json
import re
import smtplib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import validate_csrf
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers.response import Response
from wtforms.validators import ValidationError

from hushline.auth import CHAT_KEY_SESSION_ID_SESSION_KEY, authentication_required
from hushline.chat_key_lifecycle import (
    PQ_CHAT_PROTOCOL_VERSION,
    PqChatPackageError,
    ValidatedPqChatPackage,
    chat_key_fingerprint,
    chat_session_binding,
    validate_pq_chat_package,
)
from hushline.crypto import encrypt_message
from hushline.db import db
from hushline.forms import (
    ConversationMessageForm,
    DeleteConversationForm,
    DeleteMessageForm,
    ResendMessageForm,
    UpdateMessageStatusForm,
)
from hushline.model import (
    ChatAccount,
    ChatArchiveEpoch,
    ChatDevice,
    ChatRateLimitAttempt,
    Conversation,
    ConversationMessage,
    ConversationMessageArchiveCopy,
    ConversationMessageCopy,
    ConversationMessageTransportCopy,
    ConversationParticipant,
    FieldValue,
    InitialConversationNonce,
    Message,
    User,
    Username,
)
from hushline.routes.common import (
    do_send_email,
    notification_email_encryption_target,
    send_email_to_user_recipients,
)

_CHAT_CIPHERTEXT_MAX_LENGTH = 200_000
_CHAT_CIPHERTEXT_CONTEXT_VERSION = 2
_CONVERSATION_PARTICIPANT_COUNT = 2
_P256_COORDINATE_LENGTH_BYTES = 32
_P256_RAW_SIGNATURE_LENGTH_BYTES = 64
_CHAT_ONLY_MESSAGE_PLACEHOLDER = "Stored in encrypted conversation."
_CONVERSATION_ACTIVITY_TIMEOUT_SECONDS = 120
_CONVERSATION_PRESENCE_HEARTBEAT_SECONDS = 60
_CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_WINDOW_SECONDS = 60
_CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX = 10
_CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_WINDOW_SECONDS = 60
_CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX = 30
_CONVERSATION_MESSAGE_RATE_LIMIT_USER_WINDOW_SECONDS = 3600
_CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX = 200
_CONVERSATION_MESSAGE_RATE_LIMIT_LOCK_NAMESPACE = "hushline:chat-message-rate-limit"
_CONVERSATION_NOTIFICATION_BODY = (
    "You have new Hush Line conversation activity. "
    "Log in and unlock your Hush Line chat key to read it."
)
_ARMORED_PGP_MESSAGE_PATTERN = re.compile(
    r"^\s*-----BEGIN PGP MESSAGE-----\r?\n"
    r"(?:[!-~]+: .*\r?\n)*\r?\n?[\s\S]*\r?\n"
    r"-----END PGP MESSAGE-----\s*$"
)


def _pq_chat_error(code: str) -> tuple[Response, int]:
    status = 409 if code in {"STALE_MEMBERSHIP", "STATE_CONFLICT"} else 400
    return jsonify({"error": code}), status


def _active_pq_devices(account: ChatAccount, now: datetime) -> list[ChatDevice]:
    return list(
        db.session.scalars(
            db.select(ChatDevice)
            .where(
                ChatDevice.account_id == account.id,
                ChatDevice.revoked_at.is_(None),
                ChatDevice.expires_at > now,
                ChatDevice.membership_sequence == account.membership_sequence,
            )
            .order_by(ChatDevice.public_id.asc())
            .with_for_update()
        )
    )


def _current_pq_archive_epoch(account: ChatAccount) -> ChatArchiveEpoch | None:
    epochs = list(
        db.session.scalars(
            db.select(ChatArchiveEpoch)
            .where(
                ChatArchiveEpoch.account_id == account.id,
                ChatArchiveEpoch.retired_at.is_(None),
            )
            .order_by(ChatArchiveEpoch.epoch.desc())
            .with_for_update()
        )
    )
    return epochs[0] if len(epochs) == 1 else None


def _pq_chat_account_for_user(user_id: int) -> ChatAccount | None:
    return db.session.scalars(
        db.select(ChatAccount).where(ChatAccount.user_id == user_id)
    ).one_or_none()


def _authorized_pq_sender_device(user: User, payload: Any) -> ChatDevice | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("manifest"), dict):
        return None
    manifest = payload["manifest"]
    sender_account_id = manifest.get("sender_account_id")
    sender_device_id = manifest.get("sender_device_id")
    chat_session_id = session.get(CHAT_KEY_SESSION_ID_SESSION_KEY)
    if not all(isinstance(value, str) and value for value in (sender_account_id, sender_device_id)):
        return None
    if not isinstance(chat_session_id, str) or not chat_session_id:
        return None
    return db.session.scalars(
        db.select(ChatDevice)
        .join(ChatAccount)
        .where(
            ChatAccount.user_id == user.id,
            ChatAccount.public_id == sender_account_id,
            ChatDevice.public_id == sender_device_id,
            ChatDevice.session_id_hash == chat_session_binding(chat_session_id),
            ChatDevice.revoked_at.is_(None),
            ChatDevice.expires_at > datetime.now(UTC),
            ChatDevice.membership_sequence == ChatAccount.membership_sequence,
        )
    ).one_or_none()


def _validate_pq_copy_inventory(
    package: ValidatedPqChatPackage,
    *,
    thread: Conversation,
    sender_participant: ConversationParticipant,
    sender_device: ChatDevice,
) -> tuple[
    dict[str, ConversationParticipant],
    dict[str, ChatDevice],
    dict[str, ChatArchiveEpoch],
]:
    active_participants = _conversation_active_participants(thread)
    if len(active_participants) != _CONVERSATION_PARTICIPANT_COUNT:
        raise PqChatPackageError("STATE_CONFLICT")

    participant_by_account_id: dict[str, ConversationParticipant] = {}
    account_by_public_id: dict[str, ChatAccount] = {}
    devices_by_public_id: dict[str, ChatDevice] = {}
    epochs_by_account_id: dict[str, ChatArchiveEpoch] = {}
    expected_inventory: set[tuple[str, str, str]] = set()
    now = datetime.now(UTC)
    participant_by_user_id = {
        participant.user_id: participant for participant in active_participants
    }
    accounts = list(
        db.session.scalars(
            db.select(ChatAccount)
            .where(ChatAccount.user_id.in_(list(participant_by_user_id)))
            .order_by(ChatAccount.public_id.asc())
            .with_for_update()
        )
    )
    if len(accounts) != len(active_participants):
        raise PqChatPackageError("STALE_MEMBERSHIP")
    for account in accounts:
        if account.membership_sequence <= 0:
            raise PqChatPackageError("STALE_MEMBERSHIP")
        participant = participant_by_user_id[account.user_id]
        participant_by_account_id[account.public_id] = participant
        account_by_public_id[account.public_id] = account
        epoch = _current_pq_archive_epoch(account)
        if epoch is None:
            raise PqChatPackageError("STATE_CONFLICT")
        epochs_by_account_id[account.public_id] = epoch
        expected_inventory.add(
            ("archive", account.public_id, "00000000-0000-0000-0000-000000000000")
        )
        active_devices = _active_pq_devices(account, now)
        if not active_devices:
            raise PqChatPackageError("STALE_MEMBERSHIP")
        for device in active_devices:
            devices_by_public_id[device.public_id] = device
            if device.id != sender_device.id:
                expected_inventory.add(("transport", account.public_id, device.public_id))

    manifest = package.manifest
    if (
        manifest["conversation_id"] != thread.public_id
        or manifest["sender_account_id"] != sender_device.account.public_id
        or manifest["sender_device_id"] != sender_device.public_id
        or manifest["sender_membership_sha256"] != sender_device.membership_sha256
        or sender_participant.user_id != sender_device.account.user_id
    ):
        raise PqChatPackageError("AUTHENTICATION_FAILED")

    actual_inventory = {
        (
            copy.context["purpose"],
            copy.context["account_recipient_id"],
            copy.context["device_recipient_id"],
        )
        for copy in package.copies
    }
    if actual_inventory != expected_inventory:
        raise PqChatPackageError("STATE_CONFLICT")

    for copy in package.copies:
        context = copy.context
        account = account_by_public_id.get(context["account_recipient_id"])
        if account is None:
            raise PqChatPackageError("AUTHENTICATION_FAILED")
        if (
            context["sender_membership_sequence"] != sender_device.membership_sequence
            or context["recipient_membership_sequence"] != account.membership_sequence
        ):
            raise PqChatPackageError("STALE_MEMBERSHIP")
        if context["purpose"] == "transport":
            recipient_device = devices_by_public_id.get(context["device_recipient_id"])
            if (
                recipient_device is None
                or recipient_device.account_id != account.id
                or context["key_version"] != recipient_device.key_version
            ):
                raise PqChatPackageError("STALE_MEMBERSHIP")
        else:
            epoch = epochs_by_account_id[account.public_id]
            if context["archive_epoch"] != epoch.epoch or context["key_version"] != epoch.epoch:
                raise PqChatPackageError("STALE_MEMBERSHIP")
    return participant_by_account_id, devices_by_public_id, epochs_by_account_id


def _pq_idempotent_response(
    package: ValidatedPqChatPackage, *, conversation_id: int
) -> tuple[Response, int] | None:
    existing = db.session.scalars(
        db.select(ConversationMessage).where(
            or_(
                ConversationMessage.public_id == package.manifest["message_id"],
                ConversationMessage.idempotency_key == package.idempotency_key,
            )
        )
    ).first()
    if existing is None:
        return None
    if (
        existing.conversation_id != conversation_id
        or existing.public_id != package.manifest["message_id"]
        or existing.idempotency_key != package.idempotency_key
        or existing.request_sha256 != package.request_sha256
    ):
        raise PqChatPackageError("STATE_CONFLICT")
    return (
        jsonify(
            {
                "message_id": existing.public_id,
                "conversation_version": existing.conversation_version,
                "idempotent": True,
            }
        ),
        200,
    )


def _commit_pq_chat_message(
    *,
    thread: Conversation,
    participant: ConversationParticipant,
    user: User,
    payload: Any,
) -> tuple[Response, int]:
    if thread.minimum_protocol_version > PQ_CHAT_PROTOCOL_VERSION:
        return _pq_chat_error("SUITE_MISMATCH")
    sender_device = _authorized_pq_sender_device(user, payload)
    if sender_device is None:
        return _pq_chat_error("AUTHENTICATION_FAILED")
    try:
        package = validate_pq_chat_package(
            payload, sender_signing_public_key=sender_device.signing_public_key
        )
        prior_response = _pq_idempotent_response(package, conversation_id=thread.id)
        if prior_response is not None:
            return prior_response
        participants, devices, epochs = _validate_pq_copy_inventory(
            package,
            thread=thread,
            sender_participant=participant,
            sender_device=sender_device,
        )
        if _consume_conversation_message_rate_limit(
            thread=thread, participant=participant, user=user
        ):
            return jsonify({"error": "RATE_LIMITED"}), 429

        thread.minimum_protocol_version = max(
            thread.minimum_protocol_version, PQ_CHAT_PROTOCOL_VERSION
        )
        thread.version += 1
        message = ConversationMessage(
            public_id=package.manifest["message_id"],
            protocol_version=PQ_CHAT_PROTOCOL_VERSION,
            conversation_version=thread.version,
            idempotency_key=package.idempotency_key,
            request_sha256=package.request_sha256,
            manifest=package.manifest,
            manifest_signature=package.signature,
        )
        message.conversation = thread
        message.sender_participant = participant
        for copy in package.copies:
            context = copy.context
            recipient = participants[context["account_recipient_id"]]
            if context["purpose"] == "transport":
                message.transport_copies.append(
                    ConversationMessageTransportCopy(
                        recipient_participant=recipient,
                        recipient_device=devices[context["device_recipient_id"]],
                        key_version=context["key_version"],
                        context=context,
                        context_sha256=copy.context_sha256,
                        ciphertext_sha256=copy.ciphertext_sha256,
                        ciphertext=copy.ciphertext,
                    )
                )
            else:
                message.archive_copies.append(
                    ConversationMessageArchiveCopy(
                        recipient_participant=recipient,
                        archive_epoch=epochs[context["account_recipient_id"]],
                        context=context,
                        context_sha256=copy.context_sha256,
                        ciphertext_sha256=copy.ciphertext_sha256,
                        ciphertext=copy.ciphertext,
                    )
                )
        db.session.add(message)
        _mark_conversation_participant_active(participant)
        db.session.commit()
    except PqChatPackageError as error:
        db.session.rollback()
        return _pq_chat_error(error.code)
    except IntegrityError:
        db.session.rollback()
        try:
            replay = _pq_idempotent_response(package, conversation_id=thread.id)
        except PqChatPackageError as error:
            return _pq_chat_error(error.code)
        if replay is not None:
            return replay
        return _pq_chat_error("STATE_CONFLICT")

    _notify_conversation_participants(thread, participant)
    return (
        jsonify(
            {
                "message_id": message.public_id,
                "conversation_version": message.conversation_version,
                "idempotent": False,
            }
        ),
        201,
    )


def _conversation_latest_message(thread: Conversation) -> ConversationMessage | None:
    if not thread.messages:
        return None

    return max(
        thread.messages,
        key=lambda message: (message.created_at, message.id),
    )


def _conversation_other_participants(
    thread: Conversation, participant: ConversationParticipant
) -> list[ConversationParticipant]:
    return [
        thread_participant
        for thread_participant in thread.participants
        if thread_participant.id != participant.id and thread_participant.user
    ]


def _conversation_active_participants(thread: Conversation) -> list[ConversationParticipant]:
    return [
        thread_participant
        for thread_participant in thread.participants
        if thread_participant.deleted_at is None
    ]


def _conversation_reply_capable_participant_ids(thread: Conversation) -> set[str]:
    return {
        str(thread_participant.id)
        for thread_participant in thread.participants
        if (
            thread_participant.deleted_at is None
            and thread_participant.user
            and thread_participant.user.active_chat_key
            and thread_participant.user.chat_public_key
            and thread_participant.user.chat_public_signing_key
        )
    }


def _participant_can_sign_replies(participant: ConversationParticipant) -> bool:
    return bool(
        participant.user
        and participant.user.active_chat_key
        and participant.user.chat_public_key
        and participant.user.chat_public_signing_key
    )


def _locked_conversation_participants(thread: Conversation) -> list[ConversationParticipant]:
    return list(
        db.session.scalars(
            db.select(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == thread.id)
            .order_by(ConversationParticipant.id)
            .with_for_update()
        )
    )


def _is_conversation_background_refresh() -> bool:
    return request.headers.get("X-Hushline-Conversation-Refresh", "").lower() == "true"


def _conversation_activity_timeout() -> timedelta:
    configured_seconds = current_app.config.get(
        "CONVERSATION_ACTIVITY_TIMEOUT_SECONDS", _CONVERSATION_ACTIVITY_TIMEOUT_SECONDS
    )
    try:
        seconds = int(configured_seconds)
    except (TypeError, ValueError):
        seconds = _CONVERSATION_ACTIVITY_TIMEOUT_SECONDS
    return timedelta(seconds=max(1, seconds))


def _conversation_presence_heartbeat_ms() -> int:
    configured_seconds = current_app.config.get(
        "CONVERSATION_PRESENCE_HEARTBEAT_SECONDS", _CONVERSATION_PRESENCE_HEARTBEAT_SECONDS
    )
    try:
        seconds = int(configured_seconds)
    except (TypeError, ValueError):
        seconds = _CONVERSATION_PRESENCE_HEARTBEAT_SECONDS
    return max(1, seconds) * 1000


def _conversation_rate_limit_config(name: str, default: int) -> int:
    value = current_app.config.get(name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _conversation_message_rate_limit_lock_key(scope: str, *values: int) -> int:
    payload = ":".join(
        [_CONVERSATION_MESSAGE_RATE_LIMIT_LOCK_NAMESPACE, scope, *(str(value) for value in values)]
    ).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big", signed=True)


def _lock_conversation_message_rate_limit_buckets(
    *,
    thread: Conversation,
    participant: ConversationParticipant,
    user: User,
) -> None:
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return

    lock_keys = sorted(
        {
            _conversation_message_rate_limit_lock_key("participant", participant.id, thread.id),
            _conversation_message_rate_limit_lock_key("conversation", thread.id),
            _conversation_message_rate_limit_lock_key("user", user.id),
        }
    )
    for lock_key in lock_keys:
        db.session.execute(db.select(db.func.pg_advisory_xact_lock(lock_key)))


def _consume_conversation_message_rate_limit(
    *,
    thread: Conversation,
    participant: ConversationParticipant,
    user: User,
) -> bool:
    _lock_conversation_message_rate_limit_buckets(
        thread=thread,
        participant=participant,
        user=user,
    )
    windows = {
        "participant": max(
            _conversation_rate_limit_config(
                "CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_WINDOW_SECONDS",
                _CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_WINDOW_SECONDS,
            ),
            1,
        ),
        "conversation": max(
            _conversation_rate_limit_config(
                "CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_WINDOW_SECONDS",
                _CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_WINDOW_SECONDS,
            ),
            1,
        ),
        "user": max(
            _conversation_rate_limit_config(
                "CONVERSATION_MESSAGE_RATE_LIMIT_USER_WINDOW_SECONDS",
                _CONVERSATION_MESSAGE_RATE_LIMIT_USER_WINDOW_SECONDS,
            ),
            1,
        ),
    }
    limits = {
        "participant": _conversation_rate_limit_config(
            "CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX",
            _CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX,
        ),
        "conversation": _conversation_rate_limit_config(
            "CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX",
            _CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX,
        ),
        "user": _conversation_rate_limit_config(
            "CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX",
            _CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX,
        ),
    }
    now = datetime.now(UTC)
    oldest_window = now - timedelta(seconds=max(windows.values()))
    db.session.execute(
        db.delete(ChatRateLimitAttempt).where(ChatRateLimitAttempt.created_at < oldest_window)
    )

    participant_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ChatRateLimitAttempt)
        .where(
            ChatRateLimitAttempt.sender_participant_id == participant.id,
            ChatRateLimitAttempt.conversation_id == thread.id,
            ChatRateLimitAttempt.created_at >= now - timedelta(seconds=windows["participant"]),
        )
    )
    conversation_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ChatRateLimitAttempt)
        .where(
            ChatRateLimitAttempt.conversation_id == thread.id,
            ChatRateLimitAttempt.created_at >= now - timedelta(seconds=windows["conversation"]),
        )
    )
    user_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ChatRateLimitAttempt)
        .where(
            ChatRateLimitAttempt.user_id == user.id,
            ChatRateLimitAttempt.created_at >= now - timedelta(seconds=windows["user"]),
        )
    )
    limited = (
        (
            limits["participant"] > 0
            and participant_count is not None
            and participant_count >= limits["participant"]
        )
        or (
            limits["conversation"] > 0
            and conversation_count is not None
            and conversation_count >= limits["conversation"]
        )
        or (limits["user"] > 0 and user_count is not None and user_count >= limits["user"])
    )
    if not limited:
        db.session.add(
            ChatRateLimitAttempt(
                conversation_id=thread.id,
                sender_participant_id=participant.id,
                user_id=user.id,
                created_at=now,
            )
        )
    return limited


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mark_conversation_participant_active(
    participant: ConversationParticipant, now: datetime | None = None
) -> None:
    participant.last_active_at = now or datetime.now(UTC)


def _message_is_chat_only_placeholder(message: Message) -> bool:
    return bool(message.field_values) and all(
        field_value.encrypted is False and field_value.value == _CHAT_ONLY_MESSAGE_PLACEHOLDER
        for field_value in message.field_values
    )


def _conversation_participant_is_active(
    participant: ConversationParticipant, now: datetime | None = None
) -> bool:
    if participant.last_active_at is None:
        return False
    active_at = _as_utc(participant.last_active_at)
    current_time = now or datetime.now(UTC)
    return current_time - active_at <= _conversation_activity_timeout()


def _user_has_active_conversation_session(user: User, now: datetime | None = None) -> bool:
    return any(
        participant.user_id == user.id and _conversation_participant_is_active(participant, now=now)
        for participant in user.conversation_participants
    )


def _is_armored_pgp_message(value: str) -> bool:
    return bool(_ARMORED_PGP_MESSAGE_PATTERN.fullmatch(value))


def _validate_json_csrf() -> str | None:
    if current_app.config.get("WTF_CSRF_ENABLED") is False:
        return None

    token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    try:
        validate_csrf(token)
    except ValidationError:
        return "Invalid CSRF token."
    return None


def _is_chat_ciphertext_envelope(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > _CHAT_CIPHERTEXT_MAX_LENGTH:
        return False

    try:
        envelope = current_app.json.loads(value)
    except ValueError:
        return False

    if not isinstance(envelope, dict):
        return False

    required_fields = ("algorithm", "ephemeral_public_key", "iv", "ciphertext")
    if not all(
        isinstance(envelope.get(field), str) and envelope[field] for field in required_fields
    ):
        return False
    if envelope["algorithm"] != "ECDH-P256-AES-GCM":
        return False
    if envelope.get("v") in (None, 1):
        return True
    if envelope.get("v") != _CHAT_CIPHERTEXT_CONTEXT_VERSION:
        return False
    return (
        isinstance(envelope.get("context"), dict)
        and isinstance(envelope.get("signature"), str)
        and bool(envelope["signature"])
    )


def _chat_ciphertext_context(value: str) -> dict[str, Any] | None:
    try:
        envelope = current_app.json.loads(value)
    except ValueError:
        return None

    if not isinstance(envelope, dict) or envelope.get("v") != _CHAT_CIPHERTEXT_CONTEXT_VERSION:
        return None
    context = envelope.get("context")
    return context if isinstance(context, dict) else None


def _canonical_chat_signature_payload(envelope: dict[str, Any]) -> bytes | None:
    try:
        return json.dumps(
            {
                "v": envelope["v"],
                "algorithm": envelope["algorithm"],
                "ephemeral_public_key": envelope["ephemeral_public_key"],
                "iv": envelope["iv"],
                "ciphertext": envelope["ciphertext"],
                "context": envelope["context"],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (KeyError, TypeError, ValueError):
        return None


def _decode_jwk_coordinate(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        padded_value = value + "=" * (-len(value) % 4)
        coordinate = base64.b64decode(padded_value, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(coordinate) != _P256_COORDINATE_LENGTH_BYTES:
        return None
    return int.from_bytes(coordinate, "big")


def _chat_signing_public_key(public_signing_key: str | None) -> ec.EllipticCurvePublicKey | None:
    if not public_signing_key:
        return None
    try:
        jwk = current_app.json.loads(public_signing_key)
    except ValueError:
        return None
    if not isinstance(jwk, dict) or jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        return None

    x_coordinate = _decode_jwk_coordinate(jwk.get("x"))
    y_coordinate = _decode_jwk_coordinate(jwk.get("y"))
    if x_coordinate is None or y_coordinate is None:
        return None
    try:
        return ec.EllipticCurvePublicNumbers(
            x_coordinate,
            y_coordinate,
            ec.SECP256R1(),
        ).public_key()
    except ValueError:
        return None


def _chat_ciphertext_signature_is_valid(value: str, public_signing_key: str | None) -> bool:
    verification_key = _chat_signing_public_key(public_signing_key)
    if verification_key is None:
        return False

    try:
        envelope = current_app.json.loads(value)
    except ValueError:
        return False
    if not isinstance(envelope, dict) or envelope.get("v") != _CHAT_CIPHERTEXT_CONTEXT_VERSION:
        return False

    signed_payload = _canonical_chat_signature_payload(envelope)
    if signed_payload is None:
        return False

    signature_value = envelope.get("signature")
    if not isinstance(signature_value, str):
        return False
    try:
        signature = base64.b64decode(signature_value, validate=True)
    except (binascii.Error, TypeError, ValueError):
        return False
    if len(signature) != _P256_RAW_SIGNATURE_LENGTH_BYTES:
        return False

    der_signature = encode_dss_signature(
        int.from_bytes(signature[:_P256_COORDINATE_LENGTH_BYTES], "big"),
        int.from_bytes(signature[_P256_COORDINATE_LENGTH_BYTES:], "big"),
    )
    try:
        verification_key.verify(der_signature, signed_payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def _chat_ciphertext_signatures_are_valid(
    encrypted_copies: dict[str, object],
    *,
    public_signing_key: str | None,
) -> bool:
    return all(
        isinstance(encrypted_payload, str)
        and _chat_ciphertext_signature_is_valid(encrypted_payload, public_signing_key)
        for encrypted_payload in encrypted_copies.values()
    )


def _chat_ciphertext_context_is_bound(
    encrypted_copies: dict[str, object],
    *,
    conversation: Conversation,
    sender_participant_id: int,
) -> bool:
    for recipient_participant_id, encrypted_payload in encrypted_copies.items():
        if not isinstance(encrypted_payload, str):
            return False
        context = _chat_ciphertext_context(encrypted_payload)
        if context is None:
            return False
        if context.get("purpose") != "hushline.chat.message":
            return False
        conversation_public_id = context.get("conversation_public_id")
        if conversation_public_id is not None:
            if str(conversation_public_id) != conversation.public_id:
                return False
        elif str(context.get("conversation_id")) != str(conversation.id):
            return False
        if str(context.get("sender_participant_id")) != str(sender_participant_id):
            return False
        if str(context.get("recipient_participant_id")) != str(recipient_participant_id):
            return False
    return True


def _conversation_notification_body(user: User) -> str:
    if not (user.email_include_message_content and user.email_encrypt_entire_body):
        return _CONVERSATION_NOTIFICATION_BODY

    notification_encryption_target = notification_email_encryption_target(user)
    if not notification_encryption_target:
        return _CONVERSATION_NOTIFICATION_BODY

    try:
        return encrypt_message(_CONVERSATION_NOTIFICATION_BODY, notification_encryption_target)
    except (RuntimeError, TypeError, ValueError) as e:
        current_app.logger.error(
            "Failed to encrypt conversation notification body: %s",
            str(e),
            exc_info=True,
        )
        return _CONVERSATION_NOTIFICATION_BODY


def _notify_conversation_participants(
    thread: Conversation, sender_participant: ConversationParticipant
) -> None:
    for recipient_participant in thread.participants:
        recipient_user = recipient_participant.user
        if recipient_participant.id == sender_participant.id or recipient_user is None:
            continue
        if not recipient_user.enable_email_notifications:
            continue
        if _user_has_active_conversation_session(recipient_user):
            continue

        try:
            send_email_to_user_recipients(
                recipient_user,
                "New Hush Line Conversation Activity",
                _conversation_notification_body(recipient_user),
            )
        except (RuntimeError, OSError, TypeError, ValueError, smtplib.SMTPException) as e:
            current_app.logger.error(
                "Failed to send conversation notification for participant %s: %s",
                recipient_participant.id,
                str(e),
                exc_info=True,
            )


def register_message_routes(app: Flask) -> None:
    @app.route("/message/<public_id>")
    @authentication_required
    def message(public_id: str) -> str:
        msg = db.session.scalars(
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == session["user_id"], Message.public_id == public_id)
        ).one_or_none()

        if not msg:
            abort(404)

        update_status_form = UpdateMessageStatusForm(data={"status": msg.status.value})
        delete_message_form = DeleteMessageForm()
        resend_message_form = ResendMessageForm()

        return render_template(
            "message.html",
            message=msg,
            update_status_form=update_status_form,
            delete_message_form=delete_message_form,
            resend_message_form=resend_message_form,
        )

    @app.route("/conversation/<public_id>")
    @authentication_required
    def conversation(public_id: str) -> str:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.public_id == public_id)
        ).one_or_none()
        if not thread:
            abort(404)

        participant = thread.participant_for_user_id(user.id)
        if not participant:
            abort(404)

        _mark_conversation_participant_active(participant)
        latest_message = _conversation_latest_message(thread)
        if (
            not _is_conversation_background_refresh()
            and latest_message
            and (
                participant.last_read_message_id != latest_message.id
                or participant.last_read_at is None
                or latest_message.created_at > participant.last_read_at
            )
        ):
            participant.last_read_at = latest_message.created_at
            participant.last_read_message = latest_message
        db.session.commit()

        other_participants = _conversation_other_participants(thread, participant)
        conversation_name = ", ".join(
            other_participant.user.primary_username.display_name
            or other_participant.user.primary_username.username
            for other_participant in other_participants
        )
        conversation_username = (
            other_participants[0].user.primary_username.username
            if len(other_participants) == 1
            else None
        )

        message_copies = []
        message_copy_payloads = []
        for conversation_message in thread.messages:
            copy = next(
                (
                    encrypted_copy
                    for encrypted_copy in conversation_message.encrypted_copies
                    if encrypted_copy.recipient_participant_id == participant.id
                ),
                None,
            )
            message_copies.append(
                (
                    conversation_message,
                    copy,
                    conversation_message.sender_participant_id == participant.id,
                )
            )
            message_copy_payloads.append(
                {
                    "message_id": conversation_message.id,
                    "encrypted_payload": copy.encrypted_payload if copy else None,
                }
            )

        participant_public_keys = [
            {
                "participant_id": thread_participant.id,
                "key_version": thread_participant.user.active_chat_key.key_version,
                "public_key": thread_participant.user.chat_public_key,
                "public_key_fingerprint": chat_key_fingerprint(
                    thread_participant.user.chat_public_key
                ),
                "public_signing_key": thread_participant.user.chat_public_signing_key,
                "public_signing_key_fingerprint": chat_key_fingerprint(
                    thread_participant.user.chat_public_signing_key
                ),
            }
            for thread_participant in thread.participants
            if (
                thread_participant.deleted_at is None
                and thread_participant.user
                and thread_participant.user.active_chat_key
                and thread_participant.user.chat_public_key
            )
        ]
        participant_signing_public_keys = [
            {
                "participant_id": thread_participant.id,
                "key_version": chat_key.key_version,
                "public_signing_key": chat_key.public_signing_key,
                "public_signing_key_fingerprint": chat_key_fingerprint(chat_key.public_signing_key),
            }
            for thread_participant in thread.participants
            if thread_participant.user
            for chat_key in thread_participant.user.chat_keys
            if chat_key.public_signing_key
        ]
        has_rotated_participant_keys = any(
            thread_participant.deleted_at is None
            and thread_participant.user
            and thread_participant.user.active_chat_key
            and thread_participant.user.active_chat_key.key_version > 1
            for thread_participant in thread.participants
        )
        if has_rotated_participant_keys:
            flash(
                "One or more participants are using rotated chat keys. Verify "
                "fingerprints before sharing sensitive follow-up details."
            )
        active_participants = _conversation_active_participants(thread)
        reply_capable_participant_ids = _conversation_reply_capable_participant_ids(thread)
        can_compose = (
            len(active_participants) == len(thread.participants)
            and len(participant_public_keys) == len(thread.participants)
            and len(reply_capable_participant_ids) == len(thread.participants)
            and _participant_can_sign_replies(participant)
        )
        conversation_message_form = ConversationMessageForm()
        delete_conversation_form = DeleteConversationForm()

        return render_template(
            "conversation.html",
            conversation=thread,
            participant=participant,
            message_copies=message_copies,
            message_copy_payloads=message_copy_payloads,
            participant_public_keys=participant_public_keys,
            participant_signing_public_keys=participant_signing_public_keys,
            can_compose=can_compose,
            conversation_name=conversation_name or "Conversation",
            conversation_username=conversation_username,
            conversation_presence_interval_ms=_conversation_presence_heartbeat_ms(),
            conversation_message_form=conversation_message_form,
            delete_conversation_form=delete_conversation_form,
        )

    @app.route("/api/pq/conversations/to/<username>/messages", methods=["POST"])
    @authentication_required
    def create_pq_conversation_message(username: str) -> tuple[Response, int]:
        user = db.session.get(User, session["user_id"])
        recipient_username = db.session.scalars(
            db.select(Username).where(db.func.lower(Username._username) == username.lower())
        ).one_or_none()
        if user is None or recipient_username is None or recipient_username.user_id == user.id:
            abort(404)

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return jsonify({"error": csrf_error}), 400
        payload: Any = request.get_json(silent=True)
        manifest = payload.get("manifest") if isinstance(payload, dict) else None
        conversation_id = manifest.get("conversation_id") if isinstance(manifest, dict) else None
        if not isinstance(manifest, dict) or not isinstance(conversation_id, str):
            return _pq_chat_error("MALFORMED_WIRE")
        try:
            if str(UUID(conversation_id)) != conversation_id:
                return _pq_chat_error("MALFORMED_WIRE")
        except ValueError:
            return _pq_chat_error("MALFORMED_WIRE")
        if recipient_username.user.is_suspended:
            abort(404)

        owner_guard_nonce = request.headers.get("X-Hushline-Owner-Guard-Nonce", "")
        owner_guard_signature = request.headers.get("X-Hushline-Owner-Guard-Signature", "")
        expected_owner_guard_signature = hmac.new(
            key=(current_app.secret_key or "").encode("utf-8"),
            msg=(
                f"{recipient_username.username}:{recipient_username.user_id}:"
                f"{owner_guard_nonce}"
            ).encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        captcha_answer = request.headers.get("X-Hushline-Captcha-Answer", "")
        if (
            not owner_guard_nonce
            or not owner_guard_signature
            or not hmac.compare_digest(owner_guard_signature, expected_owner_guard_signature)
            or not captcha_answer
            or not hmac.compare_digest(captcha_answer, str(session.get("math_answer", "")))
        ):
            return _pq_chat_error("AUTHENTICATION_FAILED")

        thread = db.session.scalars(
            Conversation.for_user_id(user.id)
            .where(Conversation.public_id == conversation_id)
            .with_for_update()
        ).one_or_none()
        existing_thread = thread is not None
        if thread is None:
            thread = Conversation(public_id=conversation_id)
            sender_participant = ConversationParticipant(
                user=user,
                has_usable_public_key=True,
            )
            recipient_participant = ConversationParticipant(
                user=recipient_username.user,
                has_usable_public_key=True,
            )
            thread.participants.extend([sender_participant, recipient_participant])
            initial_message = Message(username_id=recipient_username.id)
            initial_message.conversation = thread
            db.session.add(initial_message)
            for field_definition in recipient_username.message_fields:
                if field_definition.enabled:
                    db.session.add(
                        FieldValue(
                            field_definition,
                            initial_message,
                            _CHAT_ONLY_MESSAGE_PLACEHOLDER,
                            False,
                        )
                    )
            db.session.add(
                InitialConversationNonce(
                    nonce_hash=hashlib.sha256(
                        f"hushline:initial-conversation:{owner_guard_nonce}".encode()
                    ).hexdigest(),
                    sender_user_id=user.id,
                    recipient_user_id=recipient_username.user_id,
                    consumed_at=datetime.now(UTC),
                )
            )
            db.session.add(thread)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                thread = db.session.scalars(
                    Conversation.for_user_id(user.id)
                    .where(Conversation.public_id == conversation_id)
                    .with_for_update()
                ).one_or_none()
                if thread is None:
                    return _pq_chat_error("STATE_CONFLICT")
                existing_thread = True

        if existing_thread:
            existing_message_id = db.session.scalar(
                db.select(ConversationMessage.id).where(
                    ConversationMessage.conversation_id == thread.id,
                    ConversationMessage.public_id == manifest.get("message_id"),
                )
            )
            if existing_message_id is None:
                db.session.rollback()
                return _pq_chat_error("STATE_CONFLICT")

        participant = thread.participant_for_user_id(user.id)
        participant_user_ids = {item.user_id for item in _conversation_active_participants(thread)}
        if (
            participant is None
            or participant_user_ids != {user.id, recipient_username.user_id}
            or thread.minimum_protocol_version not in {0, PQ_CHAT_PROTOCOL_VERSION}
        ):
            db.session.rollback()
            return _pq_chat_error("STATE_CONFLICT")
        return _commit_pq_chat_message(
            thread=thread,
            participant=participant,
            user=user,
            payload=payload,
        )

    @app.route("/conversation/<public_id>/messages/<message_public_id>")
    @authentication_required
    def pq_conversation_message(public_id: str, message_public_id: str) -> tuple[Response, int]:
        user = db.session.get(User, session["user_id"])
        if user is None:
            abort(404)
        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.public_id == public_id)
        ).one_or_none()
        if thread is None:
            abort(404)
        participant = thread.participant_for_user_id(user.id)
        account = _pq_chat_account_for_user(user.id)
        chat_session_id = session.get(CHAT_KEY_SESSION_ID_SESSION_KEY)
        device_id = request.headers.get("X-Hushline-Device-ID") or request.args.get("device_id")
        if (
            participant is None
            or account is None
            or not isinstance(chat_session_id, str)
            or not isinstance(device_id, str)
        ):
            abort(404)
        device = db.session.scalars(
            db.select(ChatDevice).where(
                ChatDevice.account_id == account.id,
                ChatDevice.public_id == device_id,
                ChatDevice.session_id_hash == chat_session_binding(chat_session_id),
                ChatDevice.revoked_at.is_(None),
                ChatDevice.expires_at > datetime.now(UTC),
                ChatDevice.membership_sequence == account.membership_sequence,
            )
        ).one_or_none()
        if device is None:
            abort(404)
        message = db.session.scalars(
            db.select(ConversationMessage).where(
                ConversationMessage.conversation_id == thread.id,
                ConversationMessage.public_id == message_public_id,
                ConversationMessage.protocol_version == PQ_CHAT_PROTOCOL_VERSION,
            )
        ).one_or_none()
        if message is None or message.manifest is None or message.manifest_signature is None:
            abort(404)

        authorized: dict[tuple[str, str, str], dict[str, Any]] = {}
        for copy in message.archive_copies:
            if copy.recipient_participant_id == participant.id:
                context = copy.context
                key = (
                    "archive",
                    context["account_recipient_id"],
                    context["device_recipient_id"],
                )
                authorized[key] = {
                    "context": context,
                    "ciphertext": copy.ciphertext,
                }
        for copy in message.transport_copies:
            if copy.recipient_device_id == device.id:
                context = copy.context
                key = (
                    "transport",
                    context["account_recipient_id"],
                    context["device_recipient_id"],
                )
                authorized[key] = {
                    "context": context,
                    "ciphertext": copy.ciphertext,
                }
        ordered_copies = []
        for manifest_copy in message.manifest["copies"]:
            key = (
                manifest_copy["purpose"],
                manifest_copy["account_recipient_id"],
                manifest_copy["device_recipient_id"],
            )
            if key in authorized:
                ordered_copies.append(authorized[key])
        return (
            jsonify(
                {
                    "manifest": message.manifest,
                    "signature": message.manifest_signature,
                    "copies": ordered_copies,
                    "conversation_version": message.conversation_version,
                }
            ),
            200,
        )

    @app.route("/conversation/<public_id>/presence", methods=["POST"])
    @authentication_required
    def conversation_presence(public_id: str) -> tuple[Response, int]:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.public_id == public_id)
        ).one_or_none()
        if not thread:
            abort(404)

        participant = thread.participant_for_user_id(user.id)
        if not participant:
            abort(404)

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return jsonify({"error": csrf_error}), 400

        _mark_conversation_participant_active(participant)
        db.session.commit()
        return jsonify({"ok": True}), 200

    @app.route("/conversation/<public_id>/messages", methods=["POST"])
    @authentication_required
    def append_conversation_message(public_id: str) -> tuple[Response, int]:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.public_id == public_id)
        ).one_or_none()
        if not thread:
            abort(404)

        participant = thread.participant_for_user_id(user.id)
        if not participant:
            abort(404)

        csrf_error = _validate_json_csrf()
        if csrf_error:
            return jsonify({"error": csrf_error}), 400

        payload: Any = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        if set(payload) == {"manifest", "signature", "copies"}:
            thread = db.session.scalars(
                Conversation.for_user_id(user.id)
                .where(Conversation.public_id == public_id)
                .with_for_update()
            ).one_or_none()
            if thread is None:
                abort(404)
            participant = thread.participant_for_user_id(user.id)
            if participant is None:
                abort(404)
            return _commit_pq_chat_message(
                thread=thread,
                participant=participant,
                user=user,
                payload=payload,
            )

        encrypted_copies = payload.get("encrypted_copies")
        if not isinstance(encrypted_copies, dict):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        thread = db.session.scalars(
            Conversation.for_user_id(user.id)
            .where(Conversation.public_id == public_id)
            .with_for_update()
        ).one_or_none()
        if thread is None:
            abort(404)
        participant = thread.participant_for_user_id(user.id)
        if participant is None:
            abort(404)
        if thread.minimum_protocol_version >= PQ_CHAT_PROTOCOL_VERSION:
            return jsonify({"error": "Conversation requires protected messages."}), 409

        reply_capable_participant_ids = _conversation_reply_capable_participant_ids(thread)
        active_participants = _conversation_active_participants(thread)
        if (
            len(active_participants) != len(thread.participants)
            or len(reply_capable_participant_ids) != len(thread.participants)
            or not _participant_can_sign_replies(participant)
        ):
            return jsonify({"error": "Conversation replies are unavailable."}), 400

        if set(encrypted_copies.keys()) != reply_capable_participant_ids:
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        if not all(_is_chat_ciphertext_envelope(value) for value in encrypted_copies.values()):
            return jsonify({"error": "Invalid encrypted message payload."}), 400
        if not _chat_ciphertext_context_is_bound(
            encrypted_copies,
            conversation=thread,
            sender_participant_id=participant.id,
        ):
            return jsonify({"error": "Invalid encrypted message payload."}), 400
        if not _chat_ciphertext_signatures_are_valid(
            encrypted_copies,
            public_signing_key=(
                participant.user.chat_public_signing_key if participant.user else None
            ),
        ):
            return jsonify({"error": "Invalid encrypted message payload."}), 400

        if _consume_conversation_message_rate_limit(
            thread=thread, participant=participant, user=user
        ):
            return (
                jsonify(
                    {
                        "error": (
                            "Too many chat messages. " "Please wait before sending another reply."
                        )
                    }
                ),
                429,
            )

        thread.version += 1
        conversation_message = ConversationMessage(conversation_version=thread.version)
        conversation_message.conversation = thread
        conversation_message.sender_participant = participant
        db.session.add(conversation_message)
        _mark_conversation_participant_active(participant)
        for recipient_participant in thread.participants:
            encrypted_copy = ConversationMessageCopy()
            conversation_message.encrypted_copies.append(encrypted_copy)
            encrypted_copy.recipient_participant = recipient_participant
            encrypted_copy.encrypted_payload = encrypted_copies[str(recipient_participant.id)]
        db.session.commit()
        _notify_conversation_participants(thread, participant)

        return (
            jsonify(
                {
                    "message_id": conversation_message.id,
                }
            ),
            201,
        )

    @app.route("/conversation/<public_id>/delete", methods=["POST"])
    @authentication_required
    def delete_conversation(public_id: str) -> Response:
        user = db.session.get(User, session["user_id"])
        if not user:
            abort(404)

        thread = db.session.scalars(
            Conversation.for_user_id(user.id).where(Conversation.public_id == public_id)
        ).one_or_none()
        if not thread or not thread.participant_for_user_id(user.id):
            abort(404)

        delete_conversation_form = DeleteConversationForm()
        if not delete_conversation_form.validate_on_submit():
            abort(400)

        locked_participants = _locked_conversation_participants(thread)
        participant = next(
            (
                thread_participant
                for thread_participant in locked_participants
                if thread_participant.user_id == user.id
            ),
            None,
        )
        if participant is None:
            abort(404)

        initial_message = thread.initial_message
        if initial_message is not None and not _message_is_chat_only_placeholder(initial_message):
            initial_message.conversation = None

        participant.deleted_at = datetime.now(UTC)
        participant.last_read_at = participant.deleted_at
        participant.last_read_message = _conversation_latest_message(thread)

        participant_message_ids = db.select(ConversationMessage.id).where(
            ConversationMessage.sender_participant_id == participant.id
        )
        db.session.execute(
            db.delete(ConversationMessageCopy).where(
                ConversationMessageCopy.conversation_message_id.in_(participant_message_ids)
            ),
            execution_options={"synchronize_session": False},
        )
        db.session.execute(
            db.delete(ConversationMessageTransportCopy).where(
                or_(
                    ConversationMessageTransportCopy.conversation_message_id.in_(
                        participant_message_ids
                    ),
                    ConversationMessageTransportCopy.recipient_participant_id == participant.id,
                )
            ),
            execution_options={"synchronize_session": False},
        )
        db.session.execute(
            db.delete(ConversationMessageArchiveCopy).where(
                or_(
                    ConversationMessageArchiveCopy.conversation_message_id.in_(
                        participant_message_ids
                    ),
                    ConversationMessageArchiveCopy.recipient_participant_id == participant.id,
                )
            ),
            execution_options={"synchronize_session": False},
        )
        db.session.execute(
            db.delete(ConversationMessageCopy).where(
                ConversationMessageCopy.recipient_participant_id == participant.id
            ),
            execution_options={"synchronize_session": False},
        )

        db.session.flush()
        if not any(
            thread_participant.deleted_at is None for thread_participant in locked_participants
        ):
            initial_message = thread.initial_message
            if initial_message is not None:
                if _message_is_chat_only_placeholder(initial_message):
                    db.session.delete(initial_message)
                else:
                    initial_message.conversation = None
            db.session.delete(thread)
        db.session.commit()
        flash("Conversation deleted successfully.")
        return redirect(url_for("inbox", type="conversations"))

    @app.route("/reply/<slug>")
    def message_reply(slug: str) -> str:
        msg = db.session.scalars(db.select(Message).filter_by(reply_slug=slug)).one_or_none()
        if msg is None:
            abort(404)

        return render_template("reply.html", message=msg)

    @app.route("/message/<public_id>/delete", methods=["POST"])
    @authentication_required
    def delete_message(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        message = db.session.scalars(
            db.select(Message).where(
                Message.public_id == public_id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
                ),
            )
        ).one_or_none()
        if message:
            db.session.execute(db.delete(FieldValue).where(FieldValue.message_id == message.id))
            db.session.commit()

            db.session.delete(message)
            db.session.commit()
            flash("🗑️ Message deleted successfully.")
        else:
            flash("⛔️ Message not found.")

        return redirect(url_for("inbox"))

    @app.route("/message/<public_id>/resend", methods=["POST"])
    @authentication_required
    def resend_message(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        form = ResendMessageForm()
        if not form.validate_on_submit():
            flash("⛔️ Invalid resend request.")
            return redirect(url_for("message", public_id=public_id))

        message = db.session.scalars(
            db.select(Message)
            .join(Username)
            .filter(Username.user_id == user.id, Message.public_id == public_id)
        ).one_or_none()
        if not message:
            flash("⛔️ Message not found.")
            return redirect(url_for("inbox"))

        if not user.enable_email_notifications:
            flash("⛔️ Email notifications are disabled.")
            return redirect(url_for("message", public_id=public_id))

        extracted_fields = [
            (field_value.field_definition.label, field_value.value or "")
            for field_value in message.field_values
        ]
        generic_body = "You have a new Hush Line message! Please log in to read it."
        notification_encryption_target = notification_email_encryption_target(user)

        if user.email_include_message_content:
            sent_any = False
            for _, value in extracted_fields:
                if not value:
                    continue
                if user.email_encrypt_entire_body:
                    value_is_armored = _is_armored_pgp_message(value)
                    if value_is_armored and isinstance(notification_encryption_target, str):
                        email_body = value
                    else:
                        try:
                            email_body = (
                                encrypt_message(value, notification_encryption_target)
                                if notification_encryption_target and not value_is_armored
                                else None
                            )
                            if value_is_armored and not isinstance(
                                notification_encryption_target, str
                            ):
                                current_app.logger.warning(
                                    "Cannot reuse single-recipient armored resend body for "
                                    "multi-recipient delivery; sending generic notification."
                                )
                        except (RuntimeError, TypeError, ValueError) as e:
                            current_app.logger.error(
                                "Failed to encrypt email body: %s", str(e), exc_info=True
                            )
                            email_body = None
                    do_send_email(user, (email_body or generic_body).strip())
                else:
                    do_send_email(user, value.strip())
                sent_any = True
            if not sent_any:
                do_send_email(user, generic_body)
        else:
            do_send_email(user, generic_body)
        flash("📧 Message resent to your email inbox.")
        return redirect(url_for("message", public_id=public_id))

    @app.route("/message/<public_id>/status", methods=["POST"])
    @authentication_required
    def set_message_status(public_id: str) -> Response:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()

        form = UpdateMessageStatusForm()
        if not form.validate():
            flash(f"⛔️ Invalid status: {form.status.data}.")
            return redirect(url_for("message", public_id=public_id))

        row_count = db.session.execute(
            db.update(Message)
            .where(
                Message.public_id == public_id,
                Message.username_id.in_(
                    db.select(Username.id).select_from(Username).filter(Username.user_id == user.id)
                ),
            )
            .values(status=form.status.data, status_changed_at=datetime.now(UTC))
        ).rowcount
        match row_count:
            case 1:
                db.session.commit()
                flash("👍 Message status updated.")
            case 0:
                db.session.rollback()
                flash("⛔️ Message not found.")
            case _:
                db.session.rollback()
                current_app.logger.error(
                    "Multiple messages would have been updated. "
                    f"Message.public_id={public_id} User.id={user.id}"
                )
                flash("⛔️ Internal server error. Message not updated.")
        return redirect(url_for("message", public_id=public_id))

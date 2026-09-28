import base64
import binascii
import json
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from typing import Any, Mapping

from flask import current_app, session
from sqlalchemy.exc import IntegrityError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import decode_credential_public_key
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from hushline.config import (
    ConfigParseError,
    WebAuthnRelyingPartyConfig,
    validate_webauthn_relying_party_config,
)
from hushline.db import db
from hushline.model import User, WebAuthnChallenge, WebAuthnCredential, WebAuthnUserHandle

WEBAUTHN_SESSION_BINDING_KEY = "webauthn_session_binding"
APPLICATION_SECRET_MIN_LENGTH = 32
SESSION_BINDING_MIN_LENGTH = 32
SESSION_BINDING_MAX_LENGTH = 512
SUPPORTED_ALGORITHMS = (
    COSEAlgorithmIdentifier.EDDSA,
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
)
VALID_TRANSPORTS = frozenset(("ble", "hybrid", "internal", "nfc", "smart-card", "usb"))


class WebAuthnPurpose(StrEnum):
    REGISTRATION = "registration"
    AUTHENTICATION = "authentication"
    RECOVERY = "recovery"


class WebAuthnServiceError(Exception):
    """Base error safe for ceremony callers to handle without exposing verifier details."""


class WebAuthnConfigurationError(WebAuthnServiceError):
    pass


class WebAuthnRateLimitError(WebAuthnServiceError):
    pass


class WebAuthnChallengeError(WebAuthnServiceError):
    pass


class WebAuthnVerificationError(WebAuthnServiceError):
    pass


def current_webauthn_session_binding() -> str:
    binding = session.get(WEBAUTHN_SESSION_BINDING_KEY)
    if not isinstance(binding, str) or len(binding) < SESSION_BINDING_MIN_LENGTH:
        binding = secrets.token_urlsafe(48)
        session[WEBAUTHN_SESSION_BINDING_KEY] = binding
    return binding


def _now() -> datetime:
    return datetime.now(UTC)


def _service_secret() -> bytes:
    secret = (
        current_app.config.get("SECRET_KEY")
        or current_app.config.get("SESSION_FERNET_KEY")
        or current_app.config.get("ENCRYPTION_KEY")
    )
    if not isinstance(secret, str) or len(secret) < APPLICATION_SECRET_MIN_LENGTH:
        raise WebAuthnConfigurationError("WebAuthn requires an application secret")
    return secret.encode("utf-8")


def _session_binding_hash(binding: str) -> bytes:
    if not isinstance(binding, str) or not (
        SESSION_BINDING_MIN_LENGTH <= len(binding) <= SESSION_BINDING_MAX_LENGTH
    ):
        raise WebAuthnChallengeError("Invalid ceremony session")
    return hmac_new(_service_secret(), binding.encode("utf-8"), sha256).digest()


def _challenge_hash(challenge: bytes) -> bytes:
    return sha256(challenge).digest()


def _advisory_lock(scope: str, value: bytes) -> None:
    if db.session.get_bind().dialect.name != "postgresql":
        return
    lock_digest = sha256(scope.encode("ascii") + b"\0" + value).digest()
    lock_key = int.from_bytes(lock_digest[:8], byteorder="big", signed=True)
    db.session.execute(db.select(db.func.pg_advisory_xact_lock(lock_key)))


def _options_dict(options: Any) -> dict[str, Any]:
    value = json.loads(options_to_json(options))
    if not isinstance(value, dict):
        raise WebAuthnVerificationError("Unable to create WebAuthn options")
    return value


def _decode_base64url(value: object, *, field: str, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > max_bytes * 2:
        raise WebAuthnVerificationError(f"Malformed {field}")
    try:
        encoded = value.encode("ascii")
        decoded = base64.b64decode(
            encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        )
    except (UnicodeEncodeError, binascii.Error):
        raise WebAuthnVerificationError(f"Malformed {field}") from None
    if len(decoded) > max_bytes:
        raise WebAuthnVerificationError(f"Malformed {field}")
    return decoded


def _bounded_payload(response: str | Mapping[str, Any]) -> dict[str, Any]:
    max_bytes = int(current_app.config.get("WEBAUTHN_MAX_RESPONSE_BYTES", 65536))
    try:
        if isinstance(response, str):
            if len(response.encode("utf-8")) > max_bytes:
                raise WebAuthnVerificationError("WebAuthn response is too large")
            parsed = json.loads(response)
        elif isinstance(response, Mapping):
            parsed = dict(response)
            if len(json.dumps(parsed, separators=(",", ":")).encode("utf-8")) > max_bytes:
                raise WebAuthnVerificationError("WebAuthn response is too large")
        else:
            raise WebAuthnVerificationError("Malformed WebAuthn response")
    except (RecursionError, TypeError, ValueError):
        raise WebAuthnVerificationError("Malformed WebAuthn response") from None
    if not isinstance(parsed, dict):
        raise WebAuthnVerificationError("Malformed WebAuthn response")
    return parsed


def _response_challenge(payload: Mapping[str, Any]) -> bytes:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        raise WebAuthnVerificationError("Malformed WebAuthn response")
    client_data_bytes = _decode_base64url(
        response.get("clientDataJSON"), field="client data", max_bytes=4096
    )
    try:
        client_data = json.loads(client_data_bytes)
    except (RecursionError, UnicodeDecodeError, ValueError):
        raise WebAuthnVerificationError("Malformed client data") from None
    if not isinstance(client_data, dict):
        raise WebAuthnVerificationError("Malformed client data")
    return _decode_base64url(client_data.get("challenge"), field="challenge", max_bytes=128)


def _response_credential_id(payload: Mapping[str, Any]) -> bytes:
    raw_id = _decode_base64url(
        payload.get("rawId"),
        field="credential ID",
        max_bytes=WebAuthnCredential.MAX_CREDENTIAL_ID_LENGTH,
    )
    if not raw_id:
        raise WebAuthnVerificationError("Malformed credential ID")
    return raw_id


def _response_user_handle(payload: Mapping[str, Any]) -> bytes | None:
    response = payload.get("response")
    if not isinstance(response, Mapping) or response.get("userHandle") is None:
        return None
    return _decode_base64url(
        response.get("userHandle"),
        field="user handle",
        max_bytes=WebAuthnUserHandle.HANDLE_LENGTH,
    )


def _registration_transports(payload: Mapping[str, Any]) -> list[str]:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        return []
    transports = response.get("transports", [])
    if not isinstance(transports, list) or len(transports) > len(VALID_TRANSPORTS):
        raise WebAuthnVerificationError("Malformed authenticator transports")
    if any(not isinstance(item, str) or item not in VALID_TRANSPORTS for item in transports):
        raise WebAuthnVerificationError("Malformed authenticator transports")
    return sorted(set(transports))


def _persist_authentication_result(
    credential: WebAuthnCredential,
    *,
    expected_sign_count: int,
    new_sign_count: int,
    device_type: str,
    backed_up: bool,
) -> None:
    conditions = [
        WebAuthnCredential.id == credential.id,
        WebAuthnCredential.disabled_at.is_(None),
    ]
    # Authenticators that always return zero do not support clone detection. For
    # every stateful counter transition, compare-and-swap prevents two concurrent
    # assertions made from the same stored counter from both succeeding.
    if expected_sign_count != 0 or new_sign_count != 0:
        conditions.append(WebAuthnCredential.sign_count == expected_sign_count)
    updated_id = db.session.scalar(
        db.update(WebAuthnCredential)
        .where(*conditions)
        .values(
            sign_count=new_sign_count,
            device_type=device_type,
            backed_up=backed_up,
            last_used_at=_now(),
        )
        .returning(WebAuthnCredential.id)
    )
    if updated_id is None:
        db.session.rollback()
        raise WebAuthnVerificationError("WebAuthn credential state changed concurrently")
    db.session.commit()


class WebAuthnChallengeService:
    @staticmethod
    def issue(*, user_id: int, purpose: WebAuthnPurpose, session_binding: str) -> bytes:
        session_hash = _session_binding_hash(session_binding)
        now = _now()
        window = timedelta(
            seconds=int(current_app.config.get("WEBAUTHN_RATE_LIMIT_WINDOW_SECONDS", 600))
        )
        _advisory_lock("webauthn-account", str(user_id).encode("ascii"))
        _advisory_lock("webauthn-session", session_hash)

        account_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.user_id == user_id,
                WebAuthnChallenge.purpose == purpose.value,
                WebAuthnChallenge.created_at >= now - window,
            )
        )
        session_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.session_binding_hash == session_hash,
                WebAuthnChallenge.purpose == purpose.value,
                WebAuthnChallenge.created_at >= now - window,
            )
        )
        if int(account_count or 0) >= int(
            current_app.config.get("WEBAUTHN_RATE_LIMIT_ACCOUNT_MAX", 10)
        ) or int(session_count or 0) >= int(
            current_app.config.get("WEBAUTHN_RATE_LIMIT_SESSION_MAX", 10)
        ):
            db.session.rollback()
            raise WebAuthnRateLimitError("Too many WebAuthn ceremonies")

        challenge = secrets.token_bytes(64)
        ttl = timedelta(seconds=int(current_app.config.get("WEBAUTHN_CHALLENGE_TTL_SECONDS", 300)))
        db.session.add(
            WebAuthnChallenge(
                user_id=user_id,
                purpose=purpose.value,
                challenge_hash=_challenge_hash(challenge),
                session_binding_hash=session_hash,
                created_at=now,
                expires_at=now + ttl,
            )
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise WebAuthnChallengeError("Unable to create WebAuthn challenge") from None
        return challenge

    @staticmethod
    def consume(
        *, challenge: bytes, user_id: int, purpose: WebAuthnPurpose, session_binding: str
    ) -> None:
        now = _now()
        consumed_id = db.session.scalar(
            db.update(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.challenge_hash == _challenge_hash(challenge),
                WebAuthnChallenge.user_id == user_id,
                WebAuthnChallenge.purpose == purpose.value,
                WebAuthnChallenge.session_binding_hash == _session_binding_hash(session_binding),
                WebAuthnChallenge.expires_at > now,
                WebAuthnChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
            .returning(WebAuthnChallenge.id)
        )
        db.session.commit()
        if consumed_id is None:
            raise WebAuthnChallengeError("Invalid or expired WebAuthn challenge")


class WebAuthnCeremonyService:
    @staticmethod
    def _rp_config() -> WebAuthnRelyingPartyConfig:
        try:
            config = validate_webauthn_relying_party_config(current_app.config, required=True)
        except ConfigParseError:
            raise WebAuthnConfigurationError("WebAuthn relying party is not configured") from None
        if config is None:
            raise WebAuthnConfigurationError("WebAuthn relying party is not configured")
        return config

    @classmethod
    def begin_registration(
        cls,
        *,
        user: User,
        username: str,
        display_name: str | None,
        session_binding: str,
    ) -> dict[str, Any]:
        config = cls._rp_config()
        _advisory_lock("webauthn-account", str(user.id).encode("ascii"))
        user_handle = db.session.scalar(
            db.select(WebAuthnUserHandle).where(WebAuthnUserHandle.user_id == user.id)
        )
        if user_handle is None:
            user_handle = WebAuthnUserHandle(user=user)
            db.session.add(user_handle)
            db.session.flush()

        challenge = WebAuthnChallengeService.issue(
            user_id=user.id,
            purpose=WebAuthnPurpose.REGISTRATION,
            session_binding=session_binding,
        )
        credentials = [
            PublicKeyCredentialDescriptor(id=credential.credential_id)
            for credential in user.webauthn_credentials
            if credential.disabled_at is None
        ]
        options = generate_registration_options(
            rp_id=config.rp_id,
            rp_name=config.rp_name,
            user_id=user_handle.handle,
            user_name=username,
            user_display_name=display_name or username,
            challenge=challenge,
            timeout=int(current_app.config.get("WEBAUTHN_CHALLENGE_TTL_SECONDS", 300)) * 1000,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.DISCOURAGED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=credentials,
            supported_pub_key_algs=list(SUPPORTED_ALGORITHMS),
        )
        return _options_dict(options)

    @classmethod
    def finish_registration(
        cls,
        *,
        user: User,
        session_binding: str,
        response: str | Mapping[str, Any],
        name: str | None = None,
    ) -> WebAuthnCredential:
        config = cls._rp_config()
        payload = _bounded_payload(response)
        challenge = _response_challenge(payload)
        WebAuthnChallengeService.consume(
            challenge=challenge,
            user_id=user.id,
            purpose=WebAuthnPurpose.REGISTRATION,
            session_binding=session_binding,
        )
        transports = _registration_transports(payload)
        _advisory_lock("webauthn-account", str(user.id).encode("ascii"))
        active_count = db.session.scalar(
            db.select(db.func.count())
            .select_from(WebAuthnCredential)
            .where(
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
        )
        if int(active_count or 0) >= int(
            current_app.config.get("WEBAUTHN_MAX_CREDENTIALS_PER_USER", 20)
        ):
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn credential limit reached")
        try:
            verified = verify_registration_response(
                credential=payload,
                expected_challenge=challenge,
                expected_rp_id=config.rp_id,
                expected_origin=config.origin,
                require_user_presence=True,
                require_user_verification=True,
                supported_pub_key_algs=list(SUPPORTED_ALGORITHMS),
            )
            decoded_key = decode_credential_public_key(verified.credential_public_key)
        except (TypeError, ValueError, WebAuthnException):
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn registration could not be verified") from None
        if (
            not verified.credential_id
            or len(verified.credential_id) > WebAuthnCredential.MAX_CREDENTIAL_ID_LENGTH
            or len(verified.credential_public_key) > WebAuthnCredential.MAX_PUBLIC_KEY_LENGTH
            or decoded_key.alg not in SUPPORTED_ALGORITHMS
        ):
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn credential is unsupported")

        cleaned_name = name.strip() if isinstance(name, str) else None
        if cleaned_name and len(cleaned_name) > WebAuthnCredential.MAX_NAME_LENGTH:
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn credential name is too long")
        credential = WebAuthnCredential(
            user_id=user.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            algorithm=int(decoded_key.alg),
            sign_count=verified.sign_count,
            transports=transports,
            device_type=verified.credential_device_type.value,
            backed_up=verified.credential_backed_up,
            name=cleaned_name or None,
        )
        db.session.add(credential)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn credential is already registered") from None
        return credential

    @classmethod
    def begin_authentication(
        cls,
        *,
        user: User,
        session_binding: str,
        purpose: WebAuthnPurpose = WebAuthnPurpose.AUTHENTICATION,
    ) -> dict[str, Any]:
        if purpose not in {WebAuthnPurpose.AUTHENTICATION, WebAuthnPurpose.RECOVERY}:
            raise WebAuthnChallengeError("Invalid WebAuthn authentication purpose")
        config = cls._rp_config()
        active_credentials = [
            credential for credential in user.webauthn_credentials if credential.disabled_at is None
        ]
        if not active_credentials:
            raise WebAuthnVerificationError("No active WebAuthn credentials")
        challenge = WebAuthnChallengeService.issue(
            user_id=user.id,
            purpose=purpose,
            session_binding=session_binding,
        )
        options = generate_authentication_options(
            rp_id=config.rp_id,
            challenge=challenge,
            timeout=int(current_app.config.get("WEBAUTHN_CHALLENGE_TTL_SECONDS", 300)) * 1000,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=credential.credential_id)
                for credential in active_credentials
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return _options_dict(options)

    @classmethod
    def finish_authentication(
        cls,
        *,
        user: User,
        session_binding: str,
        response: str | Mapping[str, Any],
        purpose: WebAuthnPurpose = WebAuthnPurpose.AUTHENTICATION,
    ) -> WebAuthnCredential:
        if purpose not in {WebAuthnPurpose.AUTHENTICATION, WebAuthnPurpose.RECOVERY}:
            raise WebAuthnChallengeError("Invalid WebAuthn authentication purpose")
        config = cls._rp_config()
        payload = _bounded_payload(response)
        challenge = _response_challenge(payload)
        WebAuthnChallengeService.consume(
            challenge=challenge,
            user_id=user.id,
            purpose=purpose,
            session_binding=session_binding,
        )
        credential_id = _response_credential_id(payload)

        credential = db.session.scalars(
            db.select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id == credential_id,
                WebAuthnCredential.user_id == user.id,
                WebAuthnCredential.disabled_at.is_(None),
            )
        ).one_or_none()
        if credential is None:
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn authentication could not be verified")
        user_handle = _response_user_handle(payload)
        stored_handle = user.webauthn_user_handle
        if user_handle is not None and (
            stored_handle is None or not compare_digest(user_handle, stored_handle.handle)
        ):
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn authentication could not be verified")
        try:
            verified = verify_authentication_response(
                credential=payload,
                expected_challenge=challenge,
                expected_rp_id=config.rp_id,
                expected_origin=config.origin,
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
                require_user_verification=True,
            )
        except (TypeError, ValueError, WebAuthnException):
            db.session.rollback()
            raise WebAuthnVerificationError(
                "WebAuthn authentication could not be verified"
            ) from None
        if not compare_digest(verified.credential_id, credential.credential_id):
            db.session.rollback()
            raise WebAuthnVerificationError("WebAuthn authentication could not be verified")

        _persist_authentication_result(
            credential,
            expected_sign_count=credential.sign_count,
            new_sign_count=verified.new_sign_count,
            device_type=verified.credential_device_type.value,
            backed_up=verified.credential_backed_up,
        )
        db.session.refresh(credential)
        return credential

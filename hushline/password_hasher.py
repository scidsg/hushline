import re
from typing import Final

from flask import current_app, has_app_context
from passlib.hash import scrypt
from werkzeug.security import check_password_hash

LEGACY_PASSLIB_SCRYPT_PREFIX: Final = "$scrypt$"
PASSWORD_HASH_VERIFICATION_EVENT: Final = "password_hash_verification"
PASSWORD_HASH_COUNTER_EVENT: Final = "password_hash_counter"
PASSWORD_HASH_VERIFICATION_SUCCESS_COUNTER: Final = "password_hash_verification_success_total"
PASSWORD_HASH_VERIFICATION_FAILURE_COUNTER: Final = "password_hash_verification_failure_total"
PASSWORD_HASH_WRITE_COUNTER: Final = "password_hash_write_total"
PASSWORD_HASH_REHASH_ON_AUTH_SUCCESS_COUNTER: Final = "password_hash_rehash_on_auth_success_total"
PASSWORD_HASH_REHASH_ON_AUTH_FAILURE_COUNTER: Final = "password_hash_rehash_on_auth_failure_total"
UNKNOWN_PASSWORD_HASH_PREFIX: Final = "unknown"
_NATIVE_HASH_PREFIX_RE: Final = re.compile(r"^(?P<prefix>[a-z0-9_-]{1,32}):")
_DOLLAR_HASH_PREFIX_RE: Final = re.compile(r"^\$(?P<prefix>[a-z0-9_-]{1,32})\$")


def hash_password(plaintext_password: str) -> str:
    hashed_password = scrypt.hash(plaintext_password)
    emit_password_hash_write_telemetry(hashed_password)
    return hashed_password


def verify_password(plaintext_password: str, stored_hash: str | None) -> bool:
    stored_hash_value = stored_hash or ""

    try:
        verified = _dispatch_password_verification(plaintext_password, stored_hash_value)
    except ValueError:
        verified = False

    _emit_password_verification_telemetry(stored_hash_value, verified)
    return verified


def verify_primary_password_hash(plaintext_password: str, stored_hash: str) -> bool:
    native_prefix = _get_native_hash_prefix(stored_hash)
    if native_prefix == "scrypt:":
        return _verify_primary_scrypt_password_hash(plaintext_password, stored_hash)
    return False


def get_password_hash_format(stored_hash: str | None) -> str:
    stored_hash_value = stored_hash or ""
    if stored_hash_value.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX):
        return "passlib_scrypt"

    native_prefix = _get_native_hash_prefix(stored_hash_value)
    if native_prefix is not None:
        return f"native_{native_prefix.removesuffix(':')}"

    return UNKNOWN_PASSWORD_HASH_PREFIX


def get_password_hash_prefix(stored_hash: str | None) -> str:
    stored_hash_value = stored_hash or ""
    if stored_hash_value.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX):
        return LEGACY_PASSLIB_SCRYPT_PREFIX

    native_prefix = _get_native_hash_prefix(stored_hash_value)
    if native_prefix is not None:
        return native_prefix

    dollar_match = _DOLLAR_HASH_PREFIX_RE.match(stored_hash_value)
    if dollar_match is not None:
        return f"${dollar_match.group('prefix')}$"

    return UNKNOWN_PASSWORD_HASH_PREFIX


def _dispatch_password_verification(plaintext_password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(LEGACY_PASSLIB_SCRYPT_PREFIX):
        return scrypt.verify(plaintext_password, stored_hash)

    if _get_native_hash_prefix(stored_hash) is not None:
        return verify_primary_password_hash(plaintext_password, stored_hash)

    return False


def _verify_primary_scrypt_password_hash(_plaintext_password: str, _stored_hash: str) -> bool:
    return check_password_hash(_stored_hash, _plaintext_password)


def emit_password_hash_write_telemetry(stored_hash: str | None) -> None:
    _emit_password_hash_counter(
        PASSWORD_HASH_WRITE_COUNTER,
        hash_format=get_password_hash_format(stored_hash),
    )


def emit_password_rehash_on_auth_telemetry(stored_hash: str | None, *, success: bool) -> None:
    counter_name = (
        PASSWORD_HASH_REHASH_ON_AUTH_SUCCESS_COUNTER
        if success
        else PASSWORD_HASH_REHASH_ON_AUTH_FAILURE_COUNTER
    )
    _emit_password_hash_counter(
        counter_name,
        hash_format=get_password_hash_format(stored_hash),
    )


def _get_native_hash_prefix(stored_hash: str) -> str | None:
    native_match = _NATIVE_HASH_PREFIX_RE.match(stored_hash)
    if native_match is None:
        return None
    return f"{native_match.group('prefix')}:"


def _emit_password_verification_telemetry(stored_hash: str, verified: bool) -> None:
    if not has_app_context():
        return

    current_app.logger.info(
        "Password hash verification",
        extra={
            "event": PASSWORD_HASH_VERIFICATION_EVENT,
            "verification_result": "success" if verified else "failure",
            "hash_format": get_password_hash_format(stored_hash),
            "hash_prefix": get_password_hash_prefix(stored_hash),
        },
    )

    if verified:
        _emit_password_hash_counter(
            PASSWORD_HASH_VERIFICATION_SUCCESS_COUNTER,
            hash_format=get_password_hash_format(stored_hash),
        )
        return

    _emit_password_hash_counter(
        PASSWORD_HASH_VERIFICATION_FAILURE_COUNTER,
        hash_prefix=get_password_hash_prefix(stored_hash),
    )


def _emit_password_hash_counter(counter_name: str, **labels: str) -> None:
    if not has_app_context():
        return

    current_app.logger.info(
        "Password hash counter",
        extra={
            "event": PASSWORD_HASH_COUNTER_EVENT,
            "counter_name": counter_name,
            "count": 1,
            **labels,
        },
    )

import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum, unique
from ipaddress import ip_address
from json import JSONDecodeError
from typing import Any, Mapping, Optional, Self
from urllib.parse import urlsplit

import bleach
from markupsafe import Markup

from hushline.external_urls import normalize_public_base_url
from hushline.utils import if_not_none, parse_bool

_STRING_CFG_PREFIX = "HL_CFG_"
_JSON_CFG_PREFIX = "HL_CFG_JSON_"
PASSWORD_HASH_REHASH_ON_AUTH_ENABLED = "PASSWORD_HASH_REHASH_ON_AUTH_ENABLED"  # noqa: S105
PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT = "PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT"  # noqa: S105
ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL = "ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL"
ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED = "ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED"
ENCRYPTED_FIELD_LEGACY_READS_ENABLED = "ENCRYPTED_FIELD_LEGACY_READS_ENABLED"
ENCRYPTED_FIELD_WRITE_FORMAT = "ENCRYPTED_FIELD_WRITE_FORMAT"
SPLASH_SCREEN_DURATION_MS = "SPLASH_SCREEN_DURATION_MS"
WEBAUTHN_ORIGIN = "WEBAUTHN_ORIGIN"
WEBAUTHN_RP_ID = "WEBAUTHN_RP_ID"
WEBAUTHN_HOSTNAME_MAX_LENGTH = 253
WEBAUTHN_RP_NAME_MAX_LENGTH = 100
WEBAUTHN_MIN_CREDENTIALS_PER_USER = 2


class ConfigParseError(Exception):
    pass


@dataclass(frozen=True)
class WebAuthnRelyingPartyConfig:
    rp_id: str
    origin: str
    rp_name: str


def validate_webauthn_relying_party_config(
    config: Mapping[str, Any], *, required: bool
) -> WebAuthnRelyingPartyConfig | None:
    """Validate WebAuthn trust roots without consulting the current request."""
    raw_rp_id = config.get(WEBAUTHN_RP_ID)
    raw_origin = config.get(WEBAUTHN_ORIGIN)
    if raw_rp_id is None and raw_origin is None:
        if required:
            raise ConfigParseError(
                "WEBAUTHN_RP_ID and WEBAUTHN_ORIGIN must be explicitly configured"
            )
        return None
    if not isinstance(raw_rp_id, str) or not raw_rp_id.strip():
        raise ConfigParseError("WEBAUTHN_RP_ID must be a non-empty hostname")
    if not isinstance(raw_origin, str) or not raw_origin.strip():
        raise ConfigParseError("WEBAUTHN_ORIGIN must be an explicit origin")

    rp_id = raw_rp_id.strip().lower()
    if len(rp_id) > WEBAUTHN_HOSTNAME_MAX_LENGTH or any(char in rp_id for char in "/:@?#"):
        raise ConfigParseError("WEBAUTHN_RP_ID must be a hostname without a scheme or port")
    try:
        rp_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ConfigParseError("WEBAUTHN_RP_ID must use its ASCII IDNA form") from exc
    try:
        rp_ip = ip_address(rp_id)
    except ValueError:
        rp_ip = None
    if rp_ip is None and any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in rp_id.split(".")
    ):
        raise ConfigParseError("WEBAUTHN_RP_ID must be a valid hostname")

    origin = raw_origin.strip()
    parsed = urlsplit(origin)
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigParseError("WEBAUTHN_ORIGIN contains an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigParseError("WEBAUTHN_ORIGIN must contain only scheme, hostname, and port")
    origin_host = parsed.hostname.lower()
    try:
        origin_host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ConfigParseError("WEBAUTHN_ORIGIN must use an ASCII IDNA hostname") from exc
    if origin_host != rp_id and (rp_ip is not None or not origin_host.endswith(f".{rp_id}")):
        raise ConfigParseError("WEBAUTHN_RP_ID must equal or be a parent of the origin hostname")

    try:
        parsed_ip = ip_address(origin_host)
    except ValueError:
        parsed_ip = None
    if len(origin_host) > WEBAUTHN_HOSTNAME_MAX_LENGTH or (
        parsed_ip is None
        and any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in origin_host.split(".")
        )
    ):
        raise ConfigParseError("WEBAUTHN_ORIGIN must contain a valid hostname")
    is_local = origin_host == "localhost" or (parsed_ip is not None and parsed_ip.is_loopback)
    is_onion = origin_host.endswith(".onion")
    if parsed.scheme != "https" and not (is_local or is_onion):
        raise ConfigParseError("WEBAUTHN_ORIGIN must use HTTPS except for localhost or onion sites")

    rp_name = config.get("WEBAUTHN_RP_NAME", "Hush Line")
    if (
        not isinstance(rp_name, str)
        or not rp_name.strip()
        or len(rp_name) > WEBAUTHN_RP_NAME_MAX_LENGTH
    ):
        raise ConfigParseError("WEBAUTHN_RP_NAME must be between 1 and 100 characters")
    return WebAuthnRelyingPartyConfig(
        rp_id=rp_id,
        origin=origin,
        rp_name=rp_name.strip(),
    )


@unique
class AliasMode(Enum):
    ALWAYS = "always"
    PREMIUM = "premium"
    NEVER = "never"

    @classmethod
    def parse(cls, string: str) -> Self:
        for var in cls:
            if var.value == string:
                return var
        raise ConfigParseError(f"Not a valid value for {cls.__name__}: {string!r}")


@unique
class FieldsMode(Enum):
    ALWAYS = "always"
    PREMIUM = "premium"

    @classmethod
    def parse(cls, string: str) -> Self:
        for var in cls:
            if var.value == string:
                return var
        raise ConfigParseError(f"Not a valid value for {cls.__name__}: {string!r}")


@unique
class EncryptedFieldWriteFormat(Enum):
    LEGACY_FERNET = "legacy-fernet"
    ENVELOPE_FERNET = "envelope-fernet"
    ENVELOPE_AES_GCM = "envelope-aes-gcm"

    @classmethod
    def parse(cls, string: str) -> Self:
        for var in cls:
            if var.value == string:
                return var
        raise ConfigParseError(f"Not a valid value for {cls.__name__}: {string!r}")


def load_config(env: Optional[Mapping[str, str]] = None) -> Mapping[str, Any]:
    if env is None:
        env = os.environ

    config: dict[str, Any] = {}
    for func in [
        _load_flask,
        _load_sqlalchemy,
        _load_smtp,
        _load_stripe,
        _load_blob_storage,
        _load_hushline_misc,
        _load_webauthn,
        # load strings and JSON last as overrides
        _load_strings,
        _load_json,
    ]:
        config |= func(env)

    validate_webauthn_relying_party_config(config, required=False)
    return config


def _load_webauthn(env: Mapping[str, str]) -> Mapping[str, Any]:
    data: dict[str, Any] = {}
    for key in (WEBAUTHN_RP_ID, WEBAUTHN_ORIGIN, "WEBAUTHN_RP_NAME"):
        if key in env:
            data[key] = env[key]

    integer_defaults = {
        "WEBAUTHN_CHALLENGE_TTL_SECONDS": 300,
        "WEBAUTHN_RATE_LIMIT_WINDOW_SECONDS": 600,
        "WEBAUTHN_RATE_LIMIT_ACCOUNT_MAX": 10,
        "WEBAUTHN_RATE_LIMIT_SESSION_MAX": 10,
        "WEBAUTHN_MAX_RESPONSE_BYTES": 65536,
        "WEBAUTHN_MAX_CREDENTIALS_PER_USER": 20,
        "WEBAUTHN_MAX_REVOKED_CREDENTIALS_PER_USER": 20,
        "WEBAUTHN_REVOKED_CREDENTIAL_RETENTION_DAYS": 30,
    }
    for key, default in integer_defaults.items():
        try:
            value = int(env.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ConfigParseError(f"{key} must be an integer") from exc
        if value <= 0:
            raise ConfigParseError(f"{key} must be greater than zero")
        if key == "WEBAUTHN_MAX_CREDENTIALS_PER_USER" and value < WEBAUTHN_MIN_CREDENTIALS_PER_USER:
            raise ConfigParseError(
                "WEBAUTHN_MAX_CREDENTIALS_PER_USER must allow at least two credentials"
            )
        data[key] = value
    return data


def _load_flask(env: Mapping[str, str]) -> Mapping[str, Any]:
    data = {
        "SESSION_COOKIE_NAME": "__HOST-session",
        "SESSION_COOKIE_SECURE": True,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Strict",
        "PERMANENT_SESSION_LIFETIME": timedelta(minutes=30),
    }

    # Handle the tips domain for profile verification
    if server_name := env.get("SERVER_NAME"):
        data["SERVER_NAME"] = server_name
    if preferred_scheme := env.get("PREFERRED_URL_SCHEME"):
        preferred_scheme = preferred_scheme.lower()
        if preferred_scheme not in {"http", "https"}:
            raise ConfigParseError(
                "PREFERRED_URL_SCHEME must be 'http' or 'https', " f"got {preferred_scheme!r}"
            )
        data["PREFERRED_URL_SCHEME"] = preferred_scheme
    else:
        data["PREFERRED_URL_SCHEME"] = "https" if server_name else "http"
    if public_base_url := env.get("PUBLIC_BASE_URL"):
        try:
            data["PUBLIC_BASE_URL"] = normalize_public_base_url(public_base_url)
        except ValueError as exc:
            raise ConfigParseError(str(exc)) from exc

    for key in ["FLASK_ENV", "SECRET_KEY"]:
        if val := env.get(key):
            data[key] = val

    return data


def _load_sqlalchemy(env: Mapping[str, str]) -> Mapping[str, Any]:
    data: dict[str, Any] = {}

    if db_uri := env.get("SQLALCHEMY_DATABASE_URI"):
        # if it's a Postgres URI, replace the scheme with `postgresql+psycopg`
        # because we're using the psycopg driver
        if db_uri.startswith("postgresql://"):
            db_uri = db_uri.replace("postgresql://", "postgresql+psycopg://", 1)
        data["SQLALCHEMY_DATABASE_URI"] = db_uri

    data["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    return data


def clean_html(html_str: str) -> Markup:
    return Markup(
        bleach.clean(
            html_str, tags=["p", "span", "b", "strong", "i", "em", "a"], attributes={"a": ["href"]}
        )
    )


def _load_smtp(env: Mapping[str, str]) -> Mapping[str, Any]:
    data: dict[str, Any] = {}

    for key in [
        "NOTIFICATIONS_ADDRESS",
        "NOTIFICATIONS_REPLY_TO",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_SERVER",
    ]:
        if val := env.get(key):
            data[key] = val

    data["SMTP_PORT"] = if_not_none(env.get("SMTP_PORT"), int, allow_falsey=False)
    data["SMTP_ENCRYPTION"] = env.get("SMTP_ENCRYPTION", "StartTLS")
    data["SMTP_FORWARDING_MESSAGE_HTML"] = if_not_none(
        env.get("SMTP_FORWARDING_MESSAGE_HTML"), clean_html, allow_falsey=False
    )

    return data


def _load_hushline_misc(env: Mapping[str, str]) -> Mapping[str, Any]:
    data: dict[str, Any] = {}

    # these are required by the Flask app but not by the Stripe worker
    # so we have to allow for them to be missing
    if key := env.get("ENCRYPTION_KEY"):
        data["ENCRYPTION_KEY"] = key
    if key := env.get("SESSION_FERNET_KEY"):
        data["SESSION_FERNET_KEY"] = key

    if onion := env.get("ONION_HOSTNAME"):
        data["ONION_HOSTNAME"] = onion

    data[SPLASH_SCREEN_DURATION_MS] = if_not_none(
        env.get(SPLASH_SCREEN_DURATION_MS), int, allow_falsey=False
    )
    if data[SPLASH_SCREEN_DURATION_MS] is None:
        data[SPLASH_SCREEN_DURATION_MS] = 2000

    bool_configs = [
        ("DIRECTORY_VERIFIED_TAB_ENABLED", True),
        (ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED, False),
        (ENCRYPTED_FIELD_LEGACY_READS_ENABLED, True),
        ("FILE_UPLOADS_ENABLED", False),
        (PASSWORD_HASH_REHASH_ON_AUTH_ENABLED, False),
        (PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT, False),
        ("REGISTRATION_SETTINGS_ENABLED", True),
        ("USER_VERIFICATION_ENABLED", False),
    ]
    for key, default in bool_configs:
        if value := env.get(key):
            data[key] = parse_bool(value)
        else:
            data[key] = default

    if alias_str := env.get("ALIAS_MODE"):
        data["ALIAS_MODE"] = AliasMode.parse(alias_str)
    else:
        data["ALIAS_MODE"] = AliasMode.ALWAYS

    if fields_str := env.get("FIELDS_MODE"):
        data["FIELDS_MODE"] = FieldsMode.parse(fields_str)
    else:
        data["FIELDS_MODE"] = FieldsMode.ALWAYS

    if encrypted_field_write_format := env.get(ENCRYPTED_FIELD_WRITE_FORMAT):
        data[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.parse(
            encrypted_field_write_format
        )
    else:
        data[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET

    if ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL in env:
        data[ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL] = env[ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL]
    if data[ENCRYPTED_FIELD_WRITE_FORMAT] == EncryptedFieldWriteFormat.ENVELOPE_AES_GCM:
        if not data[ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED]:
            raise ConfigParseError(
                "ENCRYPTED_FIELD_WRITE_FORMAT='envelope-aes-gcm' requires "
                "ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED='true'"
            )
        approval = data.get(ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL)
        if not isinstance(approval, str) or not approval.strip():
            raise ConfigParseError(
                "ENCRYPTED_FIELD_WRITE_FORMAT='envelope-aes-gcm' requires "
                "non-empty ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL"
            )

    return data


def _load_stripe(env: Mapping[str, str]) -> Mapping[str, Any]:
    data = {}

    for key in ["STRIPE_PUBLISHABLE_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"]:
        if (value := env.get(key)) and value != "":
            data[key] = value

    return data


def _load_blob_storage(env: Mapping[str, str]) -> Mapping[str, Any]:
    data = {}

    for k, v in env.items():
        if k.startswith("BLOB_STORAGE"):
            data[k] = v

    return data


def _load_strings(env: Mapping[str, str]) -> Mapping[str, Any]:
    return {
        k[len(_STRING_CFG_PREFIX) :]: v for k, v in env.items() if k.startswith(_STRING_CFG_PREFIX)
    }


def _load_json(env: Mapping[str, str]) -> Mapping[str, Any]:
    data = {}

    for k, v in env.items():
        if not k.startswith(_JSON_CFG_PREFIX):
            continue

        try:
            data[k[len(_JSON_CFG_PREFIX) :]] = json.loads(v)
        except JSONDecodeError:
            raise ConfigParseError(f"Env var {k!r} could not be parsed as JSON")

    return data

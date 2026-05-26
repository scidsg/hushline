import binascii
import json
import os
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from flask import current_app
from pysequoia import Cert, encrypt

with open(Path(__file__).parent / "files" / "diceware.txt") as f:
    DICEWARE_WORDS = [x.strip() for x in f]
SLUG_DICEWARE_WORDS = [word for word in DICEWARE_WORDS if "-" not in word]

# https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#scrypt
SCRYPT_LENGTH = 32  # The desired length of the derived key in bytes.
_SCRYPT_PARAMS = {
    "n": 2**14,  # CPU/Memory cost parameter. It must be larger than 1 and be a power of 2.
    "r": 8,  # Block size parameter.
    "p": 1,  # Parallelization parameter.
}
ENCRYPTED_FIELD_ENVELOPE_PREFIX = "hlfield:"
ENCRYPTED_FIELD_ENVELOPE_VERSION = 1
ENCRYPTED_FIELD_ENVELOPE_ALGORITHM = "fernet"
ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION = 2
ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM = "aes-256-gcm"
ENCRYPTED_FIELD_AAD_SCHEMA = "hushline.encrypted-field.aad.v1"
ENCRYPTED_FIELD_AEAD_KEY_INFO = b"hushline:encrypted-field:aes-256-gcm:v2"
ENCRYPTED_FIELD_MUTABLE_AAD_NAMES = frozenset(
    {
        "bio",
        "display_name",
        "email",
        "field_value",
        "message",
        "message_text",
        "pgp_key",
        "profile_text",
        "smtp_password",
        "smtp_server",
        "smtp_username",
        "username",
    }
)


@dataclass(frozen=True)
class EncryptedFieldEnvelope:
    version: int
    algorithm: str
    ciphertext: str


@dataclass(frozen=True)
class EncryptedFieldContract:
    id: str
    domain: str
    table: str
    column: str
    aad_fields: tuple[str, ...]


@dataclass(frozen=True)
class EncryptedFieldAEADEnvelope:
    version: int
    algorithm: str
    nonce: bytes
    ciphertext: bytes


ENCRYPTED_FIELD_CONTRACTS = (
    EncryptedFieldContract(
        id="User.totp_secret",
        domain="hushline.encrypted-field.users.totp_secret",
        table="users",
        column="totp_secret",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="User.email",
        domain="hushline.encrypted-field.users.email",
        table="users",
        column="email",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="User.smtp_server",
        domain="hushline.encrypted-field.users.smtp_server",
        table="users",
        column="smtp_server",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="User.smtp_username",
        domain="hushline.encrypted-field.users.smtp_username",
        table="users",
        column="smtp_username",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="User.smtp_password",
        domain="hushline.encrypted-field.users.smtp_password",
        table="users",
        column="smtp_password",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="User.pgp_key",
        domain="hushline.encrypted-field.users.pgp_key",
        table="users",
        column="pgp_key",
        aad_fields=("user_id",),
    ),
    EncryptedFieldContract(
        id="NotificationRecipient.email",
        domain="hushline.encrypted-field.notification_recipients.email",
        table="notification_recipients",
        column="email",
        aad_fields=("notification_recipient_id", "user_id"),
    ),
    EncryptedFieldContract(
        id="NotificationRecipient.pgp_key",
        domain="hushline.encrypted-field.notification_recipients.pgp_key",
        table="notification_recipients",
        column="pgp_key",
        aad_fields=("notification_recipient_id", "user_id"),
    ),
    EncryptedFieldContract(
        id="FieldValue.value",
        domain="hushline.encrypted-field.field_values._value",
        table="field_values",
        column="_value",
        aad_fields=("field_definition_id", "field_value_id", "message_id"),
    ),
)
ENCRYPTED_FIELD_CONTRACT_BY_ID = {contract.id: contract for contract in ENCRYPTED_FIELD_CONTRACTS}


def generate_salt() -> str:
    """
    Generate a random salt for use in encryption key derivation.
    """
    return urlsafe_b64encode(os.urandom(32)).decode()


def get_encryption_key(scope: bytes | str | None = None, salt: str | None = None) -> Fernet:
    """
    Return the default Fernet encryption key. If a scope and salt are provided, a unique encryption
    key will be derived based on the scope and salt.
    """
    if not (encryption_key := os.environ.get("ENCRYPTION_KEY", None)):
        raise ValueError("Encryption key not found via env var ENCRYPTION_KEY")

    # If a scope is provided, we will use it to derive a unique encryption key
    if scope is not None and salt is not None:
        # Convert the scope to bytes if it is a string
        if isinstance(scope, str):
            scope_bytes = scope.encode()
        elif isinstance(scope, bytes):
            scope_bytes = scope

        # Convert the encryption key and salt to bytes
        encryption_key_bytes = urlsafe_b64decode(encryption_key)
        salt_bytes = urlsafe_b64decode(salt)

        # Use Scrypt to derive a unique encryption key based on the scope
        kdf = Scrypt(salt=salt_bytes, length=SCRYPT_LENGTH, **_SCRYPT_PARAMS)

        # Concatenate the encryption key with the scope
        items = (encryption_key_bytes, scope_bytes)
        result = len(items).to_bytes(8, "big")
        result += b"".join(len(item).to_bytes(8, "big") + item for item in items)

        # Derive the new key
        new_encryption_key_bytes = kdf.derive(result)
        encryption_key = urlsafe_b64encode(new_encryption_key_bytes).decode()

    return Fernet(encryption_key)


def build_encrypted_field_aad(contract: EncryptedFieldContract, values: Mapping[str, int]) -> bytes:
    mutable_names = ENCRYPTED_FIELD_MUTABLE_AAD_NAMES.intersection(values)
    if mutable_names:
        names = ", ".join(sorted(mutable_names))
        raise ValueError(f"Mutable values are not allowed in encrypted field AAD: {names}")

    expected_fields = set(contract.aad_fields)
    actual_fields = set(values)
    if actual_fields != expected_fields:
        missing = ", ".join(sorted(expected_fields - actual_fields)) or "none"
        extra = ", ".join(sorted(actual_fields - expected_fields)) or "none"
        raise ValueError(f"Encrypted field AAD mismatch; missing: {missing}; extra: {extra}")

    for name, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"Encrypted field AAD value {name!r} must be a positive integer")

    return json.dumps(
        {
            "alg": ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM,
            "column": contract.column,
            "domain": contract.domain,
            "row": {name: values[name] for name in contract.aad_fields},
            "schema": ENCRYPTED_FIELD_AAD_SCHEMA,
            "table": contract.table,
            "v": ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _get_encrypted_field_aead_key() -> bytes:
    if not (encryption_key := os.environ.get("ENCRYPTION_KEY", None)):
        raise ValueError("Encryption key not found via env var ENCRYPTION_KEY")

    encryption_key_bytes = urlsafe_b64decode(encryption_key)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=ENCRYPTED_FIELD_AEAD_KEY_INFO,
    ).derive(encryption_key_bytes)


def _encode_unpadded_urlsafe(data: bytes) -> str:
    return urlsafe_b64encode(data).decode().rstrip("=")


def _decode_unpadded_urlsafe(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


def serialize_encrypted_field_envelope(
    ciphertext: str,
    version: int = ENCRYPTED_FIELD_ENVELOPE_VERSION,
    algorithm: str = ENCRYPTED_FIELD_ENVELOPE_ALGORITHM,
) -> str:
    if version != ENCRYPTED_FIELD_ENVELOPE_VERSION:
        raise ValueError("Unsupported encrypted field envelope version")
    if algorithm != ENCRYPTED_FIELD_ENVELOPE_ALGORITHM:
        raise ValueError("Unsupported encrypted field envelope algorithm")
    if not ciphertext:
        raise ValueError("Encrypted field envelope ciphertext is required")

    payload = json.dumps(
        {"alg": algorithm, "ct": ciphertext, "v": version},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded_payload = urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{ENCRYPTED_FIELD_ENVELOPE_PREFIX}{encoded_payload}"


def parse_encrypted_field_envelope(data: str) -> EncryptedFieldEnvelope | None:
    if not data.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX):
        return None

    encoded_payload = data[len(ENCRYPTED_FIELD_ENVELOPE_PREFIX) :]
    try:
        payload = urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        envelope = json.loads(payload.decode())
    except (binascii.Error, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise InvalidToken from exc

    if not isinstance(envelope, dict):
        raise InvalidToken

    version = envelope.get("v")
    algorithm = envelope.get("alg")
    ciphertext = envelope.get("ct")
    if (
        version != ENCRYPTED_FIELD_ENVELOPE_VERSION
        or algorithm != ENCRYPTED_FIELD_ENVELOPE_ALGORITHM
        or not isinstance(ciphertext, str)
        or not ciphertext
    ):
        raise InvalidToken

    return EncryptedFieldEnvelope(
        version=version,
        algorithm=algorithm,
        ciphertext=ciphertext,
    )


def serialize_encrypted_field_aead_envelope(ciphertext: bytes, nonce: bytes) -> str:
    if not ciphertext:
        raise ValueError("Encrypted field envelope ciphertext is required")
    if not nonce:
        raise ValueError("Encrypted field envelope nonce is required")

    payload = json.dumps(
        {
            "alg": ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM,
            "ct": _encode_unpadded_urlsafe(ciphertext),
            "n": _encode_unpadded_urlsafe(nonce),
            "v": ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded_payload = _encode_unpadded_urlsafe(payload)
    return f"{ENCRYPTED_FIELD_ENVELOPE_PREFIX}{encoded_payload}"


def parse_encrypted_field_aead_envelope(data: str) -> EncryptedFieldAEADEnvelope:
    if not data.startswith(ENCRYPTED_FIELD_ENVELOPE_PREFIX):
        raise InvalidToken

    encoded_payload = data[len(ENCRYPTED_FIELD_ENVELOPE_PREFIX) :]
    try:
        payload = _decode_unpadded_urlsafe(encoded_payload)
        envelope = json.loads(payload.decode())
        nonce = _decode_unpadded_urlsafe(envelope["n"])
        ciphertext = _decode_unpadded_urlsafe(envelope["ct"])
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise InvalidToken from exc

    if not isinstance(envelope, dict):
        raise InvalidToken

    version = envelope.get("v")
    algorithm = envelope.get("alg")
    if (
        version != ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION
        or algorithm != ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM
        or not nonce
        or not ciphertext
    ):
        raise InvalidToken

    return EncryptedFieldAEADEnvelope(
        version=version,
        algorithm=algorithm,
        nonce=nonce,
        ciphertext=ciphertext,
    )


def encrypt_field_aead_prototype(
    data: bytes | str | None,
    contract: EncryptedFieldContract,
    aad_values: Mapping[str, int],
) -> str | None:
    if data is None:
        return None
    if not isinstance(data, bytes):
        data = data.encode()

    aad = build_encrypted_field_aad(contract, aad_values)
    nonce = os.urandom(12)
    ciphertext = AESGCM(_get_encrypted_field_aead_key()).encrypt(nonce, data, aad)
    return serialize_encrypted_field_aead_envelope(ciphertext, nonce)


def decrypt_field_aead_prototype(
    data: str | None,
    contract: EncryptedFieldContract,
    aad_values: Mapping[str, int],
) -> str | None:
    if data is None:
        return None

    envelope = parse_encrypted_field_aead_envelope(data)
    aad = build_encrypted_field_aad(contract, aad_values)
    try:
        plaintext = AESGCM(_get_encrypted_field_aead_key()).decrypt(
            envelope.nonce,
            envelope.ciphertext,
            aad,
        )
    except InvalidTag as exc:
        raise InvalidToken from exc
    return plaintext.decode()


def encrypt_field(
    data: bytes | str | None, scope: bytes | str | None = None, salt: str | None = None
) -> str | None:
    """
    Encrypts the data with the default encryption key. If both scope and salt are provided,
    a unique encryption key will be derived based on the scope and salt.
    """
    if data is None:
        return None

    fernet = get_encryption_key(scope, salt)

    # Check if data is already a bytes object
    if not isinstance(data, bytes):
        # If data is a string, encode it to bytes
        data = data.encode()

    # We explicitly set the current time to 0 to avoid storing timestamps
    # that could be used to de-anonymize user-activity per the threat model.
    return fernet.encrypt_at_time(data, current_time=0).decode()


def decrypt_field(
    data: str | None, scope: bytes | str | None = None, salt: str | None = None
) -> str | None:
    """
    Decrypts the data with the default encryption key. If both scope and salt are provided,
    a unique encryption key will be derived based on the scope and salt.
    """
    if data is None:
        return None

    envelope = parse_encrypted_field_envelope(data)
    if envelope is not None:
        data = envelope.ciphertext

    fernet = get_encryption_key(scope, salt)
    return fernet.decrypt(data.encode()).decode()


def is_valid_pgp_key(key: str) -> bool:
    current_app.logger.debug(f"Attempting to validate key: {key}")
    try:
        # Attempt to load the PGP key to verify its validity
        Cert.from_bytes(key.encode())
        return True
    except (RuntimeError, TypeError, ValueError) as e:
        current_app.logger.error(f"Error validating PGP key: {e}")
        return False


def can_encrypt_with_pgp_key(key: str) -> bool:
    """
    Validate that we can encrypt a message with the provided public key.
    """
    try:
        recipient_cert = Cert.from_bytes(key.encode())
        test_message = b"pgp-encryption-test"
        encrypted = encrypt([recipient_cert], test_message)
        return bool(encrypted)
    except (RuntimeError, TypeError, ValueError) as e:
        current_app.logger.error(f"Error during encryption test: {e}")
        return False


def _load_recipient_certs(user_pgp_keys: str | Sequence[str]) -> list[Cert]:
    keys = [user_pgp_keys] if isinstance(user_pgp_keys, str) else list(user_pgp_keys)
    if not keys:
        raise ValueError("At least one PGP key is required for encryption")
    return [Cert.from_bytes(key.encode()) for key in keys]


def encrypt_message(message: str, user_pgp_keys: str | Sequence[str]) -> str:
    current_app.logger.info("Encrypting message for user with provided PGP key")
    recipient_certs = _load_recipient_certs(user_pgp_keys)

    # Encode the message string to bytes
    message_bytes = message.encode("utf-8")

    # Assuming there is no signer (i.e., unsigned encryption).
    encrypted = encrypt(recipient_certs, message_bytes)
    if isinstance(encrypted, bytes):
        return encrypted.decode("utf-8")
    return encrypted


def encrypt_bytes(data: bytes, user_pgp_keys: str | Sequence[str]) -> bytes | None:
    current_app.logger.info("Encrypting bytes for user with provided PGP key")
    try:
        recipient_certs = _load_recipient_certs(user_pgp_keys)
        encrypted = encrypt(recipient_certs, data)
        if isinstance(encrypted, str):
            return encrypted.encode("utf-8")
        return encrypted
    except (RuntimeError, TypeError, ValueError) as e:
        current_app.logger.error(f"Error during encryption: {e}")
        return None


def gen_reply_slug() -> str:
    # 4 words = 7776**4 = 51.7 bits of entropy
    return "-".join(secrets.choice(SLUG_DICEWARE_WORDS) for _ in range(4))

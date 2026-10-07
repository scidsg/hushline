"""Per-order encryption keeps invitations and workflow results out of artifacts."""

import base64
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

MAX_PRIVATE_BYTES = 8192
RSA_BITS = 2048


def keys() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, base64.b64encode(public).decode()


def encrypt(public_key: str, value: dict[str, Any]) -> dict[str, str]:
    if not isinstance(public_key, str) or len(public_key) > MAX_PRIVATE_BYTES:
        raise ValueError("Per-order result key exceeded safety limit")
    public = serialization.load_pem_public_key(base64.b64decode(public_key, validate=True))
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < RSA_BITS:
        raise ValueError("A valid per-order result encryption key is required")
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > MAX_PRIVATE_BYTES:
        raise ValueError("Private result exceeded safety limit")
    key = Fernet.generate_key()
    wrapped = public.encrypt(
        key,
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=b"hushline-single-tenant-v1",
        ),
    )
    return {
        "wrapped_key": base64.b64encode(wrapped).decode(),
        "payload": Fernet(key).encrypt(encoded).decode(),
    }


def decrypt(private_key: str, envelope: dict[str, str]) -> dict[str, Any]:
    try:
        if set(envelope) != {"wrapped_key", "payload"} or any(
            len(value) > MAX_PRIVATE_BYTES * 2 for value in envelope.values()
        ):
            raise ValueError("Invalid encrypted result")
        private = serialization.load_pem_private_key(private_key.encode(), password=None)
        if not isinstance(private, rsa.RSAPrivateKey):
            raise ValueError("Invalid owned result key")
        key = private.decrypt(
            base64.b64decode(envelope["wrapped_key"], validate=True),
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=b"hushline-single-tenant-v1",
            ),
        )
        encoded = Fernet(key).decrypt(envelope["payload"].encode())
        if len(encoded) > MAX_PRIVATE_BYTES:
            raise ValueError("Private result exceeded safety limit")
        result = json.loads(encoded)
        if not isinstance(result, dict):
            raise ValueError("Invalid decrypted result")
        return result
    except (ValueError, TypeError, KeyError, InvalidToken):
        raise ValueError("Encrypted result failed exact-order authentication") from None

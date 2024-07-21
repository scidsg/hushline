"""
Facilitates the transparent encryption & decryption of sensitive database
fields.
"""

from collections import deque

from flask import current_app


def encrypt_field(
    data: bytes | str | None,
    *,
    domain: bytes | bytearray,
    aad: deque[bytes | bytearray] | None = None,
) -> str | None:
    if aad is None:
        aad = deque()

    if isinstance(data, str):
        data = data.encode()
    elif data is None:
        # the interface must consistently clear `aad` before returning, as `SecretsManager` does
        aad.clear()
        return None

    aad.appendleft(b"database_field")
    return current_app.config["VAULT"].encrypt(data, domain=domain, aad=aad).decode()


def decrypt_field(
    data: bytes | str | None,
    *,
    domain: bytes | bytearray,
    aad: deque[bytes | bytearray] | None = None,
    ttl: int | None = None,
) -> str | None:
    if aad is None:
        aad = deque()

    if isinstance(data, str):
        data = data.encode()
    elif data is None:
        # the interface must consistently clear `aad` before returning, as `SecretsManager` does
        aad.clear()
        return None

    aad.appendleft(b"database_field")
    return current_app.config["VAULT"].decrypt(data, domain=domain, aad=aad, ttl=ttl).decode()

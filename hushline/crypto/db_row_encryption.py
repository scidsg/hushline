"""
Facilitates the transparent encryption & decryption of sensitive database
fields.
"""

from flask import current_app


def encrypt_field(
    data: bytes | str | None, *, domain: bytes | bytearray, aad: bytes | bytearray = b""
) -> str | None:
    if data is None:
        return None

    # Check if data is already a bytes object
    if not isinstance(data, bytes):
        # If data is a string, encode it to bytes
        data = data.encode()

    return current_app.config["VAULT"].encrypt(data, domain=domain, aad=aad).decode()


def decrypt_field(
    data: str | None,
    *,
    domain: bytes | bytearray,
    aad: bytes | bytearray = b"",
    ttl: int | None = None,
) -> str | None:
    if data is None:
        return None
    return current_app.config["VAULT"].decrypt(data.encode(), domain=domain, aad=aad).decode()

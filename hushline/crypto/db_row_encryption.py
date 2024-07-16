"""
Facilitates the transparent encryption & decryption of sensitive database
fields.
"""

import os

from cryptography.fernet import Fernet

encryption_key = os.environ.get("ENCRYPTION_KEY")

if encryption_key is None:
    raise ValueError("Encryption key not found. Please check your .env file.")

fernet = Fernet(encryption_key)


def encrypt_field(data: bytes | str | None) -> str | None:
    if data is None:
        return None

    # Check if data is already a bytes object
    if not isinstance(data, bytes):
        # If data is a string, encode it to bytes
        data = data.encode()

    return fernet.encrypt(data).decode()


def decrypt_field(data: str | None) -> str | None:
    if data is None:
        return None
    return fernet.decrypt(data.encode()).decode()

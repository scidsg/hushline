import os

from cryptography.fernet import Fernet
from flask import current_app
from pysequoia import Cert, encrypt

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


def is_valid_pgp_key(key):
    current_app.logger.debug(f"Attempting to validate key: {key}")
    try:
        # Attempt to load the PGP key to verify its validity
        Cert.from_bytes(key.encode())
        return True
    except Exception as e:
        current_app.logger.error(f"Error validating PGP key: {e}")
        return False


def encrypt_message(message: str | bytes, user_pgp_key: str) -> str | None:
    current_app.logger.info("Encrypting message for user with provided PGP key")
    try:
        # Load the user's PGP certificate (public key) from the key data
        recipient_cert = Cert.from_bytes(user_pgp_key.encode())

        # Encode the message string to bytes
        message_bytes = message.encode("utf-8")

        # Assuming there is no signer (i.e., unsigned encryption).
        # Adjust the call to encrypt by passing the encoded message
        encrypted = encrypt([recipient_cert], message_bytes)  # Use message_bytes
        return encrypted
    except Exception as e:
        current_app.logger.error(f"Error during encryption: {e}")
        return None

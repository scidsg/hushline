"""
A module with a focus on providing support for PGP functionalities.
"""

from flask import current_app
from pysequoia import Cert, encrypt


def is_valid_pgp_key(key: str) -> bool:
    current_app.logger.debug(f"Attempting to validate key: {key}")
    try:
        # Attempt to load the PGP key to verify its validity
        Cert.from_bytes(key.encode())
        return True
    except Exception as e:
        current_app.logger.error(f"Error validating PGP key: {e}")
        return False


def encrypt_message(message: str, user_pgp_key: str) -> str | None:
    current_app.logger.info("Encrypting message for user with provided PGP key")
    try:
        # Load the user's PGP certificate (public key) from the key data
        recipient_cert = Cert.from_bytes(user_pgp_key.encode())

        # Encode the message string to bytes
        message_bytes = message.encode("utf-8")

        # Assuming there is no signer (i.e., unsigned encryption).
        # Adjust the call to encrypt by passing the encoded message
        return encrypt([recipient_cert], message_bytes)  # Use message_bytes
    except Exception as e:
        current_app.logger.error(f"Error during encryption: {e}")
        return None

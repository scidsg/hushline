import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from flask import current_app
from pysequoia import Cert, encrypt


def generate_salt() -> str:
    """
    Generate a random salt for use in encryption key derivation.
    """
    return urlsafe_b64encode(os.urandom(16)).decode()


def get_encryption_key(scope: bytes | str | None = None, salt: str | None = None) -> Fernet:
    """
    Return the default Fernet encryption key. If a scope and salt are provided, a unique encryption
    key will be derived based on the scope and salt.
    """
    encryption_key = os.environ.get("ENCRYPTION_KEY")
    if encryption_key is None:
        raise ValueError("Encryption key not found. Please check your .env file.")

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
        kdf = Scrypt(
            salt=salt_bytes,
            length=32,
            n=2**14,
            r=8,
            p=1,
        )
        new_encryption_key_bytes = kdf.derive(encryption_key_bytes + scope_bytes)
        encryption_key = urlsafe_b64encode(new_encryption_key_bytes).decode()

    return Fernet(encryption_key)


encryption_key = os.environ.get("ENCRYPTION_KEY")

if encryption_key is None:
    raise ValueError("Encryption key not found. Please check your .env file.")


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

    fernet = get_encryption_key(scope, salt)
    return fernet.decrypt(data.encode()).decode()


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

import os

import gnupg
from cryptography.fernet import Fernet
from flask import current_app

encryption_key = os.environ.get("ENCRYPTION_KEY")
if encryption_key is None:
    raise ValueError("Encryption key not found. Please check your .env file.")

fernet = Fernet(encryption_key)

gpg_home = os.path.expanduser("~/.gnupg")


def encrypt_field(data):
    if data is None:
        return None
    return fernet.encrypt(data.encode()).decode()


def decrypt_field(data):
    if data is None:
        return None
    return fernet.decrypt(data.encode()).decode()


def is_valid_pgp_key(key):
    current_app.logger.debug(f"Attempting to import key: {key}")
    gpg = gnupg.GPG(gpg_home)
    try:
        imported_key = gpg.import_keys(key)
        current_app.logger.info(f"Key import attempt: {imported_key.results}")
        return imported_key.count > 0
    except Exception as e:
        current_app.logger.error(f"Error importing PGP key: {e}")
        return False


def encrypt_message(message, recipient_email):
    gpg = gnupg.GPG(gpg_home, options=["--trust-model", "always"])
    current_app.logger.info(f"Encrypting message for recipient: {recipient_email}")

    try:
        # Ensure the message is a byte string encoded in UTF-8
        if isinstance(message, str):
            message = message.encode("utf-8")
        encrypted_data = gpg.encrypt(message, recipients=recipient_email, always_trust=True)

        if not encrypted_data.ok:
            current_app.logger.error(f"Encryption failed: {encrypted_data.status}")
            return None

        return str(encrypted_data)
    except Exception as e:
        current_app.logger.error(f"Error during encryption: {e}")
        return None


def list_keys():
    gpg = gnupg.GPG(gpg_home)
    try:
        public_keys = gpg.list_keys()
        current_app.logger.info("Public keys in the keyring:")
        for key in public_keys:
            current_app.logger.info(f"Key: {key}")
    except Exception as e:
        current_app.logger.error(f"Error listing keys: {e}")


def get_email_from_pgp_key(pgp_key):
    gpg = gnupg.GPG(gpg_home)
    try:
        # Import the PGP key
        imported_key = gpg.import_keys(pgp_key)

        if imported_key.count > 0:
            # Get the Key ID of the imported key
            key_id = imported_key.results[0]["fingerprint"][-16:]

            # List all keys to find the matching key
            all_keys = gpg.list_keys()
            for key in all_keys:
                if key["keyid"] == key_id:
                    # Extract email from the uid (user ID)
                    uids = key["uids"][0]
                    email_start = uids.find("<") + 1
                    email_end = uids.find(">")
                    if email_start > 0 and email_end > email_start:
                        return uids[email_start:email_end]
    except Exception as e:
        current_app.logger.error(f"Error extracting email from PGP key: {e}")

    return None

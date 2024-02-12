import os
import pyotp
import gnupg
from cryptography.fernet import Fernet
import logging

# Configure logging
logger = logging.getLogger('crypto')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Ensure all necessary cryptographic configurations are present
encryption_key = os.getenv("ENCRYPTION_KEY")
if not encryption_key:
    logger.critical("Encryption key not found in environment variables.")
    raise EnvironmentError("Missing ENCRYPTION_KEY environment variable.")

try:
    fernet = Fernet(encryption_key)
except Exception as e:
    logger.critical(f"Failed to initialize Fernet with given ENCRYPTION_KEY: {e}")
    raise ValueError("Fernet initialization failed. Check ENCRYPTION_KEY validity.")

gpg_home = os.path.expanduser("~/.gnupg")
try:
    gpg = gnupg.GPG(gnupghome=gpg_home)
except Exception as e:
    logger.critical(f"Failed to initialize GPG: {e}")
    raise EnvironmentError("GPG initialization failed. Check GPG configuration.")

def encrypt_field(data):
    """Encrypts data using Fernet."""
    if data is None:
        return None
    try:
        return fernet.encrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed for data: {e}")
        return None

def decrypt_field(data):
    """Decrypts data using Fernet."""
    if data is None:
        return None
    try:
        return fernet.decrypt(data.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed for data: {e}")
        return None

def encrypt_message(message, recipient_email):
    """Encrypts a message with recipient's PGP key."""
    if not isinstance(message, bytes):
        message = message.encode('utf-8')
    try:
        encrypted_data = gpg.encrypt(message, recipients=recipient_email, always_trust=True)
        if not encrypted_data.ok:
            logger.error(f"PGP encryption failed: {encrypted_data.status}")
            return None
        return str(encrypted_data)
    except Exception as e:
        logger.error(f"Error during PGP encryption: {e}")
        return None

def get_email_from_pgp_key(pgp_key):
    """Extracts email from a PGP key."""
    try:
        imported_key = gpg.import_keys(pgp_key)
        if imported_key.count == 0:
            logger.error("No keys were imported.")
            return None
        key_id = imported_key.results[0]['fingerprint'][-16:]
        for key in gpg.list_keys():
            if key['keyid'] == key_id:
                uids = key['uids'][0]
                email_start = uids.find('<') + 1
                email_end = uids.find('>')
                if email_start > 0 and email_end > email_start:
                    return uids[email_start:email_end]
    except Exception as e:
        logger.error(f"Error extracting email from PGP key: {e}")
        return None

def is_valid_pgp_key(key):
    """Validates a PGP key."""
    try:
        imported_key = gpg.import_keys(key)
        return imported_key.count > 0
    except Exception as e:
        logger.error(f"PGP key validation failed: {e}")
        return False

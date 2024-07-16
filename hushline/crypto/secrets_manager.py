"""
A class definition to simplify the careful handling of cryptographic secrets.
"""

import secrets
import warnings
from pathlib import Path


class SecretsManager:
    __slots__ = ("_secret_salt_filename", "_secret_salt_length")

    _APP_SECRETS_DIRECTORY: Path = Path("hushline/crypto/_app_secrets")
    _SECRET_SALT_FILENAME: str = "_device_salt.txt"
    _SECRET_SALT_LENGTH: int = 32

    def __init__(
        self,
        *,
        secret_salt_filename: str | None = None,
        secret_salt_length: int | None = None,
    ) -> None:
        self._APP_SECRETS_DIRECTORY.mkdir(parents=True, exist_ok=True)
        self._secret_salt_filename = (
            self._SECRET_SALT_FILENAME if secret_salt_filename is None else secret_salt_filename
        )
        self._secret_salt_length = (
            self._SECRET_SALT_LENGTH if secret_salt_length is None else secret_salt_length
        )

    def _summon_device_salt(self) -> bytes:
        salt_path = self._APP_SECRETS_DIRECTORY / self._secret_salt_filename

        if not salt_path.is_file():
            salt_path.write_bytes(salt := secrets.token_bytes(self._secret_salt_length))
        else:
            salt_path.chmod(0o600)
            if len(salt := salt_path.read_bytes()) != self._secret_salt_length:
                warnings.warn("The secret salt length doesn't match its declaration.", stacklevel=2)

        salt_path.chmod(0o000)
        return salt

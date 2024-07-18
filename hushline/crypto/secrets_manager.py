"""
A class definition to simplify the careful handling of cryptographic secrets.
"""

import warnings
from base64 import b64decode, urlsafe_b64encode
from hashlib import shake_256
from pathlib import Path
from secrets import token_bytes

from aiootp.generics.canon import canonical_pack, fullblock_ljust
from cryptography.fernet import Fernet, InvalidToken
from passlib.hash import argon2

__all__ = ["InvalidToken", "SecretsManager"]


def truncated_b64decode(value: bytearray) -> bytearray:
    if bool(remainder := len(value) % 4):
        value = value + (4 - remainder) * b"="
    return bytearray(b64decode(value))


class SecretsManager:
    __slots__ = ("_secret_salt_filename", "_secret_salt_length", "_memory_cost", "_kdf")

    _APP_SECRETS_DIRECTORY: Path = Path("hushline/crypto/_app_secrets")
    _KDF_BLOCKSIZE: int = shake_256().block_size
    _MEMORY_COST_IN_KiB: int = 128 * 1024
    _SECRET_SALT_FILENAME: str = "_device_salt.txt"
    _SECRET_SALT_LENGTH: int = 32

    def __init__(
        self,
        admin_secret: bytearray,
        *,
        memory_cost: int | None = None,
        secret_salt_filename: str | None = None,
        secret_salt_length: int | None = None,
    ) -> None:
        self._APP_SECRETS_DIRECTORY.mkdir(parents=True, exist_ok=True)
        self._memory_cost = self._MEMORY_COST_IN_KiB if memory_cost is None else memory_cost
        self._secret_salt_filename = (
            self._SECRET_SALT_FILENAME if secret_salt_filename is None else secret_salt_filename
        )
        self._secret_salt_length = (
            self._SECRET_SALT_LENGTH if secret_salt_length is None else secret_salt_length
        )
        self._prepare_key_derivation_object(admin_secret)

    def _summon_device_salt(self) -> bytearray:
        salt_path = self._APP_SECRETS_DIRECTORY / self._secret_salt_filename

        if not salt_path.is_file():
            salt_path.write_bytes(salt := token_bytes(self._secret_salt_length))
        else:
            salt_path.chmod(0o600)
            if len(salt := salt_path.read_bytes()) != self._secret_salt_length:
                warnings.warn("The secret salt length doesn't match its declaration.", stacklevel=2)

        salt_path.chmod(0o000)
        return bytearray(salt)

    def _prepare_key_derivation_object(self, admin_secret: bytearray) -> None:
        salt = self._summon_device_salt()
        hashed_secret_with_metadata = bytearray(
            argon2
            .using(salt=bytes(salt), digest_size=self._KDF_BLOCKSIZE, memory_cost=self._memory_cost)
            .hash(bytes(admin_secret)),
            encoding="utf-8",
        )
        hashed_secret = truncated_b64decode(hashed_secret_with_metadata.split(b"$")[-1])
        self._kdf = shake_256(hashed_secret)
        self._kdf.update(fullblock_ljust(hashed_secret_with_metadata, self._KDF_BLOCKSIZE))
        salt.clear()
        admin_secret.clear()
        hashed_secret.clear()
        hashed_secret_with_metadata.clear()

    def derive_key(
        self, *, domain: bytes | bytearray, aad: bytes | bytearray = b"", size: int = 32
    ) -> bytearray:
        kdf = self._kdf.copy()
        size_as_bytes = size.to_bytes(8, "big")
        kdf.update(canonical_pack(domain, aad, size_as_bytes, blocksize=self._KDF_BLOCKSIZE))
        return bytearray(kdf.digest(size))

    def encrypt(
        self,
        data: bytes | bytearray,
        *,
        domain: bytes | bytearray,
        aad: bytes | bytearray = b"",
    ) -> bytes:
        key = bytearray(urlsafe_b64encode(self.derive_key(domain=domain, aad=aad, size=32)))
        try:
            return Fernet(key).encrypt(data)
        finally:
            key.clear()

    def decrypt(
        self,
        data: bytes | bytearray,
        *,
        domain: bytes | bytearray,
        aad: bytes | bytearray = b"",
        ttl: int | None = None,
    ) -> bytes:
        key = bytearray(urlsafe_b64encode(self.derive_key(domain=domain, aad=aad, size=32)))
        try:
            return Fernet(key).decrypt(data, ttl=ttl)
        finally:
            key.clear()

"""
A class definition to simplify the careful handling of cryptographic secrets.
"""

from base64 import b64decode, urlsafe_b64encode
from hashlib import shake_256

from aiootp.generics.canon import canonical_pack
from cryptography.fernet import Fernet, InvalidToken
from passlib.hash import argon2

__all__ = ["InvalidToken", "SecretsManager"]


def truncated_b64decode(value: bytes | bytearray) -> bytearray:
    if bool(remainder := len(value) % 4):
        value = value + (4 - remainder) * b"="
    return bytearray(b64decode(value))


class SecretsManager:
    __slots__ = ("_kdf", "_memory_cost")

    _KDF_BLOCKSIZE: int = shake_256().block_size
    _MEMORY_COST_IN_KiB: int = 128 * 1024

    def __init__(
        self, admin_secret: bytearray, *, salt: bytearray, memory_cost: int | None = None
    ) -> None:
        self._memory_cost = self._MEMORY_COST_IN_KiB if memory_cost is None else memory_cost
        self._prepare_key_derivation_object(admin_secret, salt=salt)

    def _prepare_key_derivation_object(self, admin_secret: bytearray, *, salt: bytearray) -> None:
        hashed_secret_with_metadata = bytearray(
            argon2.using(
                salt=bytes(salt), memory_cost=self._memory_cost, digest_size=self._KDF_BLOCKSIZE
            ).hash(canonical_pack(b"app_admin_secret", bytes(admin_secret))),
            encoding="utf-8",
        )
        # Use the raw, uniform, pseudo-random hash portion of the argon2id output, which is
        # exactly a block-size number of bytes, to initialize a keyed shake_256 object.
        # Reference: https://eprint.iacr.org/2018/449.pdf
        hashed_secret = truncated_b64decode(hashed_secret_with_metadata.split(b"$")[-1])
        self._kdf = shake_256(hashed_secret)

        # Commit to the original encoded argon2id output, pad it to a block-size multiple.
        self._kdf.update(
            canonical_pack(
                b"app_admin_secret_commitment",
                hashed_secret_with_metadata,
                blocksize=self._KDF_BLOCKSIZE,
            )
        )
        salt.clear()
        admin_secret.clear()
        hashed_secret.clear()
        hashed_secret_with_metadata.clear()

    def _derive_key(
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
        key = bytearray(urlsafe_b64encode(self._derive_key(domain=domain, aad=aad, size=32)))
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
        key = bytearray(urlsafe_b64encode(self._derive_key(domain=domain, aad=aad, size=32)))
        try:
            return Fernet(key).decrypt(data, ttl=ttl)
        finally:
            key.clear()

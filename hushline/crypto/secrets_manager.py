"""
A class definition to simplify the careful handling of cryptographic secrets.
"""

from base64 import b64decode
from collections import deque
from hashlib import shake_256
from secrets import token_bytes
from typing import Literal

from aiootp.generics.canon import canonical_pack
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from passlib.hash import argon2

__all__ = ["InvalidTag", "SecretsManager"]


def truncated_b64decode(value: bytes | bytearray) -> bytearray:
    if bool(remainder := len(value) % 4):
        value = value + (4 - remainder) * b"="
    return bytearray(b64decode(value))


class SecretsManager:
    __slots__ = ("_kdf", "_memory_cost")

    _APP_NAME: bytes = b"hushline"  # name to be changed if used in other apps
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
            ).hash(canonical_pack(self._APP_NAME, b"app_admin_secret", bytes(admin_secret))),
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
        self, *, domain: bytes | bytearray, aad: deque[bytes | bytearray], size: int = 32
    ) -> bytearray:
        kdf = self._kdf.copy()
        byte_order: Literal["little", "big"] = "big"
        encoded_size = (byte_order.encode(), size.to_bytes(8, byte_order))
        kdf.update(canonical_pack(domain, *aad, *encoded_size, blocksize=self._KDF_BLOCKSIZE))
        return bytearray(kdf.digest(size))

    def encrypt(
        self,
        data: bytes | bytearray,
        *,
        domain: bytes | bytearray,
        aad: deque[bytes | bytearray] | None = None,
    ) -> bytes:
        if aad is None:
            aad = deque()

        aad.appendleft(salt := token_bytes(32))
        aad.appendleft(b"chacha20_poly1305_cipher_with_derived_inputs_kna_salt256")
        key = bytearray(self._derive_key(domain=domain, aad=aad, size=76))
        try:
            return salt + ChaCha20Poly1305(key[44:]).encrypt(
                data=data, nonce=key[:12], associated_data=key[12:44]
            )
        finally:
            aad.clear()
            key.clear()

    def decrypt(
        self,
        data: bytes | bytearray,
        *,
        domain: bytes | bytearray,
        aad: deque[bytes | bytearray] | None = None,
    ) -> bytes:
        if aad is None:
            aad = deque()

        aad.appendleft(data[:32])
        aad.appendleft(b"chacha20_poly1305_cipher_with_derived_inputs_kna_salt256")
        key = bytearray(self._derive_key(domain=domain, aad=aad, size=76))
        try:
            return ChaCha20Poly1305(key[44:]).decrypt(
                data=data[32:], nonce=key[:12], associated_data=key[12:44]
            )
        finally:
            aad.clear()
            key.clear()

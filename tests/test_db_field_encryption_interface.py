from base64 import urlsafe_b64encode
from collections import deque
from secrets import token_bytes
from typing import Callable

import pytest
from conftest import Flask

from hushline.crypto.db_field_encryption import decrypt_field, encrypt_field


@pytest.mark.parametrize("data_size_multiple", [0, 1, 32])
@pytest.mark.parametrize("aad", [None, deque([b"timestamp"]), deque([bytearray(b"timestamp")])])
@pytest.mark.parametrize("domain", [b"totp_secret", bytearray(b"totp_secret")])
@pytest.mark.parametrize("data", [b"example data", "example data"])
def test_declared_field_value_types_are_handled_correctly(
    data: bytes | str,
    domain: bytes | bytearray,
    aad: deque[bytes | bytearray] | None,
    data_size_multiple: int,
    static_app: Flask,
) -> None:
    def new_aad() -> deque[bytes | bytearray] | None:
        if aad is None:
            return None
        return aad.copy()

    with static_app.app_context():
        assert encrypt_field(None, domain=domain, aad=new_aad()) is None
        assert decrypt_field(None, domain=domain, aad=new_aad()) is None

        plaintext = data_size_multiple * data
        ciphertext = encrypt_field(plaintext, domain=domain, aad=new_aad())

        if isinstance(plaintext, bytes):
            plaintext = plaintext.decode()
        assert isinstance(plaintext, str)
        assert isinstance(ciphertext, bytes)
        assert plaintext == decrypt_field(ciphertext, domain=domain, aad=new_aad())


@pytest.mark.parametrize("aad", [deque([token_bytes(16), bytearray(token_bytes(16))])])
@pytest.mark.parametrize("domain", [b"password_hash", bytearray(b"totp_secret")])
@pytest.mark.parametrize("data", [urlsafe_b64encode(token_bytes(8)), token_bytes(8).hex()])
def test_aad_deque_is_cleared_but_aad_items_are_not_mutated(
    data: bytes | str,
    domain: bytes | bytearray,
    aad: deque[bytes | bytearray],
    static_app: Flask,
) -> None:
    def wrap_in_test(
        func: Callable[..., bytes | str | None], data: bytes | str | None
    ) -> bytes | str | None:
        aad_copy = aad.copy()
        assert aad_copy
        result = func(data, domain=domain, aad=aad_copy)
        assert not aad_copy
        for item, static_item, mutable_item in zip(aad, aad_static_items, aad_mutable_items):
            assert bytes(item) == static_item
            assert item is mutable_item
            assert item
        return result

    aad_static_items = [bytes(item) for item in aad]
    aad_mutable_items = aad.copy()
    with static_app.app_context():
        # None plaintext data
        assert wrap_in_test(encrypt_field, data=None) is None

        # None ciphertext data
        assert wrap_in_test(decrypt_field, data=None) is None

        # bytes | str plaintext data
        ciphertext = wrap_in_test(encrypt_field, data=data)

        if isinstance(data, bytes):
            data = data.decode()
        assert isinstance(data, str)
        assert isinstance(ciphertext, bytes)

        # bytes ciphertext data
        assert data == wrap_in_test(decrypt_field, data=ciphertext)

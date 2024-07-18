from base64 import b64encode
from secrets import token_bytes

import pytest
from conftest import vault

from hushline.crypto.secrets_manager import InvalidToken, truncated_b64decode

DERIVED_KEYS_PER_DISTINCT_INPUTS: dict = {}


def test_device_salt_is_static_once_created() -> None:
    salt = vault._summon_device_salt()
    assert isinstance(salt, bytearray)
    assert len(salt) == vault._secret_salt_length
    assert salt == vault._summon_device_salt()


@pytest.mark.parametrize("size", list(range(33)))
def test_truncated_b64decode_with_variable_length_encoded_inputs(size: int) -> None:
    value = size * b"a"
    encoded_value = b64encode(value).replace(b"=", b"")
    assert value == truncated_b64decode(bytearray(encoded_value))


@pytest.mark.parametrize("size", [16, 24, 32])
@pytest.mark.parametrize("aad", [b"timestamp", b"user_agent"])
@pytest.mark.parametrize("domain", [b"password_hash", b"totp_secret"])
def test_distinct_derived_keys_per_distinct_inputs(domain: bytes, aad: bytes, size: int) -> None:
    key = vault._derive_key(domain=domain, aad=aad, size=size)
    assert len(key) == size
    assert isinstance(key, bytearray)
    bytes_key = bytes(key)
    assert bytes_key[:16] not in DERIVED_KEYS_PER_DISTINCT_INPUTS
    assert bytes_key[:24] not in DERIVED_KEYS_PER_DISTINCT_INPUTS
    assert bytes_key not in DERIVED_KEYS_PER_DISTINCT_INPUTS
    DERIVED_KEYS_PER_DISTINCT_INPUTS[bytes_key] = True


@pytest.mark.parametrize("data", [token_bytes(32) for _ in range(16)])
def test_encryption_correctness(data: bytes) -> None:
    domain = b"test"
    aad = b"tester"
    ciphertext = vault.encrypt(data, domain=domain, aad=aad)
    assert data not in ciphertext
    assert data == vault.decrypt(ciphertext, domain=domain, aad=aad)

    try:
        vault.decrypt(ciphertext, domain=b"wrong-domain", aad=aad)
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with the wrong domain.")

    try:
        vault.decrypt(ciphertext, domain=domain, aad=b"wrong-aad")
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with the wrong authenticated associated data.")

    try:
        vault.decrypt(token_bytes(len(ciphertext)), domain=domain, aad=aad)
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with an arbitrary ciphertext.")

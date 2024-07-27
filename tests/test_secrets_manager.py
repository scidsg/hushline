from base64 import b64encode
from collections import deque
from secrets import token_bytes

import pytest
from conftest import Flask, vault

from hushline import _summon_db_secret
from hushline.crypto.secrets_manager import InvalidToken, truncated_b64decode
from hushline.model import InfrastructureAdmin

_APP_ADMIN_SECRET_SALT_NAME: str = InfrastructureAdmin._APP_ADMIN_SECRET_SALT_NAME
_FLASK_COOKIE_SECRET_KEY_NAME: str = InfrastructureAdmin._FLASK_COOKIE_SECRET_KEY_NAME
DERIVED_KEYS_PER_DISTINCT_INPUTS: dict = {}


class MockInfrastructureAdminEntry:
    name: str = ""
    _value: bytes = b""
    value: bytearray = bytearray()


@pytest.mark.parametrize("name", [_APP_ADMIN_SECRET_SALT_NAME, _FLASK_COOKIE_SECRET_KEY_NAME])
def test_admin_db_secrets_are_static_once_created(static_app: Flask, name: str) -> None:
    with static_app.app_context():
        vault = static_app.config["VAULT"]
        secret = _summon_db_secret(name=name)
        assert isinstance(secret, bytearray)
        assert len(secret) == 32
        assert secret == _summon_db_secret(name=name)

        if (entry := InfrastructureAdmin.query.get(name)) is None:
            # hack: mypy gets upset because the query could return `None`
            db_value = MockInfrastructureAdminEntry()._value
        else:
            db_value = entry._value

        if name == _APP_ADMIN_SECRET_SALT_NAME:
            assert db_value == secret
        else:
            assert db_value != secret
            assert isinstance(db_value, bytes)
            assert len(db_value) > 32
            assert vault.decrypt(db_value, domain=name.encode()) == secret


@pytest.mark.parametrize("size", list(range(33)))
def test_truncated_b64decode_with_variable_length_encoded_inputs(size: int) -> None:
    value = size * b"a"
    encoded_value = b64encode(value).replace(b"=", b"")
    assert value == truncated_b64decode(encoded_value)
    assert value == truncated_b64decode(bytearray(encoded_value))


@pytest.mark.parametrize("size", [16, 24, 32])
@pytest.mark.parametrize("aad", [deque([b"timestamp"]), deque([b"user_agent"])])
@pytest.mark.parametrize("domain", [b"password_hash", b"totp_secret"])
def test_distinct_derived_keys_per_distinct_inputs(
    domain: bytes, aad: deque[bytes | bytearray], size: int
) -> None:
    key = vault._derive_key(domain=domain, aad=aad.copy(), size=size)
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
    aad = deque([b"tester"])
    ciphertext = vault.encrypt(data, domain=domain, aad=aad.copy())
    assert data not in ciphertext
    assert data == vault.decrypt(ciphertext, domain=domain, aad=aad.copy())

    try:
        vault.decrypt(ciphertext, domain=b"wrong-domain", aad=aad.copy())
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with the wrong domain.")

    try:
        vault.decrypt(ciphertext, domain=domain, aad=deque([b"wrong-aad"]))
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with the wrong authenticated associated data.")

    try:
        vault.decrypt(token_bytes(len(ciphertext)), domain=domain, aad=aad.copy())
    except InvalidToken:
        assert True
    else:
        pytest.fail("Decryption succeeded with an arbitrary ciphertext.")

import pytest
from conftest import Flask

from hushline.crypto.db_field_encryption import decrypt_field, encrypt_field


@pytest.mark.parametrize("data_size_multiple", [0, 1, 32])
@pytest.mark.parametrize("aad", [b"timestamp", bytearray(b"timestamp")])
@pytest.mark.parametrize("domain", [b"totp_secret", bytearray(b"totp_secret")])
@pytest.mark.parametrize("data", [b"example data", "example data"])
def test_declared_field_value_types_are_handled_correctly(
    data: bytes | str,
    domain: bytes | bytearray,
    aad: bytes | bytearray,
    data_size_multiple: int,
    static_app: Flask,
) -> None:
    with static_app.app_context():
        assert encrypt_field(None, domain=domain, aad=aad) is None
        assert decrypt_field(None, domain=domain, aad=aad) is None

        plaintext = data_size_multiple * data
        ciphertext = encrypt_field(plaintext, domain=domain, aad=aad)

        if isinstance(plaintext, bytes):
            plaintext = plaintext.decode()
        assert isinstance(plaintext, str)
        assert isinstance(ciphertext, str)
        assert plaintext == decrypt_field(ciphertext, domain=domain, aad=aad)
        assert plaintext == decrypt_field(ciphertext.encode(), domain=domain, aad=aad)

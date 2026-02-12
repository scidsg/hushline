from base64 import urlsafe_b64decode

import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask

from hushline import crypto


def _decode_fernet_token(token: str) -> bytes:
    # Fernet tokens are URL-safe base64 without guaranteed padding.
    return urlsafe_b64decode(token + "=" * (-len(token) % 4))


def test_get_encryption_key_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="Encryption key not found"):
        crypto.get_encryption_key()


def test_scoped_key_derivation_changes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    salt = crypto.generate_salt()

    key_a = crypto.get_encryption_key("scope-a", salt)
    key_a_2 = crypto.get_encryption_key("scope-a", salt)
    key_b = crypto.get_encryption_key(b"scope-b", salt)

    token = key_a.encrypt(b"hello")
    assert key_a_2.decrypt(token) == b"hello"
    with pytest.raises(InvalidToken):
        key_b.decrypt(token)


def test_encrypt_and_decrypt_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    salt = crypto.generate_salt()

    encrypted = crypto.encrypt_field("secret", scope="x", salt=salt)
    assert encrypted is not None
    assert crypto.decrypt_field(encrypted, scope="x", salt=salt) == "secret"


def test_encrypt_field_uses_zero_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt_field("hello")
    assert token is not None
    raw = _decode_fernet_token(token)
    assert raw[0] == 0x80
    assert int.from_bytes(raw[1:9], "big") == 0


def test_none_roundtrips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert crypto.encrypt_field(None) is None
    assert crypto.decrypt_field(None) is None


def test_pgp_helpers(app: Flask) -> None:
    with app.app_context():
        with open("tests/test_pgp_key.txt") as f:
            pgp_key = f.read().strip()

        assert crypto.is_valid_pgp_key(pgp_key)
        assert crypto.can_encrypt_with_pgp_key(pgp_key)

        encrypted_message = crypto.encrypt_message("hello world", pgp_key)
        assert "BEGIN PGP MESSAGE" in encrypted_message

        encrypted_bytes = crypto.encrypt_bytes(b"hello", pgp_key)
        assert encrypted_bytes is not None
        assert b"BEGIN PGP MESSAGE" in encrypted_bytes


def test_pgp_helpers_invalid_key(app: Flask) -> None:
    with app.app_context():
        assert not crypto.is_valid_pgp_key("not-a-key")
        assert not crypto.can_encrypt_with_pgp_key("not-a-key")
        assert crypto.encrypt_bytes(b"hello", "not-a-key") is None


def test_gen_reply_slug_uses_diceware_words() -> None:
    slug = crypto.gen_reply_slug()
    words = slug.split("-")
    assert len(words) == 4
    assert all(word in crypto.DICEWARE_WORDS for word in words)

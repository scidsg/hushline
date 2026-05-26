import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from unittest.mock import call

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


def test_partial_scope_or_salt_uses_base_key_for_legacy_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    salt = crypto.generate_salt()

    base_token = crypto.get_encryption_key().encrypt(b"legacy-value")

    assert crypto.get_encryption_key("scope-only").decrypt(base_token) == b"legacy-value"
    assert crypto.get_encryption_key(salt=salt).decrypt(base_token) == b"legacy-value"


def test_encrypt_and_decrypt_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    salt = crypto.generate_salt()

    encrypted = crypto.encrypt_field("secret", scope="x", salt=salt)
    assert encrypted is not None
    assert not encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(encrypted, scope="x", salt=salt) == "secret"


def test_encrypt_field_accepts_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    encrypted = crypto.encrypt_field(b"secret-bytes")

    assert encrypted is not None
    assert crypto.decrypt_field(encrypted) == "secret-bytes"


def test_scoped_field_ciphertext_requires_matching_scope_and_salt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    salt = crypto.generate_salt()

    encrypted = crypto.encrypt_field("scoped secret", scope="profile:email", salt=salt)

    assert encrypted is not None
    with pytest.raises(InvalidToken):
        crypto.decrypt_field(encrypted, scope="profile:pgp-key", salt=salt)


def test_encrypted_field_envelope_roundtrips_wrapped_fernet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    encrypted = crypto.encrypt_field("secret")
    assert encrypted is not None
    envelope = crypto.serialize_encrypted_field_envelope(encrypted)

    parsed = crypto.parse_encrypted_field_envelope(envelope)
    assert parsed == crypto.EncryptedFieldEnvelope(
        version=crypto.ENCRYPTED_FIELD_ENVELOPE_VERSION,
        algorithm=crypto.ENCRYPTED_FIELD_ENVELOPE_ALGORITHM,
        ciphertext=encrypted,
    )
    assert crypto.decrypt_field(envelope) == "secret"


def test_encrypted_field_aad_is_canonical_and_stable() -> None:
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["NotificationRecipient.email"]

    aad = crypto.build_encrypted_field_aad(
        contract,
        {"user_id": 7, "notification_recipient_id": 3},
    )

    assert json.loads(aad.decode()) == {
        "alg": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM,
        "column": "email",
        "domain": "hushline.encrypted-field.notification_recipients.email",
        "row": {"notification_recipient_id": 3, "user_id": 7},
        "schema": crypto.ENCRYPTED_FIELD_AAD_SCHEMA,
        "table": "notification_recipients",
        "v": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION,
    }
    assert aad == crypto.build_encrypted_field_aad(
        contract,
        {"notification_recipient_id": 3, "user_id": 7},
    )


@pytest.mark.parametrize(
    "values",
    [
        {"username": 1},
        {"email": 1},
        {"display_name": 1},
        {"profile_text": 1},
        {"message_text": 1},
    ],
)
def test_encrypted_field_aad_rejects_mutable_context(values: dict[str, int]) -> None:
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]

    with pytest.raises(ValueError, match="Mutable values are not allowed"):
        crypto.build_encrypted_field_aad(contract, values)


def test_encrypted_field_aead_prototype_requires_expected_domain_and_aad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    email_contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    pgp_key_contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.pgp_key"]

    envelope = crypto.encrypt_field_aead_prototype(
        "secret",
        email_contract,
        {"user_id": 1},
    )

    assert envelope is not None
    assert envelope.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field_aead_prototype(envelope, email_contract, {"user_id": 1}) == "secret"
    with pytest.raises(InvalidToken):
        crypto.decrypt_field_aead_prototype(envelope, pgp_key_contract, {"user_id": 1})
    with pytest.raises(InvalidToken):
        crypto.decrypt_field_aead_prototype(envelope, email_contract, {"user_id": 2})


def test_legacy_fernet_token_has_no_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    encrypted = crypto.encrypt_field("legacy")
    assert encrypted is not None
    assert crypto.parse_encrypted_field_envelope(encrypted) is None
    assert crypto.decrypt_field(encrypted) == "legacy"


def _make_envelope(payload: object) -> str:
    encoded_payload = urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode()
    return f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}{encoded_payload.rstrip('=')}"


def test_unknown_encrypted_field_envelope_version_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    encrypted = crypto.encrypt_field("secret")
    assert encrypted is not None

    envelope = _make_envelope(
        {
            "alg": crypto.ENCRYPTED_FIELD_ENVELOPE_ALGORITHM,
            "ct": encrypted,
            "v": crypto.ENCRYPTED_FIELD_ENVELOPE_VERSION + 1,
        }
    )

    with pytest.raises(InvalidToken):
        crypto.decrypt_field(envelope)


@pytest.mark.parametrize(
    "envelope",
    [
        crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX,
        f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}not-json",
        _make_envelope([]),
        _make_envelope({"alg": crypto.ENCRYPTED_FIELD_ENVELOPE_ALGORITHM, "v": 1}),
        _make_envelope({"alg": "unknown", "ct": "ciphertext", "v": 1}),
        _make_envelope({"alg": crypto.ENCRYPTED_FIELD_ENVELOPE_ALGORITHM, "ct": "", "v": 1}),
        _make_envelope({"alg": crypto.ENCRYPTED_FIELD_ENVELOPE_ALGORITHM, "ct": 1, "v": 1}),
    ],
)
def test_malformed_encrypted_field_envelopes_fail_closed(
    monkeypatch: pytest.MonkeyPatch, envelope: str
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    with pytest.raises(InvalidToken):
        crypto.decrypt_field(envelope)


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


def test_can_encrypt_with_pgp_key_rejects_empty_encryption_result(app: Flask, mocker) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        mocker.patch("hushline.crypto.Cert.from_bytes", return_value=object())
        mocker.patch("hushline.crypto.encrypt", return_value=b"")

        assert not crypto.can_encrypt_with_pgp_key("pgp-key")


def test_encrypt_message_uses_all_recipient_keys(app: Flask, mocker) -> None:  # type: ignore[no-untyped-def]
    cert_one = object()
    cert_two = object()
    with app.app_context():
        from_bytes = mocker.patch(
            "hushline.crypto.Cert.from_bytes",
            side_effect=[cert_one, cert_two],
        )
        encrypt = mocker.patch("hushline.crypto.encrypt", return_value="ciphertext")

        assert crypto.encrypt_message("hello", ["key-one", "key-two"]) == "ciphertext"
        assert from_bytes.call_args_list == [call(b"key-one"), call(b"key-two")]
        encrypt.assert_called_once_with([cert_one, cert_two], b"hello")


def test_load_recipient_certs_requires_at_least_one_key() -> None:
    with pytest.raises(ValueError, match="At least one PGP key is required"):
        crypto._load_recipient_certs([])


def test_public_pgp_encrypt_helpers_reject_empty_recipient_list(app: Flask) -> None:
    with app.app_context():
        with pytest.raises(ValueError, match="At least one PGP key is required"):
            crypto.encrypt_message("hello", [])

        assert crypto.encrypt_bytes(b"hello", []) is None


def test_gen_reply_slug_uses_diceware_words() -> None:
    slug = crypto.gen_reply_slug()
    words = slug.split("-")
    assert len(words) == 4
    assert all(word in crypto.DICEWARE_WORDS for word in words)

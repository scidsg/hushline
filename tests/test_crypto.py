import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path
from typing import Any
from unittest.mock import call

import pytest
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask

from hushline import crypto
from hushline.config import ENCRYPTED_FIELD_WRITE_FORMAT, EncryptedFieldWriteFormat

CRYPTO_VECTOR_FIXTURE = json.loads(
    Path("tests/testdata/crypto-known-answer-vectors.json").read_text()
)

HUSHLINE_AEAD_NEGATIVE_CASES = [
    "corrupted ciphertext byte",
    "corrupted authentication tag byte",
    "wrong AAD row identifier",
    "wrong AAD domain",
    "corrupted nonce byte",
    "malformed nonce length",
    "unknown envelope version",
    "unknown envelope algorithm",
    "unexpected envelope metadata",
]


def _decode_fernet_token(token: str) -> bytes:
    # Fernet tokens are URL-safe base64 without guaranteed padding.
    return urlsafe_b64decode(token + "=" * (-len(token) % 4))


def _decode_unpadded_urlsafe(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _encode_unpadded_urlsafe(data: bytes) -> str:
    return urlsafe_b64encode(data).decode().rstrip("=")


def _aead_payload_from_envelope(envelope: str) -> dict[str, Any]:
    encoded_payload = envelope[len(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX) :]
    payload = _decode_unpadded_urlsafe(encoded_payload)
    return json.loads(payload.decode())


def _aead_envelope_from_payload(payload: dict[str, Any]) -> str:
    encoded_payload = _encode_unpadded_urlsafe(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    return f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}{encoded_payload}"


def _hushline_aead_vector() -> dict[str, Any]:
    return CRYPTO_VECTOR_FIXTURE["hushline_encrypted_field_aead_vectors"][0]


def test_crypto_known_answer_vector_fixture_documents_source_and_rationale() -> None:
    assert CRYPTO_VECTOR_FIXTURE["schema"] == "hushline.crypto-known-answer-vectors.v1"
    assert "NIST SP 800-38D" in CRYPTO_VECTOR_FIXTURE["sources"][0]["name"]
    assert CRYPTO_VECTOR_FIXTURE["sources"][0]["url"] == (
        "https://csrc.nist.gov/pubs/sp/800/38/d/final"
    )
    assert "synthetic" in CRYPTO_VECTOR_FIXTURE["rationale"]
    assert _hushline_aead_vector()["negative_cases"] == HUSHLINE_AEAD_NEGATIVE_CASES


@pytest.mark.parametrize(
    "vector",
    CRYPTO_VECTOR_FIXTURE["aes_gcm_known_answer_vectors"],
    ids=lambda vector: vector["id"],
)
def test_aes_gcm_known_answer_vectors_from_nist(vector: dict[str, str]) -> None:
    key = bytes.fromhex(vector["key_hex"])
    nonce = bytes.fromhex(vector["nonce_hex"])
    aad = bytes.fromhex(vector["aad_hex"])
    plaintext = bytes.fromhex(vector["plaintext_hex"])
    expected_ciphertext = bytes.fromhex(vector["ciphertext_hex"])
    expected_tag = bytes.fromhex(vector["tag_hex"])

    encrypted = AESGCM(key).encrypt(nonce, plaintext, aad)

    assert encrypted[:-16] == expected_ciphertext
    assert encrypted[-16:] == expected_tag
    assert AESGCM(key).decrypt(nonce, expected_ciphertext + expected_tag, aad) == plaintext


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


def test_encrypt_field_defaults_to_legacy_fernet_write_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv(ENCRYPTED_FIELD_WRITE_FORMAT, raising=False)

    encrypted = crypto.encrypt_field("secret")

    assert encrypted is not None
    assert not encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(encrypted) == "secret"


def test_encrypt_field_can_write_versioned_fernet_envelope(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET

    encrypted = crypto.encrypt_field("secret")

    assert encrypted is not None
    assert encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    parsed = crypto.parse_encrypted_field_envelope(encrypted)
    assert parsed is not None
    assert crypto.decrypt_field(parsed.ciphertext) == "secret"
    assert crypto.decrypt_field(encrypted) == "secret"


def test_encrypt_field_envelope_write_requires_schema_check_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv(
        ENCRYPTED_FIELD_WRITE_FORMAT,
        EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
    )

    with pytest.raises(crypto.EncryptedFieldSchemaNotReadyError, match="outside a Flask"):
        crypto.encrypt_field("secret")


def test_encrypt_field_transition_reads_legacy_and_envelope_formats(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET
    legacy_ciphertext = crypto.encrypt_field("legacy")

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    envelope_ciphertext = crypto.encrypt_field("envelope")

    assert legacy_ciphertext is not None
    assert envelope_ciphertext is not None
    assert not legacy_ciphertext.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert envelope_ciphertext.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(legacy_ciphertext) == "legacy"
    assert crypto.decrypt_field(envelope_ciphertext) == "envelope"


def test_encrypt_field_uses_app_configured_write_format(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv(
        ENCRYPTED_FIELD_WRITE_FORMAT,
        EncryptedFieldWriteFormat.LEGACY_FERNET.value,
    )

    with app.app_context():
        app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
        encrypted = crypto.encrypt_field("secret")

    assert encrypted is not None
    assert encrypted.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert crypto.decrypt_field(encrypted) == "secret"


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


def test_encrypt_field_can_write_production_aes_gcm_envelope(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    aad_values = {"user_id": 1}

    encrypted = crypto.encrypt_field("secret", contract=contract, aad_values=aad_values)

    assert encrypted is not None
    parsed = crypto.parse_encrypted_field_aead_envelope(encrypted)
    assert parsed.algorithm == crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM
    assert crypto.decrypt_field(encrypted, contract=contract, aad_values=aad_values) == "secret"
    with pytest.raises(InvalidToken):
        crypto.decrypt_field(encrypted, contract=contract, aad_values={"user_id": 2})
    with pytest.raises(InvalidToken):
        crypto.decrypt_field(
            encrypted,
            contract=crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.pgp_key"],
            aad_values=aad_values,
        )


def test_aes_gcm_write_format_requires_contract_and_aad(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM

    with pytest.raises(ValueError, match="contract and AAD values"):
        crypto.encrypt_field("secret")


def test_hushline_aead_known_answer_vector_encrypts_and_serializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector = _hushline_aead_vector()
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID[vector["contract_id"]]
    nonce = bytes.fromhex(vector["nonce_hex"])

    monkeypatch.setenv("ENCRYPTION_KEY", vector["base_encryption_key_base64"])

    def fixed_nonce(length: int) -> bytes:
        assert length == crypto.ENCRYPTED_FIELD_AEAD_NONCE_LENGTH
        return nonce

    monkeypatch.setattr(crypto.os, "urandom", fixed_nonce)

    aad = crypto.build_encrypted_field_aad(contract, vector["aad_values"])
    encrypted = crypto.encrypt_field_aead_prototype(
        vector["plaintext"],
        contract,
        vector["aad_values"],
    )

    assert crypto._get_encrypted_field_aead_key().hex() == vector["derived_aes_key_hex"]
    assert aad == bytes.fromhex(vector["aad_hex"])
    assert aad.decode() == vector["aad_json"]
    assert encrypted is not None
    assert encrypted == vector["envelope"]
    assert _aead_payload_from_envelope(encrypted)["ct"] == _encode_unpadded_urlsafe(
        bytes.fromhex(vector["ciphertext_and_tag_hex"])
    )
    assert (
        crypto.decrypt_field_aead_prototype(
            vector["envelope"],
            contract,
            vector["aad_values"],
        )
        == vector["plaintext"]
    )


def test_hushline_aead_known_answer_vector_parses_stable_envelope() -> None:
    vector = _hushline_aead_vector()

    envelope = crypto.parse_encrypted_field_aead_envelope(vector["envelope"])

    assert envelope == crypto.EncryptedFieldAEADEnvelope(
        version=crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION,
        algorithm=crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM,
        nonce=bytes.fromhex(vector["nonce_hex"]),
        ciphertext=bytes.fromhex(vector["ciphertext_and_tag_hex"]),
    )
    assert (
        crypto.serialize_encrypted_field_aead_envelope(
            envelope.ciphertext,
            envelope.nonce,
        )
        == vector["envelope"]
    )
    assert (
        json.dumps(
            _aead_payload_from_envelope(vector["envelope"]),
            separators=(",", ":"),
            sort_keys=True,
        )
        == vector["serialized_payload_json"]
    )


@pytest.mark.parametrize("case", HUSHLINE_AEAD_NEGATIVE_CASES)
def test_hushline_aead_known_answer_negative_vectors_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    vector = _hushline_aead_vector()
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID[vector["contract_id"]]
    aad_values = dict(vector["aad_values"])
    envelope = vector["envelope"]

    monkeypatch.setenv("ENCRYPTION_KEY", vector["base_encryption_key_base64"])

    if case == "corrupted ciphertext byte":
        payload = _aead_payload_from_envelope(envelope)
        ciphertext = bytearray(bytes.fromhex(vector["ciphertext_and_tag_hex"]))
        ciphertext[0] ^= 0x01
        payload["ct"] = _encode_unpadded_urlsafe(bytes(ciphertext))
        envelope = _aead_envelope_from_payload(payload)
    elif case == "corrupted authentication tag byte":
        payload = _aead_payload_from_envelope(envelope)
        ciphertext = bytearray(bytes.fromhex(vector["ciphertext_and_tag_hex"]))
        ciphertext[-1] ^= 0x01
        payload["ct"] = _encode_unpadded_urlsafe(bytes(ciphertext))
        envelope = _aead_envelope_from_payload(payload)
    elif case == "wrong AAD row identifier":
        aad_values["user_id"] += 1
    elif case == "wrong AAD domain":
        contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["NotificationRecipient.pgp_key"]
    elif case == "corrupted nonce byte":
        payload = _aead_payload_from_envelope(envelope)
        nonce = bytearray(bytes.fromhex(vector["nonce_hex"]))
        nonce[0] ^= 0x01
        payload["n"] = _encode_unpadded_urlsafe(bytes(nonce))
        envelope = _aead_envelope_from_payload(payload)
    elif case == "malformed nonce length":
        payload = _aead_payload_from_envelope(envelope)
        payload["n"] = _encode_unpadded_urlsafe(bytes.fromhex(vector["nonce_hex"])[:-1])
        envelope = _aead_envelope_from_payload(payload)
    elif case == "unknown envelope version":
        payload = _aead_payload_from_envelope(envelope)
        payload["v"] = crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION + 1
        envelope = _aead_envelope_from_payload(payload)
    elif case == "unknown envelope algorithm":
        payload = _aead_payload_from_envelope(envelope)
        payload["alg"] = "aes-128-gcm"
        envelope = _aead_envelope_from_payload(payload)
    elif case == "unexpected envelope metadata":
        payload = _aead_payload_from_envelope(envelope)
        payload["kid"] = "unexpected"
        envelope = _aead_envelope_from_payload(payload)
    else:  # pragma: no cover - protects the case list from drift.
        raise AssertionError(f"Unhandled negative vector case: {case}")

    with pytest.raises(InvalidToken):
        crypto.decrypt_field_aead_prototype(envelope, contract, aad_values)


def test_hushline_aead_envelope_rejects_non_96_bit_nonce() -> None:
    with pytest.raises(ValueError, match="nonce must be 96 bits"):
        crypto.serialize_encrypted_field_aead_envelope(b"ciphertext-and-tag", b"short")


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

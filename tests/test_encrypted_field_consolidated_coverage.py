import json
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

import click
import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask

from hushline import crypto as crypto_module

crypto: Any = crypto_module
cli: Any = pytest.importorskip("hushline.cli_encrypted_field")


TEST_ENCRYPTION_KEY = "jY0gDbATEOQolx2SGj46YnkkbN6HQBB4YCABzwl1H1A="
TEST_AES_GCM_WRITE_APPROVAL = "test maintainer approval for AES-GCM encrypted-field writes"


pytestmark = pytest.mark.skipif(
    not hasattr(crypto, "ENCRYPTED_FIELD_CONTRACT_BY_ID"),
    reason="encrypted-field modernization surface is not present on this branch",
)


def _encoded_payload(payload: object) -> str:
    return (
        urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        .decode()
        .rstrip("=")
    )


def _envelope(payload: object) -> str:
    return f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}{_encoded_payload(payload)}"


def test_encrypted_field_envelope_serializers_fail_closed_on_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="version"):
        crypto.serialize_encrypted_field_envelope("ciphertext", version=999)
    with pytest.raises(ValueError, match="algorithm"):
        crypto.serialize_encrypted_field_envelope("ciphertext", algorithm="unknown")
    with pytest.raises(ValueError, match="ciphertext"):
        crypto.serialize_encrypted_field_envelope("")

    with pytest.raises(ValueError, match="ciphertext"):
        crypto.serialize_encrypted_field_aead_envelope(b"", b"nonce")
    with pytest.raises(ValueError, match="nonce"):
        crypto.serialize_encrypted_field_aead_envelope(b"ciphertext", b"")


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-envelope",
        f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}not-json",
        _envelope({"v": 2, "alg": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM}),
        _envelope(
            {
                "alg": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_ALGORITHM,
                "ct": _encoded_payload("ciphertext"),
                "n": _encoded_payload("nonce"),
                "v": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION + 1,
            }
        ),
        _envelope(
            {
                "alg": "unsupported",
                "ct": _encoded_payload("ciphertext"),
                "n": _encoded_payload("nonce"),
                "v": crypto.ENCRYPTED_FIELD_AEAD_ENVELOPE_VERSION,
            }
        ),
    ],
)
def test_aead_envelopes_reject_malformed_or_unsupported_payloads(payload: str) -> None:
    with pytest.raises(InvalidToken):
        crypto.parse_encrypted_field_aead_envelope(payload)


def test_aead_prototype_roundtrips_bytes_and_none_without_plaintext_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL", TEST_AES_GCM_WRITE_APPROVAL)
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]

    assert crypto.encrypt_field_aead_prototype(None, contract, {"user_id": 1}) is None
    assert crypto.decrypt_field_aead_prototype(None, contract, {"user_id": 1}) is None

    envelope = crypto.encrypt_field_aead_prototype(b"byte secret", contract, {"user_id": 1})

    assert envelope is not None
    assert "byte secret" not in envelope
    assert crypto.decrypt_field_aead_prototype(envelope, contract, {"user_id": 1}) == "byte secret"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({}, "missing: user_id"),
        ({"user_id": 1, "extra_id": 2}, "extra: extra_id"),
        ({"user_id": 0}, "positive integer"),
        ({"user_id": True}, "positive integer"),
    ],
)
def test_encrypted_field_aad_rejects_incomplete_extra_or_unstable_values(
    values: dict[str, Any],
    message: str,
) -> None:
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]

    with pytest.raises(ValueError, match=message):
        crypto.build_encrypted_field_aad(contract, values)


def test_encrypted_field_write_format_reads_environment_without_app_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        cli.ENCRYPTED_FIELD_WRITE_FORMAT,
        cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
    )

    assert crypto.encrypted_field_write_format() == cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET


def test_migration_resume_state_roundtrips_without_plaintext() -> None:
    state = cli.EncryptedFieldMigrationResumeState(
        helper_version=cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
        batch_size=17,
        contract_ids=("User.totp_secret", "User.email"),
        contract_id="User.email",
        last_primary_key=42,
    )

    token = cli._serialize_resume_state(state)

    assert "User.email" not in token
    assert (
        cli._parse_resume_state(
            token,
            batch_size=17,
            contract_ids=("User.totp_secret", "User.email"),
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
        )
        == state
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"helper_version": "other-helper"}, "helper version"),
        ({"target_format": "legacy-fernet"}, "target format"),
        ({"batch_size": 99}, "batch size"),
        ({"contract_ids": ["User.email"]}, "contract set"),
        ({"contract_id": "User.email"}, "contract is not in this run"),
        ({"last_primary_key": 0}, "last primary key"),
    ],
)
def test_migration_resume_state_rejects_stale_or_cross_run_tokens(
    override: dict[str, object],
    message: str,
) -> None:
    data: dict[str, object] = {
        "helper_version": cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        "target_format": cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
        "batch_size": 10,
        "contract_ids": ["User.totp_secret"],
        "contract_id": "User.totp_secret",
        "last_primary_key": 1,
    }
    data.update(override)
    token = cli._encoded_json(data)

    with pytest.raises(click.ClickException, match=message):
        cli._parse_resume_state(
            token,
            batch_size=10,
            contract_ids=("User.totp_secret",),
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
        )


@pytest.mark.parametrize("token", ["not-json", cli._encoded_json([])])
def test_migration_resume_state_rejects_invalid_json_tokens(token: str) -> None:
    with pytest.raises(
        click.ClickException,
        match="Invalid encrypted-field migration resume token",
    ):
        cli._decoded_json(token)


def test_preflight_classification_counts_safe_buckets_without_disclosing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    legacy_ciphertext = crypto.encrypt_field("legacy secret")
    assert legacy_ciphertext is not None
    envelope_ciphertext = crypto.serialize_encrypted_field_envelope(legacy_ciphertext)
    aead_envelope = crypto.serialize_encrypted_field_aead_envelope(
        b"synthetic-ciphertext",
        b"0" * crypto.ENCRYPTED_FIELD_AEAD_NONCE_LENGTH,
    )
    undecryptable_envelope = crypto.serialize_encrypted_field_envelope(
        "gAAAAABnot-a-decryptable-fernet-token"
    )
    undecodable_legacy = (
        crypto.get_encryption_key()
        .encrypt_at_time(
            b"\xff",
            current_time=0,
        )
        .decode()
    )

    classifications = [
        cli._classify_preflight_value(None),
        cli._classify_preflight_value(""),
        cli._classify_preflight_value(123),
        cli._classify_preflight_value(f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}not-json"),
        cli._classify_preflight_value(undecryptable_envelope),
        cli._classify_preflight_value(undecodable_legacy),
        cli._classify_preflight_value(legacy_ciphertext),
        cli._classify_preflight_value(envelope_ciphertext),
        cli._classify_preflight_value(aead_envelope),
    ]
    counts = cli.EncryptedFieldCiphertextCounts()
    for classification in classifications:
        cli._record_preflight_classification(counts, classification)

    assert classifications == [
        "null_empty",
        "null_empty",
        "malformed",
        "malformed",
        "decrypt_failure",
        "decrypt_failure",
        "legacy_fernet",
        "envelope_fernet",
        "envelope_aes_gcm",
    ]
    assert counts.row_count == 9
    assert counts.scanned_rows == 9
    assert counts.null_empty == 2
    assert counts.malformed == 2
    assert counts.decrypt_failures == 4
    assert counts.legacy_fernet == 1
    assert counts.envelope_fernet == 1
    assert counts.envelope_aes_gcm == 1


def test_rollout_classifier_recognizes_aes_gcm_without_fernet_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aead_envelope = crypto.serialize_encrypted_field_aead_envelope(
        b"synthetic-ciphertext",
        b"0" * crypto.ENCRYPTED_FIELD_AEAD_NONCE_LENGTH,
    )

    def fail_fernet_probe(value: str) -> None:
        raise AssertionError(f"unexpected Fernet envelope parse for {value!r}")

    monkeypatch.setattr(cli, "parse_encrypted_field_envelope", fail_fernet_probe)

    assert cli._classify_envelope_value(aead_envelope) == "envelope_aes_gcm"
    assert cli._classify_preflight_value(aead_envelope) == "envelope_aes_gcm"


def test_preflight_report_marks_capacity_only_missing_schema_as_blocked() -> None:
    contract = crypto.EncryptedFieldContract(
        id="User.missing_secret",
        domain="hushline.encrypted-field.users.missing_secret",
        table="users",
        column="missing_secret",
        aad_fields=("user_id",),
    )
    report = cli._encrypted_field_preflight_report(
        contracts=(contract,),
        capacity_reports=[
            cli.EncryptedFieldCapacityReport(
                contract_id=contract.id,
                table=contract.table,
                column=contract.column,
                ready=False,
                detail="missing column",
            )
        ],
        ciphertext_reports=[],
        alembic_revision="test-revision",
        batch_size=25,
        require_no_legacy=False,
    )

    assert report["status"] == "blocked"
    assert report["blocked_reasons"] == [
        {"code": "missing_schema", "contract_ids": ["User.missing_secret"]}
    ]
    assert report["contracts"][0]["rows"] == {
        "envelope_aes_gcm": 0,
        "envelope_fernet": 0,
        "legacy_fernet": 0,
        "null_empty": 0,
        "scanned": 0,
        "total": 0,
    }
    assert cli._preflight_human_reason_phrases(report["blocked_reasons"]) == [
        "schema is not envelope-ready"
    ]


def test_release_gate_preflight_errors_require_complete_clean_artifact() -> None:
    report = {
        "contract_set": {
            "contract_ids": [contract.id for contract in crypto.ENCRYPTED_FIELD_CONTRACTS],
            "version": cli.ENCRYPTED_FIELD_CONTRACT_SET_VERSION,
        },
        "contracts": [
            {"contract_id": contract.id, "status": "ready"}
            for contract in crypto.ENCRYPTED_FIELD_CONTRACTS
        ],
        "helper_version": cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        "report_type": "encrypted-field-preflight",
        "schema_revision": cli.ENCRYPTED_FIELD_PREFLIGHT_SCHEMA_REVISION,
        "status": "ready",
        "totals": {"decrypt_failures": 1, "malformed": 0, "rows_scanned": 2, "rows_total": 3},
    }

    errors = cli._release_gate_preflight_errors(report)

    assert "preflight artifact must have zero decrypt failures" in errors
    assert "preflight artifact must scan every encrypted-field row" in errors


def test_load_json_artifact_rejects_unreadable_invalid_or_non_object_files(
    tmp_path: Path,
) -> None:
    with pytest.raises(click.ClickException, match="Cannot read preflight artifact"):
        cli._load_json_artifact(tmp_path / "missing.json", "preflight")

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(click.ClickException, match="Invalid JSON in preflight artifact"):
        cli._load_json_artifact(invalid_json, "preflight")

    non_object = tmp_path / "list.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(click.ClickException, match="Invalid preflight artifact"):
        cli._load_json_artifact(non_object, "preflight")


def test_migration_failure_safe_message_redacts_unknown_primary_key() -> None:
    failure = cli.EncryptedFieldMigrationFailure(
        contract_id="User.email",
        primary_key=None,
        phase="decrypt",
        error_class="InvalidToken",
        source_left_unchanged=False,
    )

    assert failure.safe_message() == (
        "contract=User.email primary_key=unknown phase=decrypt "
        "error=InvalidToken source_left_unchanged=unknown"
    )


def test_build_target_ciphertext_fails_closed_when_writer_returns_empty_value(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    monkeypatch.setattr(cli, "encrypt_field", lambda plaintext: None)

    with app.app_context(), pytest.raises(ValueError, match="empty value"):
        cli._build_target_ciphertext(
            "secret",
            cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
        )

    assert (
        app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] == cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    )

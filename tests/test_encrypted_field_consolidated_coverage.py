import json
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

import click
import pytest
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask
from sqlalchemy import String
from sqlalchemy.exc import NoSuchTableError

from hushline import crypto as crypto_module
from hushline.db import db
from hushline.model import FieldValue, Message, User

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
        _envelope([]),
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


def test_model_aad_helpers_require_persisted_ids_and_flush_field_values(
    app: Flask,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)

    transient_user = User(password="x" * User.PASSWORD_MIN_LENGTH)
    with pytest.raises(ValueError, match="persisted user id"):
        transient_user._encrypted_field_aad_values()

    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    msg = Message(username_id=user.primary_username.id)
    db.session.add(msg)
    db.session.commit()
    field_def = user.primary_username.message_fields[-1]
    field_value = FieldValue(field_def, msg, "server fallback detail", False)
    assert field_value.id is None

    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
    app.config["ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED"] = True
    app.config["ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL"] = TEST_AES_GCM_WRITE_APPROVAL

    aad_values = field_value._encrypted_field_aad_values()

    assert field_value.id is not None
    assert aad_values == {
        "field_definition_id": field_def.id,
        "field_value_id": field_value.id,
        "message_id": msg.id,
    }

    field_value.value = "AEAD-bound custom field"

    assert crypto.is_encrypted_field_aead_envelope(field_value._value)
    assert field_value.value == "AEAD-bound custom field"


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


def test_encrypted_field_config_and_schema_missing_paths_fail_closed(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.config["ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED"] = object()
    app.config["ENCRYPTED_FIELD_LEGACY_READS_ENABLED"] = object()

    assert crypto._encrypted_field_aes_gcm_writes_enabled() is False
    assert crypto._encrypted_field_legacy_reads_enabled() is True

    class MissingSchemaInspector:
        def get_columns(self, table_name: str) -> list[dict[str, object]]:
            _ = self
            if table_name == "users":
                raise NoSuchTableError(table_name)
            return [{"name": "id", "type": String(length=512)}]

    monkeypatch.setattr(crypto, "inspect", lambda _engine: MissingSchemaInspector())
    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET

    with pytest.raises(crypto.EncryptedFieldSchemaNotReadyError) as excinfo:
        crypto.assert_encrypted_field_envelope_schema_ready()

    message = str(excinfo.value)
    assert "missing: users.totp_secret" in message
    assert "notification_recipients.email" in message


def test_encrypted_field_write_format_reads_environment_without_app_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        cli.ENCRYPTED_FIELD_WRITE_FORMAT,
        cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
    )

    assert crypto.encrypted_field_write_format() == cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET


def test_aes_gcm_write_gate_defaults_closed_and_rejects_non_object_aead_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED", raising=False)
    assert crypto._encrypted_field_aes_gcm_writes_enabled() is False

    class EnvelopeLike:
        def __getitem__(self, key: str) -> str:
            if key == "n":
                return _encoded_payload("0" * crypto.ENCRYPTED_FIELD_AEAD_NONCE_LENGTH)
            if key == "ct":
                return _encoded_payload("ciphertext")
            raise KeyError(key)

    monkeypatch.setattr(crypto.json, "loads", lambda _payload: EnvelopeLike())
    valid_payload = crypto.serialize_encrypted_field_aead_envelope(
        b"ciphertext",
        b"0" * crypto.ENCRYPTED_FIELD_AEAD_NONCE_LENGTH,
    )

    with pytest.raises(InvalidToken):
        crypto.parse_encrypted_field_aead_envelope(valid_payload)


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


def test_capacity_report_handles_missing_table_without_schema_details(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app
    contract = crypto.EncryptedFieldContract(
        id="Missing.secret",
        domain="hushline.encrypted-field.missing.secret",
        table="missing_table",
        column="secret",
        aad_fields=("user_id",),
    )

    class MissingTableInspector:
        def get_columns(self, table_name: str) -> list[dict[str, object]]:
            _ = self
            assert table_name == "missing_table"
            raise NoSuchTableError(table_name)

    monkeypatch.setattr(cli, "inspect", lambda _engine: MissingTableInspector())

    assert cli._encrypted_field_column_capacity_reports((contract,)) == [
        cli.EncryptedFieldCapacityReport(
            contract_id="Missing.secret",
            table="missing_table",
            column="secret",
            ready=False,
            detail="missing table",
        )
    ]


def test_contract_lookup_and_resume_parse_fail_closed() -> None:
    malformed_state = cli._encoded_json(
        {
            "helper_version": cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
            "target_format": cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
            "batch_size": "not-an-int",
            "contract_ids": ["User.email"],
            "contract_id": "User.email",
            "last_primary_key": 1,
        }
    )

    with pytest.raises(click.ClickException, match="Unknown encrypted-field contract"):
        cli._contract_by_id("Nope.secret")
    with pytest.raises(
        click.ClickException,
        match="Invalid encrypted-field migration resume token",
    ):
        cli._parse_resume_state(
            malformed_state,
            batch_size=10,
            contract_ids=("User.email",),
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
        )


def test_migration_contract_helpers_fail_closed_and_bind_expected_aad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatched_contract = crypto.EncryptedFieldContract(
        id="User.missing",
        domain="hushline.encrypted-field.users.missing",
        table="users",
        column="missing",
        aad_fields=("user_id",),
    )
    with pytest.raises(cli.EncryptedFieldMigrationError) as mismatch:
        cli._table_for_contract(mismatched_contract)
    assert "ContractMismatch" in mismatch.value.failure.safe_message()

    cross_table_contract = crypto.EncryptedFieldContract(
        id="NotificationRecipient.synthetic",
        domain="hushline.encrypted-field.notification_recipients.synthetic",
        table="notification_recipients",
        column="email",
        aad_fields=("user_id",),
    )
    assert cli._aad_values_for_row(cross_table_contract, {"id": 3, "user_id": 7}) == {"user_id": 7}

    def reject_fernet_envelope(_value: str) -> None:
        raise InvalidToken

    monkeypatch.setattr(cli, "is_encrypted_field_aead_envelope", lambda _value: False)
    monkeypatch.setattr(cli, "parse_encrypted_field_envelope", reject_fernet_envelope)
    monkeypatch.setattr(cli, "parse_encrypted_field_aead_envelope", lambda _value: object())

    assert cli._classify_envelope_value("hlfield:synthetic") == "envelope_aes_gcm"


def test_migration_row_fails_closed_if_classification_allows_non_string(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    monkeypatch.setattr(cli, "_classify_migration_value", lambda _value: "legacy_fernet")

    with pytest.raises(AssertionError, match="non-string"):
        cli._process_migration_row(
            contract=contract,
            row={"id": 1, "email": object()},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=report,
        )


def test_migration_row_contract_and_ciphertext_failures_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setenv(
        cli.ENCRYPTED_FIELD_WRITE_FORMAT,
        cli.EncryptedFieldWriteFormat.LEGACY_FERNET.value,
    )
    missing_aad_contract = crypto.EncryptedFieldContract(
        id="User.email.synthetic",
        domain="hushline.encrypted-field.users.email.synthetic",
        table="users",
        column="email",
        aad_fields=("missing_id",),
    )

    with pytest.raises(cli.EncryptedFieldMigrationError) as missing_aad:
        cli._aad_values_for_row(missing_aad_contract, {"id": 7, "email": "ciphertext"})

    assert missing_aad.value.failure.safe_message() == (
        "contract=User.email.synthetic primary_key=7 phase=contract "
        "error=MissingAADField source_left_unchanged=yes"
    )

    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    with pytest.raises(cli.EncryptedFieldMigrationError) as decrypt_failure:
        cli._verify_ciphertext_plaintext(
            contract=contract,
            primary_key=3,
            phase="verify-existing-target",
            ciphertext="not-a-valid-fernet-token",
            expected_plaintext="secret",
        )

    message = decrypt_failure.value.failure.safe_message()
    assert "contract=User.email primary_key=3 phase=verify-existing-target" in message
    assert "not-a-valid-fernet-token" not in message

    valid_ciphertext = crypto_module.encrypt_field("different secret")
    assert valid_ciphertext is not None
    with pytest.raises(cli.EncryptedFieldMigrationError) as mismatch:
        cli._verify_ciphertext_plaintext(
            contract=contract,
            primary_key=4,
            phase="verify-candidate",
            ciphertext=valid_ciphertext,
            expected_plaintext="secret",
        )

    assert "PlaintextMismatch" in mismatch.value.failure.safe_message()


def test_migration_row_skips_null_empty_malformed_and_target_envelope_values(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setenv(
        cli.ENCRYPTED_FIELD_WRITE_FORMAT,
        cli.EncryptedFieldWriteFormat.LEGACY_FERNET.value,
    )
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    null_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )

    assert (
        cli._process_migration_row(
            contract=contract,
            row={"id": 1, "email": None},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=null_report,
        )
        is False
    )
    assert null_report.skipped_rows == 1

    envelope = crypto.serialize_encrypted_field_envelope(
        crypto_module.encrypt_field("already wrapped") or ""
    )
    envelope_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )

    assert (
        cli._process_migration_row(
            contract=contract,
            row={"id": 2, "email": envelope},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=envelope_report,
        )
        is False
    )
    assert envelope_report.already_migrated_rows == 1

    malformed_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with pytest.raises(cli.EncryptedFieldMigrationError, match="MalformedCiphertext"):
        cli._process_migration_row(
            contract=contract,
            row={"id": 3, "email": 123},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=malformed_report,
        )
    assert malformed_report.decrypt_failures == 1


def test_migration_row_decrypt_and_verification_failures_are_counted(
    app: Flask,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]

    invalid_envelope_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with pytest.raises(cli.EncryptedFieldMigrationError) as invalid_envelope:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id, "email": f"{crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX}not-json"},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=invalid_envelope_report,
        )
    assert "phase=classify" in invalid_envelope.value.failure.safe_message()
    assert invalid_envelope_report.decrypt_failures == 1

    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL", TEST_AES_GCM_WRITE_APPROVAL)
    aead_envelope = crypto.encrypt_field_aead_prototype(
        "AAD-bound migration secret",
        contract,
        {"user_id": user.id + 1},
    )
    assert aead_envelope is not None
    aead_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with pytest.raises(cli.EncryptedFieldMigrationError) as aead_failure:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id, "email": aead_envelope},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=aead_report,
        )
    assert "phase=decrypt" in aead_failure.value.failure.safe_message()
    assert "AAD-bound migration secret" not in aead_failure.value.failure.safe_message()
    assert aead_report.decrypt_failures == 1

    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    legacy_ciphertext = crypto_module.encrypt_field("candidate verification secret")
    assert legacy_ciphertext is not None
    monkeypatch.setattr(cli, "_build_target_ciphertext", lambda _plaintext, _format: "not-target")
    verification_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with pytest.raises(cli.EncryptedFieldMigrationError) as verification_failure:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id, "email": legacy_ciphertext},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=verification_report,
        )
    assert "phase=verify-candidate" in verification_failure.value.failure.safe_message()
    assert verification_report.verification_failures == 1


def test_migration_row_skips_decrypted_none_and_reraises_safe_failures(
    app: Flask,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    source_ciphertext = crypto_module.encrypt_field("source secret")
    assert source_ciphertext is not None

    none_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(cli, "decrypt_field", lambda _value: None)
        assert (
            cli._process_migration_row(
                contract=contract,
                row={"id": user.id, "email": source_ciphertext},
                dry_run=True,
                target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
                report=none_report,
            )
            is False
        )
    assert none_report.skipped_rows == 1

    replacement = crypto.serialize_encrypted_field_envelope(source_ciphertext)
    monkeypatch.setattr(cli, "_build_target_ciphertext", lambda _plaintext, _format: replacement)

    def fail_verification(**_kwargs: object) -> None:
        raise cli.EncryptedFieldMigrationError(
            cli.EncryptedFieldMigrationFailure(
                contract_id=contract.id,
                primary_key=user.id,
                phase="verify-candidate",
                error_class="SyntheticVerificationFailure",
            )
        )

    monkeypatch.setattr(cli, "_verify_ciphertext_plaintext", fail_verification)
    reraised_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )
    with pytest.raises(cli.EncryptedFieldMigrationError) as reraised:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id, "email": source_ciphertext},
            dry_run=True,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=reraised_report,
        )

    assert "SyntheticVerificationFailure" in reraised.value.failure.safe_message()
    assert reraised_report.verification_failures == 1


def test_migration_row_live_write_failures_are_counted_and_rolled_back(
    app: Flask,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    app.config[cli.ENCRYPTED_FIELD_WRITE_FORMAT] = cli.EncryptedFieldWriteFormat.LEGACY_FERNET
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    missing_row_ciphertext = crypto_module.encrypt_field("missing row secret")
    assert missing_row_ciphertext is not None
    update_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )

    with pytest.raises(cli.EncryptedFieldMigrationError) as update_failure:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id + 9999, "email": missing_row_ciphertext},
            dry_run=False,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=update_report,
        )
    assert "UnexpectedRowCount" in update_failure.value.failure.safe_message()
    assert update_report.update_failures == 1
    db.session.rollback()

    stored_ciphertext = crypto_module.encrypt_field("post-write verification secret")
    assert stored_ciphertext is not None
    user._email = stored_ciphertext
    db.session.commit()
    monkeypatch.setattr(cli.db.session, "scalar", lambda _statement: None)
    post_write_report = cli.EncryptedFieldMigrationContractReport(
        contract_id=contract.id,
        table=contract.table,
        column=contract.column,
    )

    with pytest.raises(cli.EncryptedFieldMigrationError) as post_write_failure:
        cli._process_migration_row(
            contract=contract,
            row={"id": user.id, "email": stored_ciphertext},
            dry_run=False,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
            report=post_write_report,
        )
    assert "MissingStoredCiphertext" in post_write_failure.value.failure.safe_message()
    assert post_write_report.verification_failures == 1
    db.session.rollback()


def test_preflight_classifier_handles_aes_gcm_decrypt_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL", TEST_AES_GCM_WRITE_APPROVAL)
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    envelope = crypto.encrypt_field_aead_prototype("bound secret", contract, {"user_id": 1})
    assert envelope is not None

    assert (
        cli._classify_preflight_value(envelope, contract=contract, aad_values={"user_id": 2})
        == "decrypt_failure"
    )


def test_migration_batch_and_preflight_scans_skip_missing_schema(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    monkeypatch.setattr(
        cli,
        "_encrypted_field_column_capacity_reports",
        lambda: [
            cli.EncryptedFieldCapacityReport(
                contract_id=contract.id,
                table=contract.table,
                column=contract.column,
                ready=False,
                detail="length 255",
            )
        ],
    )

    with pytest.raises(click.ClickException, match="schema not ready"):
        cli._run_encrypted_field_migration_batch(
            contracts=(contract,),
            dry_run=True,
            batch_size=1,
            resume_state=None,
            full_scan=False,
            target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
        )

    class SparseInspector:
        def get_columns(self, table_name: str) -> list[dict[str, object]]:
            _ = self
            if table_name == "missing_table":
                raise NoSuchTableError(table_name)
            if table_name == "metadata_missing_table":
                return [{"name": "secret", "type": String(length=512)}]
            return [{"name": "id", "type": String(length=512)}]

    monkeypatch.setattr(cli, "inspect", lambda _engine: SparseInspector())
    missing_table_contract = crypto.EncryptedFieldContract(
        id="Missing.secret",
        domain="hushline.encrypted-field.missing.secret",
        table="missing_table",
        column="secret",
        aad_fields=("user_id",),
    )
    missing_column_contract = crypto.EncryptedFieldContract(
        id="User.missing_secret",
        domain="hushline.encrypted-field.users.missing_secret",
        table="users",
        column="missing_secret",
        aad_fields=("user_id",),
    )
    metadata_missing_contract = crypto.EncryptedFieldContract(
        id="MissingMetadata.secret",
        domain="hushline.encrypted-field.missing-metadata.secret",
        table="metadata_missing_table",
        column="secret",
        aad_fields=("user_id",),
    )

    assert (
        cli._classify_encrypted_field_values(
            contracts=(missing_table_contract, missing_column_contract, metadata_missing_contract),
            batch_size=1,
        )
        == []
    )


def test_migration_batch_resume_skips_prior_contracts_and_stops_at_batch_size(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = app
    first_contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.totp_secret"]
    second_contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    contract_ids = (first_contract.id, second_contract.id)
    processed_rows: list[tuple[str, int]] = []

    monkeypatch.setattr(
        cli,
        "_encrypted_field_column_capacity_reports",
        lambda: [
            cli.EncryptedFieldCapacityReport(
                contract_id=contract_id,
                table="users",
                column="encrypted",
                ready=True,
                detail="unbounded",
            )
            for contract_id in contract_ids
        ],
    )

    class ExtraRows:
        def mappings(self) -> list[dict[str, object]]:
            return [
                {"id": 10, "email": "ciphertext"},
                {"id": 11, "email": "ciphertext"},
            ]

    def record_row(**kwargs: object) -> None:
        contract = kwargs["contract"]
        row = kwargs["row"]
        report = kwargs["report"]
        assert isinstance(contract, crypto.EncryptedFieldContract)
        assert isinstance(row, dict)
        assert isinstance(report, cli.EncryptedFieldMigrationContractReport)
        processed_rows.append((contract.id, int(row["id"])))
        report.examined_rows += 1
        report.last_processed_primary_key = int(row["id"])

    monkeypatch.setattr(cli.db.session, "execute", lambda _statement: ExtraRows())
    monkeypatch.setattr(cli.db.session, "rollback", lambda: None)
    monkeypatch.setattr(cli, "_process_migration_row", record_row)
    monkeypatch.setattr(cli, "_remaining_legacy_rows", lambda _contract: 1)
    resume_state = cli.EncryptedFieldMigrationResumeState(
        helper_version=cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
        batch_size=1,
        contract_ids=contract_ids,
        contract_id=second_contract.id,
        last_primary_key=9,
    )

    reports, next_resume_state = cli._run_encrypted_field_migration_batch(
        contracts=(first_contract, second_contract),
        dry_run=True,
        batch_size=1,
        resume_state=resume_state,
        full_scan=False,
        target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET,
    )

    assert processed_rows == [(second_contract.id, 10)]
    assert reports[0].examined_rows == 0
    assert reports[1].last_processed_primary_key == 10
    assert next_resume_state == cli.EncryptedFieldMigrationResumeState(
        helper_version=cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
        target_format=cli.EncryptedFieldWriteFormat.ENVELOPE_FERNET.value,
        batch_size=1,
        contract_ids=contract_ids,
        contract_id=second_contract.id,
        last_primary_key=10,
    )


def test_preflight_and_release_gate_errors_report_legacy_and_blocked_artifacts() -> None:
    assert cli._preflight_human_reason_phrases(
        [{"code": "legacy_fernet_present", "contract_ids": ["User.email"]}]
    ) == ["legacy Fernet ciphertext values are present"]

    contract_ids = [contract.id for contract in crypto.ENCRYPTED_FIELD_CONTRACTS]
    errors = cli._release_gate_preflight_errors(
        {
            "contract_set": {
                "contract_ids": contract_ids,
                "version": cli.ENCRYPTED_FIELD_CONTRACT_SET_VERSION,
            },
            "contracts": [
                {
                    "contract_id": contract_id,
                    "status": "blocked" if index == 0 else "ready",
                }
                for index, contract_id in enumerate(contract_ids)
            ],
            "helper_version": cli.ENCRYPTED_FIELD_MIGRATION_HELPER_VERSION,
            "report_type": "encrypted-field-preflight",
            "schema_revision": cli.ENCRYPTED_FIELD_PREFLIGHT_SCHEMA_REVISION,
            "status": "ready",
            "totals": {
                "decrypt_failures": 0,
                "malformed": 1,
                "rows_scanned": 3,
                "rows_total": 3,
            },
        }
    )

    assert errors == [
        "preflight artifact must have zero malformed values",
        "preflight artifact contains blocked contract results",
    ]


def test_migrate_command_rejects_unsupported_gate_modes(app: Flask, tmp_path: Path) -> None:
    runner = app.test_cli_runner()
    preflight_artifact = tmp_path / "preflight.json"
    preflight_artifact.write_text("{}", encoding="utf-8")

    invalid_target = runner.invoke(
        args=["encrypted-field", "migrate", "--target-format", "not-a-format"]
    )
    unsupported_target = runner.invoke(
        args=["encrypted-field", "migrate", "--target-format", "legacy-fernet"]
    )
    artifact_without_production = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--preflight-artifact",
            str(preflight_artifact),
        ]
    )
    production_dry_run = runner.invoke(args=["encrypted-field", "migrate", "--production"])

    assert invalid_target.exit_code == 1
    assert "Not a valid value for EncryptedFieldWriteFormat" in invalid_target.output
    assert unsupported_target.exit_code == 1
    assert "only supports target format envelope-fernet" in unsupported_target.output
    assert artifact_without_production.exit_code == 1
    assert "Production gate artifacts are only accepted with --production" in (
        artifact_without_production.output
    )
    assert production_dry_run.exit_code == 1
    assert "Production mode is only valid for --live" in production_dry_run.output


def test_release_gate_preflight_errors_cover_malformed_artifacts() -> None:
    errors = cli._release_gate_preflight_errors(
        {
            "contract_set": "not-a-dict",
            "contracts": [{"contract_id": "User.email", "status": "blocked"}],
            "helper_version": "wrong-helper",
            "report_type": "wrong-report",
            "schema_revision": 0,
            "status": "blocked",
            "totals": "not-a-dict",
        }
    )

    assert errors == [
        "preflight artifact report_type must be encrypted-field-preflight",
        "preflight artifact status must be ready",
        "preflight artifact helper_version does not match this release",
        "preflight artifact schema_revision does not match this release",
        "preflight artifact contract_set version does not match this release",
        "preflight artifact must cover every encrypted-field contract",
        "preflight artifact totals must be present",
        "preflight artifact contract details must cover every encrypted-field contract",
    ]


def test_release_gate_manifest_requires_maintainer_approver() -> None:
    manifest: dict[str, Any] = {"approval": {"approved_by": []}}

    assert "approval.approved_by must list at least one maintainer" in (
        cli._release_gate_manifest_errors(manifest)
    )

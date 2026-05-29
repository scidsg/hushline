import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from hushline import crypto
from hushline.cli_encrypted_field import EncryptedFieldCapacityReport
from hushline.config import (
    ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL,
    ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED,
    ENCRYPTED_FIELD_WRITE_FORMAT,
    EncryptedFieldWriteFormat,
)
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, Tier, User

TEST_ENCRYPTION_KEY = "jY0gDbATEOQolx2SGj46YnkkbN6HQBB4YCABzwl1H1A="
TEST_AES_GCM_WRITE_APPROVAL = "test maintainer approval for AES-GCM encrypted-field writes"


def _enable_aes_gcm_writes(app: Flask) -> None:
    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_AES_GCM
    app.config[ENCRYPTED_FIELD_AES_GCM_WRITES_ENABLED] = True
    app.config[ENCRYPTED_FIELD_AES_GCM_WRITE_APPROVAL] = TEST_AES_GCM_WRITE_APPROVAL


def _valid_encrypted_field_release_gate_manifest() -> dict[str, object]:
    return {
        "approval": {
            "approved_at": "2026-05-27T00:00:00Z",
            "approved_by": ["Maintainer One"],
            "maintainer_approved": True,
            "reference": "reviewed release approval record",
        },
        "backup_restore_rehearsal": {
            "artifact": "redacted backup restore rehearsal artifact",
            "completed": True,
            "matching_key_material_verified": True,
        },
        "contract_set_version": "encrypted-field-contracts-v1",
        "dry_run": {
            "artifact": "redacted dry-run artifact",
            "artifact_archived": True,
            "completed": True,
            "exit_status_zero": True,
        },
        "emergency_rollback": {
            "destructive_down_migration_required": False,
            "dual_reader_remains_deployed": True,
            "new_writes_can_revert_to_legacy": True,
        },
        "gate_version": 1,
        "helper_version": "encrypted-field-migration-v1",
        "interruption_resume_rehearsal": {
            "already_migrated_rows_skipped": True,
            "artifact": "redacted interruption and resume artifact",
            "completed": True,
            "remaining_rows_continued": True,
        },
        "live_batch_rehearsal": {
            "artifact": "redacted live-batch rehearsal artifact",
            "completed": True,
        },
        "preflight_artifact": "redacted preflight artifact",
        "rehearsal_report": "docs/ENCRYPTED-FIELD-RESTORED-BACKUP-REHEARSAL-REPORT.md",
        "release_checks": {
            "ciphertext_fit_tests_passed": True,
            "migration_tests_passed": True,
        },
        "report_type": "encrypted-field-production-release-gate",
        "rollback_rehearsal": {
            "artifact": "redacted rollback rehearsal artifact",
            "completed": True,
            "legacy_reads_verified": True,
            "old_reader_preserved": True,
            "target_reads_verified": True,
        },
        "target_format": "envelope-fernet",
        "zero_downtime": {
            "bounded_batches": True,
            "no_full_table_rewrite": True,
            "planned_downtime": False,
        },
    }


def test_reg_settings_command_outputs_current_values(app: Flask) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["reg", "settings"])

    assert result.exit_code == 0
    assert "Registration Enabled: False" in result.output
    assert "Registration Codes Required: True" in result.output


def test_reg_toggle_commands_update_org_settings(app: Flask) -> None:
    runner = app.test_cli_runner()

    result_enabled = runner.invoke(args=["reg", "registration-enabled", "true"])
    result_codes = runner.invoke(args=["reg", "registration-codes-required", "true"])

    assert result_enabled.exit_code == 0
    assert result_codes.exit_code == 0
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED) is True
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_CODES_REQUIRED) is True


def test_reg_code_commands_create_list_and_delete(app: Flask) -> None:
    runner = app.test_cli_runner()

    empty_result = runner.invoke(args=["reg", "code-list"])
    assert empty_result.exit_code == 0
    assert "No invite codes found." in empty_result.output

    create_result = runner.invoke(args=["reg", "code-create"])
    assert create_result.exit_code == 0
    assert "Invite code " in create_result.output
    assert " created." in create_result.output

    invite_code = db.session.scalar(db.select(InviteCode))
    assert invite_code is not None

    listed_result = runner.invoke(args=["reg", "code-list"])
    assert listed_result.exit_code == 0
    assert invite_code.code in listed_result.output

    delete_result = runner.invoke(args=["reg", "code-delete", invite_code.code])
    assert delete_result.exit_code == 0
    assert f"Invite code {invite_code.code} deleted." in delete_result.output
    assert db.session.scalar(db.select(InviteCode).filter_by(code=invite_code.code)) is None

    missing_result = runner.invoke(args=["reg", "code-delete", "does-not-exist"])
    assert missing_result.exit_code == 0
    assert "Invite code not found." in missing_result.output


def test_reg_code_create_avoids_dash_prefixed_codes(app: Flask) -> None:
    runner = app.test_cli_runner()

    with patch(
        "hushline.model.invite_code.secrets.token_urlsafe",
        side_effect=["-dashprefixed", "safe-code-token"],
    ):
        create_result = runner.invoke(args=["reg", "code-create"])

    assert create_result.exit_code == 0
    invite_code = db.session.scalar(db.select(InviteCode))
    assert invite_code is not None
    assert invite_code.code == "safe-code-token"
    assert not invite_code.code.startswith("-")

    delete_result = runner.invoke(args=["reg", "code-delete", invite_code.code])
    assert delete_result.exit_code == 0
    assert f"Invite code {invite_code.code} deleted." in delete_result.output


def test_encrypted_field_preflight_reports_ready_without_sensitive_values(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET
    user._totp_secret = crypto.encrypt_field("preflight legacy secret")
    legacy_ciphertext = user._totp_secret
    assert legacy_ciphertext is not None

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    user._email = crypto.encrypt_field("preflight envelope secret")
    envelope_ciphertext = user._email
    assert envelope_ciphertext is not None
    db.session.commit()

    result = runner.invoke(args=["encrypted-field", "preflight"])

    assert result.exit_code == 0
    revision_lines = [
        line for line in result.output.splitlines() if line.startswith("Current Alembic revision: ")
    ]
    assert len(revision_lines) == 1
    assert revision_lines[0] != "Current Alembic revision: "
    assert "User.totp_secret (users.totp_secret): ready" in result.output
    assert "User.email (users.email): legacy Fernet: 0; envelope Fernet: 1" in result.output
    assert "User.totp_secret (users.totp_secret): legacy Fernet: 1" in result.output
    assert "malformed: 0; decrypt failures: 0; decryptable: yes" in result.output
    assert "Encrypted-field preflight readiness: ready" in result.output
    assert "preflight legacy secret" not in result.output
    assert "preflight envelope secret" not in result.output
    assert legacy_ciphertext not in result.output
    assert envelope_ciphertext not in result.output

    db.session.refresh(user)
    assert user._totp_secret == legacy_ciphertext
    assert user._email == envelope_ciphertext


def test_encrypted_field_preflight_accepts_aes_gcm_envelopes_with_aad(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "preflight AES-GCM secret"
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    assert user.id is not None

    _enable_aes_gcm_writes(app)
    user._email = crypto.encrypt_field(
        plaintext,
        contract=contract,
        aad_values={"user_id": user.id},
    )
    aead_ciphertext = user._email
    assert aead_ciphertext is not None
    db.session.commit()

    result = runner.invoke(args=["encrypted-field", "preflight", "--contract", "User.email"])

    assert result.exit_code == 0
    assert "User.email (users.email): legacy Fernet: 0; envelope Fernet: 0" in result.output
    assert "envelope AES-GCM: 1" in result.output
    assert "malformed: 0; decrypt failures: 0; decryptable: yes" in result.output
    assert "Encrypted-field preflight readiness: ready" in result.output
    assert plaintext not in result.output
    assert aead_ciphertext not in result.output


def test_encrypted_field_preflight_json_reports_deterministic_redacted_artifact(
    app: Flask, user: User, user2: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    first_plaintext = "json preflight legacy secret"
    second_plaintext = "json preflight envelope secret"

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET
    user._totp_secret = crypto.encrypt_field(first_plaintext)
    legacy_ciphertext = user._totp_secret
    assert legacy_ciphertext is not None

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    user2._totp_secret = crypto.encrypt_field(second_plaintext)
    envelope_ciphertext = user2._totp_secret
    assert envelope_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--output",
            "json",
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "1",
        ]
    )

    assert result.exit_code == 0
    report = json.loads(result.output)
    assert list(report) == [
        "alembic_revision",
        "blocked_reasons",
        "contract_set",
        "contracts",
        "helper_version",
        "report_type",
        "scan",
        "schema_revision",
        "status",
        "totals",
    ]
    assert report["schema_revision"] == 1
    assert report["contract_set"] == {
        "contract_ids": ["User.totp_secret"],
        "version": "encrypted-field-contracts-v1",
    }
    assert report["scan"] == {"batch_size": 1}
    assert report["status"] == "ready"
    assert report["blocked_reasons"] == []
    assert report["totals"] == {
        "decrypt_failures": 0,
        "envelope_aes_gcm": 0,
        "envelope_fernet": 1,
        "legacy_fernet": 1,
        "malformed": 0,
        "null_empty": 0,
        "rows_scanned": 2,
        "rows_total": 2,
    }
    assert report["contracts"] == [
        {
            "capacity": {"detail": "unbounded", "ready": True},
            "column": "totp_secret",
            "contract_id": "User.totp_secret",
            "failures": {"decrypt_failures": 0, "malformed": 0},
            "rows": {
                "envelope_aes_gcm": 0,
                "envelope_fernet": 1,
                "legacy_fernet": 1,
                "null_empty": 0,
                "scanned": 2,
                "total": 2,
            },
            "status": "ready",
            "table": "users",
        }
    ]
    assert first_plaintext not in result.output
    assert second_plaintext not in result.output
    assert legacy_ciphertext not in result.output
    assert envelope_ciphertext not in result.output
    assert "User.email" not in result.output


def test_encrypted_field_preflight_require_no_legacy_blocks_legacy_rows(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "legacy retirement secret"

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.LEGACY_FERNET
    user._totp_secret = crypto.encrypt_field(plaintext)
    legacy_ciphertext = user._totp_secret
    assert legacy_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--output",
            "json",
            "--contract",
            "User.totp_secret",
            "--require-no-legacy",
        ]
    )

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["status"] == "blocked"
    assert report["blocked_reasons"] == [
        {"code": "legacy_fernet_present", "contract_ids": ["User.totp_secret"]}
    ]
    assert report["scan"] == {"batch_size": 1000, "require_no_legacy": True}
    assert report["totals"]["legacy_fernet"] == 1
    assert report["contracts"][0]["status"] == "blocked"
    assert plaintext not in result.output
    assert legacy_ciphertext not in result.output


def test_encrypted_field_preflight_require_no_legacy_accepts_envelopes(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "retired legacy read secret"

    app.config[ENCRYPTED_FIELD_WRITE_FORMAT] = EncryptedFieldWriteFormat.ENVELOPE_FERNET
    user._totp_secret = crypto.encrypt_field(plaintext)
    envelope_ciphertext = user._totp_secret
    assert envelope_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--contract",
            "User.totp_secret",
            "--require-no-legacy",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy read retirement check: require zero legacy Fernet rows" in result.output
    assert "User.totp_secret (users.totp_secret): legacy Fernet: 0" in result.output
    assert "Legacy read retirement check: ready" in result.output
    assert plaintext not in result.output
    assert envelope_ciphertext not in result.output


def test_encrypted_field_preflight_blocks_malformed_ciphertext(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    user._totp_secret = "not-a-valid-fernet-token"
    db.session.commit()

    result = runner.invoke(args=["encrypted-field", "preflight"])

    assert result.exit_code == 1
    assert "User.totp_secret (users.totp_secret): legacy Fernet: 0" in result.output
    assert "malformed: 1; decrypt failures: 1; decryptable: no" in result.output
    assert "Encrypted-field preflight readiness: blocked" in result.output
    assert "malformed ciphertext values are present" in result.output
    assert "not-a-valid-fernet-token" not in result.output


def test_encrypted_field_preflight_json_blocks_malformed_without_sensitive_values(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    malformed_ciphertext = "not-a-valid-fernet-token"
    user._totp_secret = malformed_ciphertext
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--output",
            "json",
            "--contract",
            "User.totp_secret",
        ]
    )

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["status"] == "blocked"
    assert report["blocked_reasons"] == [
        {"code": "malformed_ciphertext", "contract_ids": ["User.totp_secret"]},
        {"code": "decryptability_failure", "contract_ids": ["User.totp_secret"]},
    ]
    assert report["totals"]["malformed"] == 1
    assert report["totals"]["decrypt_failures"] == 1
    assert report["contracts"][0]["failures"] == {
        "decrypt_failures": 1,
        "malformed": 1,
    }
    assert malformed_ciphertext not in result.output


def test_encrypted_field_preflight_json_blocks_decrypt_failures_without_malformed_count(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    undecryptable_envelope = crypto.serialize_encrypted_field_envelope(
        "gAAAAABnot-a-decryptable-fernet-token"
    )
    user._totp_secret = undecryptable_envelope
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--output",
            "json",
            "--contract",
            "User.totp_secret",
        ]
    )

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["status"] == "blocked"
    assert report["blocked_reasons"] == [
        {"code": "decryptability_failure", "contract_ids": ["User.totp_secret"]}
    ]
    assert report["totals"]["malformed"] == 0
    assert report["totals"]["decrypt_failures"] == 1
    assert report["contracts"][0]["failures"] == {
        "decrypt_failures": 1,
        "malformed": 0,
    }
    assert undecryptable_envelope not in result.output


def test_encrypted_field_preflight_blocks_schema_that_is_not_envelope_ready(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = app.test_cli_runner()
    monkeypatch.setattr(
        "hushline.cli_encrypted_field._encrypted_field_column_capacity_reports",
        lambda contracts=None: [
            EncryptedFieldCapacityReport(
                contract_id="User.email",
                table="users",
                column="email",
                ready=False,
                detail="length 255",
            )
        ],
    )

    result = runner.invoke(args=["encrypted-field", "preflight", "--contract", "User.email"])

    assert result.exit_code == 1
    assert "User.email (users.email): blocked (length 255)" in result.output
    assert "Encrypted-field preflight readiness: blocked" in result.output
    assert "schema is not envelope-ready" in result.output


def test_encrypted_field_preflight_blocks_missing_schema_without_crashing(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = app.test_cli_runner()
    monkeypatch.setattr(
        "hushline.cli_encrypted_field.ENCRYPTED_FIELD_CONTRACTS",
        (
            crypto.EncryptedFieldContract(
                id="User.missing_column",
                domain="hushline.encrypted-field.users.missing_column",
                table="users",
                column="missing_column",
                aad_fields=("user_id",),
            ),
        ),
    )

    result = runner.invoke(args=["encrypted-field", "preflight"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "User.missing_column (users.missing_column): blocked (missing column)" in (result.output)
    assert "Encrypted-field preflight readiness: blocked" in result.output
    assert "schema is not envelope-ready" in result.output


def test_encrypted_field_preflight_json_blocks_missing_schema_without_crashing(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = app.test_cli_runner()
    monkeypatch.setattr(
        "hushline.cli_encrypted_field.ENCRYPTED_FIELD_CONTRACTS",
        (
            crypto.EncryptedFieldContract(
                id="User.missing_column",
                domain="hushline.encrypted-field.users.missing_column",
                table="users",
                column="missing_column",
                aad_fields=("user_id",),
            ),
        ),
    )

    result = runner.invoke(
        args=["encrypted-field", "preflight", "--output", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["status"] == "blocked"
    assert report["blocked_reasons"] == [
        {"code": "missing_schema", "contract_ids": ["User.missing_column"]}
    ]
    assert report["contracts"][0] == {
        "capacity": {"detail": "missing column", "ready": False},
        "column": "missing_column",
        "contract_id": "User.missing_column",
        "failures": {"decrypt_failures": 0, "malformed": 0},
        "rows": {
            "envelope_aes_gcm": 0,
            "envelope_fernet": 0,
            "legacy_fernet": 0,
            "null_empty": 0,
            "scanned": 0,
            "total": 0,
        },
        "status": "blocked",
        "table": "users",
    }


def test_encrypted_field_release_gate_accepts_ready_redacted_artifacts(
    app: Flask, tmp_path: Path
) -> None:
    runner = app.test_cli_runner()
    preflight_result = runner.invoke(args=["encrypted-field", "preflight", "--output", "json"])
    assert preflight_result.exit_code == 0

    preflight_artifact = tmp_path / "preflight.json"
    evidence_manifest = tmp_path / "release-gate.json"
    preflight_artifact.write_text(preflight_result.output, encoding="utf-8")
    evidence_manifest.write_text(
        json.dumps(_valid_encrypted_field_release_gate_manifest()),
        encoding="utf-8",
    )

    result = runner.invoke(
        args=[
            "encrypted-field",
            "release-gate",
            "--preflight-artifact",
            str(preflight_artifact),
            "--evidence-manifest",
            str(evidence_manifest),
        ]
    )

    assert result.exit_code == 0
    assert "Encrypted-field production release gate: ready" in result.output
    assert "Target format: envelope-fernet" in result.output
    assert "zero planned downtime with bounded batches" in result.output
    assert "dual reader remains deployed; new writes can revert to legacy-fernet" in result.output
    assert "Maintainer One" not in result.output


def test_encrypted_field_release_gate_blocks_targeted_preflight_artifact(
    app: Flask, tmp_path: Path
) -> None:
    runner = app.test_cli_runner()
    preflight_result = runner.invoke(
        args=[
            "encrypted-field",
            "preflight",
            "--output",
            "json",
            "--contract",
            "User.totp_secret",
        ]
    )
    assert preflight_result.exit_code == 0

    preflight_artifact = tmp_path / "targeted-preflight.json"
    evidence_manifest = tmp_path / "release-gate.json"
    preflight_artifact.write_text(preflight_result.output, encoding="utf-8")
    evidence_manifest.write_text(
        json.dumps(_valid_encrypted_field_release_gate_manifest()),
        encoding="utf-8",
    )

    result = runner.invoke(
        args=[
            "encrypted-field",
            "release-gate",
            "--preflight-artifact",
            str(preflight_artifact),
            "--evidence-manifest",
            str(evidence_manifest),
        ]
    )

    assert result.exit_code == 1
    assert "Encrypted-field production release gate: blocked" in result.output
    assert "preflight artifact must cover every encrypted-field contract" in result.output


def test_encrypted_field_release_gate_blocks_weakened_rollback_safety(
    app: Flask, tmp_path: Path
) -> None:
    runner = app.test_cli_runner()
    preflight_result = runner.invoke(args=["encrypted-field", "preflight", "--output", "json"])
    assert preflight_result.exit_code == 0

    manifest = _valid_encrypted_field_release_gate_manifest()
    emergency_rollback = manifest["emergency_rollback"]
    assert isinstance(emergency_rollback, dict)
    emergency_rollback["new_writes_can_revert_to_legacy"] = False
    preflight_artifact = tmp_path / "preflight.json"
    evidence_manifest = tmp_path / "release-gate.json"
    preflight_artifact.write_text(preflight_result.output, encoding="utf-8")
    evidence_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    result = runner.invoke(
        args=[
            "encrypted-field",
            "release-gate",
            "--preflight-artifact",
            str(preflight_artifact),
            "--evidence-manifest",
            str(evidence_manifest),
        ]
    )

    assert result.exit_code == 1
    assert "Encrypted-field production release gate: blocked" in result.output
    assert "emergency_rollback.new_writes_can_revert_to_legacy must be True" in result.output


def test_encrypted_field_release_gate_requires_rehearsal_report_reference(
    app: Flask, tmp_path: Path
) -> None:
    runner = app.test_cli_runner()
    preflight_result = runner.invoke(args=["encrypted-field", "preflight", "--output", "json"])
    assert preflight_result.exit_code == 0

    manifest = _valid_encrypted_field_release_gate_manifest()
    del manifest["rehearsal_report"]
    preflight_artifact = tmp_path / "preflight.json"
    evidence_manifest = tmp_path / "release-gate.json"
    preflight_artifact.write_text(preflight_result.output, encoding="utf-8")
    evidence_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    result = runner.invoke(
        args=[
            "encrypted-field",
            "release-gate",
            "--preflight-artifact",
            str(preflight_artifact),
            "--evidence-manifest",
            str(evidence_manifest),
        ]
    )

    assert result.exit_code == 1
    assert "Encrypted-field production release gate: blocked" in result.output
    assert "rehearsal_report must be a non-empty string" in result.output


def _write_valid_encrypted_field_release_gate_artifacts(
    app: Flask,
    tmp_path: Path,
) -> tuple[Path, Path]:
    runner = app.test_cli_runner()
    preflight_result = runner.invoke(args=["encrypted-field", "preflight", "--output", "json"])
    assert preflight_result.exit_code == 0

    preflight_artifact = tmp_path / "preflight.json"
    evidence_manifest = tmp_path / "release-gate.json"
    preflight_artifact.write_text(preflight_result.output, encoding="utf-8")
    evidence_manifest.write_text(
        json.dumps(_valid_encrypted_field_release_gate_manifest()),
        encoding="utf-8",
    )
    return preflight_artifact, evidence_manifest


def _next_resume_token(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("Next resume token: "):
            token = line.removeprefix("Next resume token: ")
            assert token != "complete"
            return token
    raise AssertionError("Missing next resume token")


def test_encrypted_field_migrate_dry_run_reports_without_writing(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "dry-run migration secret"
    user._totp_secret = crypto.encrypt_field(plaintext)
    original_ciphertext = user._totp_secret
    assert original_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--dry-run",
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "10",
        ]
    )

    assert result.exit_code == 0
    assert "Mode: dry-run" in result.output
    assert "User.totp_secret (users.totp_secret): status: pending" in result.output
    assert "examined: 1; eligible: 1" in result.output
    assert "would migrate: 1; migrated: 0" in result.output
    assert "remaining rows: 1" in result.output
    assert plaintext not in result.output
    assert original_ciphertext not in result.output
    db.session.refresh(user)
    assert user._totp_secret == original_ciphertext


def test_encrypted_field_migrate_skips_existing_aes_gcm_envelopes(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "already AES-GCM migration secret"
    contract = crypto.ENCRYPTED_FIELD_CONTRACT_BY_ID["User.email"]
    assert user.id is not None

    _enable_aes_gcm_writes(app)
    user._email = crypto.encrypt_field(
        plaintext,
        contract=contract,
        aad_values={"user_id": user.id},
    )
    original_ciphertext = user._email
    assert original_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--dry-run",
            "--contract",
            "User.email",
            "--batch-size",
            "10",
        ]
    )

    assert result.exit_code == 0
    assert "examined: 1; eligible: 0" in result.output
    assert "already migrated: 1" in result.output
    assert "decrypt failures: 0" in result.output
    assert "remaining rows: 0" in result.output
    assert plaintext not in result.output
    assert original_ciphertext not in result.output
    db.session.refresh(user)
    assert user._email == original_ciphertext


def test_encrypted_field_migrate_live_rewrites_and_verifies_post_write(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "live migration secret"
    user._totp_secret = crypto.encrypt_field(plaintext)
    original_ciphertext = user._totp_secret
    assert original_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--live",
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "10",
        ]
    )

    assert result.exit_code == 0
    assert "Mode: live" in result.output
    assert "would migrate: 0; migrated: 1" in result.output
    assert "verification failures: 0; update failures: 0; remaining rows: 0" in result.output
    assert "Next resume token: complete" in result.output
    assert plaintext not in result.output
    assert original_ciphertext not in result.output
    db.session.refresh(user)
    assert user._totp_secret is not None
    assert user._totp_secret.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert user.totp_secret == plaintext


def test_encrypted_field_migrate_production_live_requires_release_gate_artifacts(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "ungated production migration secret"
    user._totp_secret = crypto.encrypt_field(plaintext)
    original_ciphertext = user._totp_secret
    assert original_ciphertext is not None
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--live",
            "--production",
            "--contract",
            "User.totp_secret",
        ]
    )

    assert result.exit_code == 1
    assert "Production live migration requires --preflight-artifact" in result.output
    db.session.refresh(user)
    assert user._totp_secret == original_ciphertext
    assert user.totp_secret == plaintext


def test_encrypted_field_migrate_production_live_accepts_valid_release_gate(
    app: Flask,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    plaintext = "gated production migration secret"
    user._totp_secret = crypto.encrypt_field(plaintext)
    original_ciphertext = user._totp_secret
    assert original_ciphertext is not None
    db.session.commit()
    preflight_artifact, evidence_manifest = _write_valid_encrypted_field_release_gate_artifacts(
        app,
        tmp_path,
    )

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--live",
            "--production",
            "--environment-name",
            "production",
            "--preflight-artifact",
            str(preflight_artifact),
            "--evidence-manifest",
            str(evidence_manifest),
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "10",
        ]
    )

    assert result.exit_code == 0
    assert "Mode: live" in result.output
    assert "Environment: production" in result.output
    assert "migrated: 1" in result.output
    assert plaintext not in result.output
    assert original_ciphertext not in result.output
    db.session.refresh(user)
    assert user._totp_secret is not None
    assert user._totp_secret.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert user.totp_secret == plaintext


def test_encrypted_field_migrate_live_resumes_after_interruption(
    app: Flask, user: User, user2: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    user._totp_secret = crypto.encrypt_field("first resumable secret")
    user2._totp_secret = crypto.encrypt_field("second resumable secret")
    db.session.commit()

    first_result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--live",
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "1",
        ]
    )

    assert first_result.exit_code == 0
    assert "migrated: 1" in first_result.output
    assert "remaining rows: 1" in first_result.output
    resume_token = _next_resume_token(first_result.output)
    db.session.refresh(user)
    db.session.refresh(user2)
    assert user._totp_secret is not None
    assert user._totp_secret.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)
    assert user2._totp_secret is not None
    assert not user2._totp_secret.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)

    second_result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--live",
            "--contract",
            "User.totp_secret",
            "--batch-size",
            "1",
            "--resume-token",
            resume_token,
        ]
    )

    assert second_result.exit_code == 0
    assert "migrated: 1" in second_result.output
    assert "remaining rows: 0" in second_result.output
    assert "Next resume token: complete" in second_result.output
    db.session.refresh(user)
    db.session.refresh(user2)
    assert user.totp_secret == "first resumable secret"
    assert user2.totp_secret == "second resumable secret"
    assert user2._totp_secret is not None
    assert user2._totp_secret.startswith(crypto.ENCRYPTED_FIELD_ENVELOPE_PREFIX)


def test_encrypted_field_migrate_failure_report_omits_sensitive_values(
    app: Flask, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    runner = app.test_cli_runner()
    malformed_ciphertext = "not-a-valid-fernet-token"
    user._totp_secret = malformed_ciphertext
    db.session.commit()

    result = runner.invoke(
        args=[
            "encrypted-field",
            "migrate",
            "--dry-run",
            "--contract",
            "User.totp_secret",
        ]
    )

    assert result.exit_code == 1
    assert "Encrypted-field migration failed: contract=User.totp_secret" in result.output
    assert "phase=decrypt" in result.output
    assert "source_left_unchanged=yes" in result.output
    assert malformed_ciphertext not in result.output


def test_password_hash_report_outputs_legacy_count_and_removal_gate(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(args=["password-hash", "report"])

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert (
        "Legacy verification success counter: "
        "password_hash_verification_success_total hash_format=passlib_scrypt"
    ) in result.output
    assert (
        "Rehash-on-auth counters: password_hash_rehash_on_auth_success_total, "
        "password_hash_rehash_on_auth_failure_total"
    ) in result.output
    assert "legacy rows must stay at 0 for one full release cycle" in result.output
    assert (
        "Current build verification support: passlib $scrypt$ and native prefix-based hashes."
        in result.output
    )
    assert (
        "Measured legacy verification successes: provide --legacy-verification-successes <count>"
        in result.output
    )
    assert "Passlib removal readiness: blocked" in result.output


def test_password_hash_report_blocks_when_measured_legacy_successes_non_zero(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    native_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = native_hash
    user2._password_hash = native_hash
    db.session.commit()

    result = runner.invoke(
        args=[
            "password-hash",
            "report",
            "--legacy-verification-successes",
            "3",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 0" in result.output
    assert "Measured legacy verification successes: 3" in result.output
    assert "Legacy verifier path: passlib_dependency" in result.output
    assert "Passlib removal readiness: blocked" in result.output
    assert "Passlib removal reason: measured legacy verification success volume is non-zero" in (
        result.output
    )


def test_password_hash_can_remove_passlib_blocks_when_legacy_rows_remain(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "0",
        ]
    )

    assert result.exit_code == 1
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert "Measured legacy verification successes: 0" in result.output
    assert "Error: Passlib removal readiness: blocked (legacy passlib scrypt rows remain)" in (
        result.output
    )


def test_password_hash_can_remove_passlib_succeeds_when_legacy_rows_and_volume_are_zero(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    native_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = native_hash
    user2._password_hash = native_hash
    db.session.commit()

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "0",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 0" in result.output
    assert "Measured legacy verification successes: 0" in result.output
    assert "Legacy verifier path: passlib_dependency" in result.output
    assert "Passlib removal readiness: ready" in result.output


def test_password_hash_can_remove_passlib_accepts_reviewed_in_repo_legacy_verifier_path(
    app: Flask, user: User, user2: User, user_password: str
) -> None:
    runner = app.test_cli_runner()
    user._password_hash = generate_password_hash(user_password, method="scrypt")
    db.session.commit()

    assert user2.password_hash.startswith("$scrypt$")

    result = runner.invoke(
        args=[
            "password-hash",
            "can-remove-passlib",
            "--legacy-verification-successes",
            "7",
            "--reviewed-in-repo-legacy-verifier",
        ]
    )

    assert result.exit_code == 0
    assert "Legacy passlib scrypt rows: 1" in result.output
    assert "Measured legacy verification successes: 7" in result.output
    assert "Legacy verifier path: reviewed_in_repo_legacy_verifier" in result.output
    assert "Passlib removal readiness: ready" in result.output


def test_stripe_configure_skips_when_secret_missing(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()

    with (
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    init_stripe.assert_not_called()
    create_products.assert_not_called()


def test_stripe_configure_creates_missing_tiers_when_lookup_returns_none(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()
    db.session.execute(db.delete(Tier))
    db.session.commit()

    with (
        patch("hushline.cli_stripe.Tier.free_tier", return_value=None),
        patch("hushline.cli_stripe.Tier.business_tier", return_value=None),
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    assert db.session.scalar(db.select(Tier).filter_by(name="Free")) is not None
    assert db.session.scalar(db.select(Tier).filter_by(name="Business")) is not None
    init_stripe.assert_not_called()
    create_products.assert_not_called()


def test_stripe_configure_runs_premium_setup_when_secret_present(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    runner = app.test_cli_runner()

    with (
        patch("hushline.cli_stripe.premium.init_stripe") as init_stripe,
        patch("hushline.cli_stripe.premium.create_products_and_prices") as create_products,
    ):
        result = runner.invoke(args=["stripe", "configure"])

    assert result.exit_code == 0
    init_stripe.assert_called_once()
    create_products.assert_called_once()


def test_stripe_start_worker_skips_without_secret(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    runner = app.test_cli_runner()

    with patch.object(app.logger, "error") as logger_error:
        result = runner.invoke(args=["stripe", "start-worker"])

    assert result.exit_code == 0
    logger_error.assert_called_once()


def test_stripe_start_worker_runs_async_worker(app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    runner = app.test_cli_runner()
    worker_coro = object()

    with (
        patch(
            "hushline.cli_stripe.premium.worker", new=MagicMock(return_value=worker_coro)
        ) as worker_mock,
        patch("hushline.cli_stripe.asyncio.run") as asyncio_run,
    ):
        result = runner.invoke(args=["stripe", "start-worker"])

    assert result.exit_code == 0
    worker_mock.assert_called_once_with(app)
    asyncio_run.assert_called_once_with(worker_coro)

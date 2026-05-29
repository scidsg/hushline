from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md"
REHEARSAL_TEMPLATE = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md"
READINESS_REPORT = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-DEPLOYMENT-READINESS.md"


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_encrypted_field_migration_runbook_exists_and_is_linked() -> None:
    feasibility_doc = REPO_ROOT / "docs" / "ISSUE-411-SYMMETRIC-CRYPTO-FEASIBILITY.md"
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    feasibility = feasibility_doc.read_text(encoding="utf-8")

    assert RUNBOOK.is_file()
    assert REHEARSAL_TEMPLATE.is_file()
    assert READINESS_REPORT.is_file()
    assert "ENCRYPTED-FIELD-DEPLOYMENT-READINESS.md" in docs_index
    assert "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md" in docs_index
    assert "ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md" in docs_index
    assert "ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md" in _runbook_text()
    assert "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md" in feasibility
    assert "ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md" in feasibility


def test_encrypted_field_migration_runbook_covers_required_execution_paths() -> None:
    content = _runbook_text()

    for heading in (
        "### Local",
        "### Staging",
        "### Production",
        "## Production Release Gate",
        "## Preflight Checks",
        "## Dry-Run Behavior",
        "## Small-Batch Execution",
        "## Idempotent Resume",
        "## Per-Row Verification",
        "## Backup And Restore Rehearsal",
        "## Progress And Failure Reporting",
        "## Rollback",
    ):
        assert heading in content

    for phrase in (
        "flask encrypted-field preflight --output json",
        "flask encrypted-field release-gate",
        "JSON release-gate artifact",
        "production-release-gate.json",
        "--contract CONTRACT_ID",
        "--batch-size N",
    ):
        assert phrase in content


def test_encrypted_field_migration_runbook_locks_security_guardrails() -> None:
    content = " ".join(_runbook_text().lower().split())

    required_phrases = (
        "keep the dual reader deployed",
        "keep legacy fernet read support enabled",
        "must not edit historical alembic",
        "do not drop, blank, truncate, or overwrite source ciphertext",
        "do not assume a maintenance window",
        "transitional compatibility format",
        "must not be described as domain-bound authenticated field encryption",
        "compatibility evidence rather than production aad evidence",
        "`encrypted_field_aes_gcm_writes_enabled=true`",
        "`encrypted_field_aes_gcm_write_approval` contains that approval reference",
        "not cryptographic aad binding",
        "completed rehearsal evidence report is reviewed",
        "before changing `encrypted_field_write_format` in production",
        "preflight artifact must cover every encrypted-field contract",
        "zero planned downtime",
        "new_writes_can_revert_to_legacy",
        "stop before live mode if any non-empty row cannot be classified or decrypted",
        "dry-run mode must execute the same selection, classification, decryption",
        "skip rows already in the target envelope format after verifying",
        "the replacement plaintext exactly matches the source plaintext",
        "backups without matching encrypted-field key material are not complete",
        "must not include plaintext or full ciphertext",
        "rollback must preserve the old reader",
    )

    for phrase in required_phrases:
        assert phrase in content


def test_encrypted_field_rehearsal_template_captures_required_evidence() -> None:
    content = REHEARSAL_TEMPLATE.read_text(encoding="utf-8").lower()

    required_phrases = (
        "backup restore timestamp",
        "schema revision",
        "preflight artifact location",
        "dry-run artifact location",
        "live-batch artifact location",
        "interruption method",
        "resume completed at",
        "rollback approach rehearsed",
        "operator signoff",
        "production enablement recommendation",
        "production release-gate manifest location",
        "maintainer approval reference",
    )

    for phrase in required_phrases:
        assert phrase in content


def test_encrypted_field_rehearsal_template_forbids_sensitive_values() -> None:
    content = REHEARSAL_TEMPLATE.read_text(encoding="utf-8").lower()

    forbidden_value_phrases = (
        "plaintext disclosures",
        "message bodies",
        "secrets",
        "private keys",
        "tokens of any kind",
        "totp secrets",
        "email passwords",
        "raw encrypted-field secrets",
        "full ciphertext values",
    )

    for phrase in forbidden_value_phrases:
        assert phrase in content


def test_encrypted_field_deployment_readiness_report_captures_release_gate() -> None:
    content = " ".join(READINESS_REPORT.read_text(encoding="utf-8").lower().split())

    required_phrases = (
        "not ready for production encrypted-field write-format enablement "
        "or live data migration",
        "does not enable production envelope writes",
        "does not start a production migration",
        "does not close #2013",
        "a completed restored-backup or staging rehearsal report is reviewed",
        "flask encrypted-field release-gate",
        "no pending review comments, requested changes, failing checks, "
        "or pending required checks",
        "keep `encrypted_field_write_format` unset or set to `legacy-fernet`",
        "phase 12",
        "phase 17",
        "#2063",
        "#2076",
        "downgrade, rollback, preflight, release-gate, dry-run, live-batch",
        "deployment controls remain current after the final branch merge",
        "legacy fernet reads remain supported by the deployed dual reader",
        "does not require a full-table rewrite transaction or planned downtime",
        "source ciphertext is not overwritten until the candidate replacement decrypts",
        "rollback preserves the old reader",
        "coverage-gap, runner-log, or release-gate",
    )

    for phrase in required_phrases:
        assert phrase in content

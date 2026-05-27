from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md"


def _runbook_text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_encrypted_field_migration_runbook_exists_and_is_linked() -> None:
    feasibility_doc = REPO_ROOT / "docs" / "ISSUE-411-SYMMETRIC-CRYPTO-FEASIBILITY.md"
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    feasibility = feasibility_doc.read_text(encoding="utf-8")

    assert RUNBOOK.is_file()
    assert "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md" in docs_index
    assert "ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md" in feasibility


def test_encrypted_field_migration_runbook_covers_required_execution_paths() -> None:
    content = _runbook_text()

    for heading in (
        "### Local",
        "### Staging",
        "### Production",
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
        "JSON release-gate artifact",
        "--contract CONTRACT_ID",
        "--batch-size N",
    ):
        assert phrase in content


def test_encrypted_field_migration_runbook_locks_security_guardrails() -> None:
    content = _runbook_text().lower()

    required_phrases = (
        "keep the dual reader deployed",
        "keep legacy fernet read support enabled",
        "must not edit historical alembic",
        "do not drop, blank, truncate, or overwrite source ciphertext",
        "do not assume a maintenance window",
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

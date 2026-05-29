from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN = REPO_ROOT / "docs" / "OPERATIONAL-KEY-MANAGEMENT-DESIGN.md"


def _design_text() -> str:
    return DESIGN.read_text(encoding="utf-8")


def test_operational_key_management_design_exists_and_is_linked() -> None:
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    feasibility = (REPO_ROOT / "docs" / "ISSUE-411-SYMMETRIC-CRYPTO-FEASIBILITY.md").read_text(
        encoding="utf-8"
    )

    assert DESIGN.is_file()
    assert "OPERATIONAL-KEY-MANAGEMENT-DESIGN.md" in docs_index
    assert "OPERATIONAL-KEY-MANAGEMENT-DESIGN.md" in feasibility


def test_operational_key_management_design_covers_required_topics() -> None:
    content = _design_text()

    for heading in (
        "## Current Secret Expectations",
        "## Recovery Requirements",
        "## Options Evaluated",
        "### Current Environment-Based Secrets",
        "### External Key Service",
        "### Sealed Local Secret",
        "## Multi-Instance Startup And Deploy Constraints",
        "## Decision Record",
    ):
        assert heading in content

    for secret_name in (
        "ENCRYPTION_KEY",
        "ENCRYPTION_KEY_FALLBACKS",
        "SESSION_FERNET_KEY",
        "SECRET_KEY",
    ):
        assert secret_name in content


def test_operational_key_management_design_locks_recommendation_and_guardrails() -> None:
    content = " ".join(_design_text().lower().split())

    required_phrases = (
        "read-only fallback keys for server-side encrypted database fields",
        "new encrypted-field writes always use `encryption_key`",
        "must not be bundled into encrypted-field envelope work",
        "database backup without the matching encrypted-field key material is not a "
        "complete recovery artifact",
        "`encryption_key` is lost and no valid copy exists",
        "unrecoverable through hush line",
        "current hush line encrypted-field storage does not include key identifiers",
        "missing key identifiers are handled by ordered trial decryption",
        "rolling deploys must not mix encrypted-field write keys or fallback-key order",
        "ordered multi-key readers rather than key identifiers",
        "it does not affect recipient pgp keys",
        "rollback behavior",
        "malformed fallback configuration blocks encrypted-field operations",
        "app boot must not create secret rows, mutate schema, generate replacement "
        "production secrets, or opportunistically rewrite encrypted fields",
        "startup-time schema mutation or implicit secret-row creation is explicitly rejected",
        "keep the environment-based operational key model and add explicit read-only "
        "encrypted-field fallback keys",
        "defer external key service and sealed local secret implementation",
        "do not change flask session secret derivation",
    )

    for phrase in required_phrases:
        assert phrase in content

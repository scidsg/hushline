from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATION = REPO_ROOT / "docs" / "PASSWORD-HASH-MODERNIZATION-EVALUATION.md"


def _evaluation_text() -> str:
    return EVALUATION.read_text(encoding="utf-8")


def test_password_hash_modernization_evaluation_exists_and_is_linked() -> None:
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    feasibility = (REPO_ROOT / "docs" / "ISSUE-411-SYMMETRIC-CRYPTO-FEASIBILITY.md").read_text(
        encoding="utf-8"
    )

    assert EVALUATION.is_file()
    assert "PASSWORD-HASH-MODERNIZATION-EVALUATION.md" in docs_index
    assert "PASSWORD-HASH-MODERNIZATION-EVALUATION.md" in feasibility


def test_password_hash_modernization_evaluation_covers_required_decision_points() -> None:
    content = _evaluation_text()

    for heading in (
        "## Current Behavior Reviewed",
        "## Argon2 Evaluation",
        "## Migration Requirements If Recommended Later",
        "## Metrics And Reporting",
        "## Rollback Behavior",
        "## Decision Record",
    ):
        assert heading in content

    for option in (
        "passlib scrypt",
        "Werkzeug scrypt",
        "Argon2id",
        "rehash-on-auth",
    ):
        assert option in content


def test_password_hash_modernization_evaluation_locks_guardrails() -> None:
    content = " ".join(_evaluation_text().lower().split())

    required_phrases = (
        "does not change production authentication behavior",
        "password hashing is separate from encrypted-field modernization",
        "defer argon2 adoption for now",
        "keep the current migration path",
        "verify legacy passlib `$scrypt$` hashes",
        "optionally write pinned werkzeug scrypt",
        "fail closed without mutating the stored password hash",
        "add argon2 verification only inside `hushline/password_hasher.py`",
        "write argon2 only behind an explicit configuration flag",
        "rehash only after successful authentication",
        "never prehash passwords through encrypted-field or vault-derived material",
        "database counts by stored hash format",
        "verification success and failure counters by hash format",
        "reverting to a build that cannot verify argon2 is not a valid rollback",
        "failed rehash-on-auth must leave the original stored hash unchanged",
        "do not adopt argon2 in this issue",
    )

    for phrase in required_phrases:
        assert phrase in content

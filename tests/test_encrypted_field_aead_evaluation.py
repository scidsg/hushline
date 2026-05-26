from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATION = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-AEAD-EVALUATION.md"


def _evaluation_text() -> str:
    return EVALUATION.read_text(encoding="utf-8")


def test_encrypted_field_aead_evaluation_exists_and_is_linked() -> None:
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    feasibility = (REPO_ROOT / "docs" / "ISSUE-411-SYMMETRIC-CRYPTO-FEASIBILITY.md").read_text(
        encoding="utf-8"
    )

    assert EVALUATION.is_file()
    assert "ENCRYPTED-FIELD-AEAD-EVALUATION.md" in docs_index
    assert "ENCRYPTED-FIELD-AEAD-EVALUATION.md" in feasibility


def test_encrypted_field_aead_evaluation_covers_required_options() -> None:
    content = _evaluation_text()

    for option in (
        "Fernet continuation",
        "ChaCha20-Poly1305",
        "AES-GCM",
    ):
        assert option in content

    for heading in (
        "### Nonce Generation And Misuse Resistance",
        "### Dependency Surface And Maintenance Status",
        "### Ciphertext Size And Text Envelope Cost",
        "### FIPS And Deployment Constraints",
        "## Test-Vector Strategy",
        "## Decision Record",
    ):
        assert heading in content


def test_encrypted_field_aead_evaluation_locks_recommendation_and_guardrails() -> None:
    content = " ".join(_evaluation_text().lower().split())

    required_phrases = (
        "defer any production algorithm change and keep fernet",
        "aes-gcm is the preferred future aead candidate",
        "do not add a new crypto dependency",
        "keeping `cryptography` current",
        "does not change production encryption behavior",
        "random 96-bit nonce",
        "wrong domain",
        "wrong row aad",
        "unknown version",
        "unknown algorithm",
        "legacy fernet values and versioned fernet envelopes remain readable",
        "must not contain production secrets",
    )

    for phrase in required_phrases:
        assert phrase in content

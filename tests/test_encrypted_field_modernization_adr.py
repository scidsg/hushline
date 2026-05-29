from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR = REPO_ROOT / "docs" / "ENCRYPTED-FIELD-MODERNIZATION-ADR.md"


def _adr_text() -> str:
    return ADR.read_text(encoding="utf-8")


def test_encrypted_field_modernization_adr_records_write_format_decision() -> None:
    content = " ".join(_adr_text().lower().split())

    required_phrases = (
        "maintainers recorded this decision on 2026-05-26",
        "`envelope-fernet` is a transitional compatibility format only",
        "must not be documented or represented as domain-bound authenticated field encryption",
        "existing production encrypted-field values must not be rewritten",
        "domain-bound aead is required before any best-in-class migration",
        "does not cryptographically bind ciphertext to the encrypted-field contract",
        "`envelope-aes-gcm`: write the `hlfield:` aes-256-gcm envelope",
        "authenticate canonical aad containing the algorithm, envelope version",
        "`encrypted_field_aes_gcm_writes_enabled=true`",
        "`encrypted_field_aes_gcm_write_approval` maintainer approval reference",
    )

    for phrase in required_phrases:
        assert phrase in content


def test_encrypted_field_modernization_adr_aligns_epic_completion_language() -> None:
    content = " ".join(_adr_text().lower().split())

    required_phrases = (
        "epic #2013 is not complete in the existing-ciphertext migration sense",
        "compatibility milestones separate from new-write aad guarantees",
        "require production aead plus migration evidence before existing ciphertext migration",
        "production release gate before any production write-format configuration change",
    )

    for phrase in required_phrases:
        assert phrase in content

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g8-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0007-pq-archive-readiness.md"
G3_READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"
PREREQUISITE_PATHS = {
    "G4": PQ_CHAT_DOCS / "g4-readiness.json",
    "G6": PQ_CHAT_DOCS / "g6-readiness.json",
}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g8_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g8-readiness.json" in index
    assert "adr-0007-pq-archive-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g8_cannot_advance_until_g4_g6_and_archive_design_are_approved() -> None:
    readiness = _readiness()
    prerequisites = {item["gate"]: item for item in readiness["prerequisites"]}

    assert prerequisites.keys() == PREREQUISITE_PATHS.keys()
    for gate, path in PREREQUISITE_PATHS.items():
        prerequisite = prerequisites[gate]
        observed = _readiness(path)

        assert prerequisite["observed_result"] == observed["decision"]
        assert prerequisite["required_result"] == "approved"
        assert prerequisite["satisfied"] is False
        assert observed["decision"] != prerequisite["required_result"]

    archive_design = readiness["archive_design"]
    g3_readiness = _readiness(G3_READINESS_PATH)
    assert archive_design["gate"] == "G3"
    assert archive_design["observed_result"] == g3_readiness["decision"]
    assert archive_design["required_result"] == "approved"
    assert archive_design["satisfied"] is False
    assert g3_readiness["decision"] != archive_design["required_result"]
    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g8_inventory_covers_archive_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "archive-keys-separated-from-protocol-secrets",
        "account-root-wrapped-archive-epoch-keys",
        "normal-unlock-fresh-browser-history",
        "no-pgp-extra-password-recovery-phrase-or-pairing",
        "authenticated-sender-and-recipient-archive-copies-at-send",
        "hybrid-pq-protection-for-every-archive-copy",
        "atomic-complete-copy-write-and-stable-retry",
        "authenticated-archive-envelope-and-context",
        "offline-never-reopened-device-history",
        "no-ratchet-snapshot-in-archive",
        "archive-epoch-rotation-and-retention",
        "participant-authorization-and-copy-inventory",
        "participant-deletion-and-placeholders-across-copies",
        "account-deletion-and-non-resurrection",
        "existing-export-scope-regression",
        "deliberate-plaintext-export-ceremony-and-label",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g8_inventory_covers_required_archive_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "chromium-firefox-webkit-fresh-device-recovery",
        "offline-sender-and-recipient-history",
        "unread-history-with-original-target-device-never-reopened",
        "wrong-password-and-wrong-unlock-root-rejection",
        "forged-archive-envelope-and-ciphertext-rejection",
        "archive-context-key-and-copy-substitution-rejection",
        "atomic-send-retry-and-required-copy-failure-injection",
        "persisted-copy-audit-with-no-classical-only-protected-copy",
        "archive-and-protocol-key-separation",
        "absence-of-archived-ratchet-snapshots",
        "archive-epoch-provisioning-rotation-retention-and-retirement",
        "participant-authorization-and-cross-account-denial",
        "deletion-placeholder-account-deletion-and-non-resurrection",
        "existing-export-scope-and-deliberate-plaintext-distinction",
        "password-change-rewrap-and-password-reset-limitation",
    }


def test_g8_records_archive_compromise_limits_without_overclaiming() -> None:
    claim_limits = {item["id"]: item for item in _readiness()["required_claim_limits"]}

    assert claim_limits.keys() == {
        "stolen-archive-key-exposes-its-retained-scope",
        "archive-rotation-does-not-retroactively-repair-captured-material",
        "ratchet-progress-does-not-revoke-a-stolen-archive-key",
        "browser-and-backup-erasure-is-not-guaranteed",
    }
    assert all(item["status"] == "blocked" for item in claim_limits.values())
    assert all(item["evidence"] is None for item in claim_limits.values())


def test_g8_forbids_unsafe_archive_work_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "archive-key-reused-as-account-device-ratchet-chain-message-or-transport-key",
        "old-ratchet-snapshot-backed-up-in-archive",
        "server-readable-archive-secret",
        "pgp-import-extra-password-recovery-phrase-or-device-pairing",
        "classical-only-sender-recipient-retry-history-or-backup-copy",
        "partial-required-copy-write",
        "unbound-or-unauthenticated-archive-envelope",
        "mutable-ratchet-cloning-to-fresh-browser",
        "wrong-password-or-wrong-root-history-access",
        "cross-participant-or-cross-account-archive-access",
        "deleted-content-resurrection-from-archive-retry-or-backup",
        "silent-existing-export-scope-expansion",
        "unlabelled-plaintext-chat-export",
        "ratchet-progress-revokes-stolen-archive-key-claim",
        "archive-rotation-retroactively-repairs-captured-material-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

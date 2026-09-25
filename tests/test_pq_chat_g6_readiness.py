import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g6-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0005-transactional-browser-state-readiness.md"
G3_READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g6_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g6-readiness.json" in index
    assert "adr-0005-transactional-browser-state-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisite"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g6_cannot_advance_until_g3_is_approved() -> None:
    readiness = _readiness()
    prerequisite = readiness["prerequisite"]
    g3_readiness = _readiness(G3_READINESS_PATH)

    assert prerequisite["gate"] == "G3"
    assert prerequisite["artifact_commit"] == readiness["repository_baseline"]
    assert prerequisite["observed_result"] == g3_readiness["decision"]
    assert prerequisite["satisfied"] is False
    assert g3_readiness["decision"] != prerequisite["required_result"]
    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g6_inventory_covers_transactional_state_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "encrypted-device-scoped-indexeddb-adapter",
        "approved-persisted-state-allowlist",
        "session-only-unlock-material",
        "atomic-send-state-ciphertext-and-logical-id",
        "durable-outbox-unchanged-byte-retry",
        "atomic-receive-advance-deduplication-and-archive",
        "bounded-skipped-keys-and-pending-state",
        "cross-tab-worker-serialization-and-fencing",
        "abrupt-owner-termination-and-lock-expiration",
        "quota-private-browsing-and-storage-exception-handling",
        "reload-logout-and-storage-clear-behavior",
        "fresh-browser-fresh-session-and-stale-restore-rejection",
        "unchanged-everyday-unlock-ux",
        "complete-copy-pq-confidentiality-regression",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g6_inventory_covers_required_fault_and_browser_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "transaction-and-network-boundary-fault-injection",
        "simultaneous-tab-and-worker-sends",
        "abrupt-tab-and-worker-termination",
        "lock-expiration-takeover-and-fencing",
        "offline-retry-with-unchanged-ciphertext",
        "receive-replay-deduplication-and-archive-atomicity",
        "skipped-key-and-pending-state-bounds",
        "quota-denial-private-browsing-and-storage-exceptions",
        "reload-logout-unlock-and-cleared-storage-regressions",
        "corrupt-and-known-stale-snapshot-restores",
        "fresh-browser-fresh-session-establishment",
        "chromium-firefox-and-webkit-evidence",
        "accessibility-performance-csp-ux-and-complete-copy-regression",
    }


def test_g6_records_required_claim_limits_without_overstating_guarantees() -> None:
    claim_limits = {item["id"]: item for item in _readiness()["required_claim_limits"]}

    assert claim_limits.keys() == {
        "undetectable-browser-storage-rollback",
        "javascript-wasm-memory-erasure",
    }
    assert all(item["status"] == "blocked" for item in claim_limits.values())
    assert all(item["evidence"] is None for item in claim_limits.values())


def test_g6_forbids_unsafe_interim_implementation_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "plaintext-private-or-session-state-persistence",
        "unlocked-secret-persistence-outside-authorized-session",
        "server-readable-session-backup",
        "send-advance-before-durable-outbox-commit",
        "retry-with-regenerated-ciphertext",
        "non-atomic-receive-advance-deduplication-or-archive",
        "unbounded-skipped-keys-or-pending-state",
        "unserialized-shared-ratchet-advance",
        "unfenced-write-by-expired-lock-owner",
        "stale-state-send-after-storage-loss-or-restore",
        "mutable-ratchet-cloning-to-fresh-browser",
        "classical-only-fallback",
        "perfect-browser-secure-deletion-or-rollback-detection-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

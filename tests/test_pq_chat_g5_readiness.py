import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g5-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0004-device-prekey-readiness.md"
G4_READINESS_PATH = PQ_CHAT_DOCS / "g4-readiness.json"


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g5_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g5-readiness.json" in index
    assert "adr-0004-device-prekey-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisite"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g5_cannot_advance_until_g4_is_approved() -> None:
    readiness = _readiness()
    prerequisite = readiness["prerequisite"]
    g4_readiness = _readiness(G4_READINESS_PATH)

    assert prerequisite["gate"] == "G4"
    assert prerequisite["artifact_commit"] == readiness["repository_baseline"]
    assert prerequisite["observed_result"] == g4_readiness["decision"]
    assert prerequisite["satisfied"] is False
    assert g4_readiness["decision"] != prerequisite["required_result"]
    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g5_inventory_covers_device_and_prekey_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "login-unlock-only-device-enrollment",
        "account-key-continuity-and-signed-membership",
        "capability-binding-and-device-list-freshness",
        "substitution-replay-and-revocation-rejection",
        "documented-server-rollback-and-fork-limits",
        "authenticated-bounded-prekey-publication",
        "atomic-one-time-prekey-claim",
        "bounded-consumption-tombstones",
        "safe-replenishment-and-signed-last-resort-key-rotation",
        "expiry-depletion-and-clock-skew-behavior",
        "creation-publication-and-claim-rate-limits",
        "active-stale-and-tombstone-record-bounds",
        "peer-metadata-minimization",
        "offline-recipient-first-session",
        "accessible-fail-closed-recovery-state",
        "revocation-deletion-and-cleanup",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g5_inventory_covers_required_synthetic_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "concurrent-single-use-prekey-claims",
        "exhausted-expired-consumed-and-revoked-keys",
        "forged-membership-substitution-stale-list-and-cross-account-rejection",
        "authenticated-login-unlock-enrollment",
        "offline-recipient-first-session",
        "replenishment-rotation-and-cleanup",
        "device-publication-and-claim-rate-limits",
        "peer-response-metadata-minimization",
        "accessibility-performance-csp-and-complete-copy-regression",
    }


def test_g5_forbids_unsafe_interim_implementation_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "unauthenticated-device-enrollment",
        "membership-or-capability-substitution",
        "non-atomic-prekey-claim",
        "reusable-one-time-prekey",
        "unbounded-device-prekey-or-tombstone-retention",
        "peer-device-fingerprint-ip-or-personal-label-disclosure",
        "recipient-online-first-session-requirement",
        "classical-only-fallback",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g4-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0003-server-storage-api-readiness.md"
G3_READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g4_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g4-readiness.json" in index
    assert "adr-0003-server-storage-api-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisite"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g4_cannot_advance_until_g3_is_approved() -> None:
    readiness = _readiness()
    prerequisite = readiness["prerequisite"]
    g3_readiness = _readiness(G3_READINESS_PATH)

    assert prerequisite["gate"] == "G3"
    assert prerequisite["artifact_commit"] == readiness["repository_baseline"]
    assert prerequisite["observed_result"] == g3_readiness["decision"]
    assert prerequisite["satisfied"] is False
    assert g3_readiness["decision"] != prerequisite["required_result"]
    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g4_inventory_covers_the_issue_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "reviewed-versioned-schema",
        "device-session-authorization-and-transport-copies",
        "archive-epochs-and-copies",
        "idempotency-and-monotonic-conversation-version",
        "envelope-provenance-context-and-payload-bounds",
        "atomic-all-required-copy-commit",
        "legacy-and-upgraded-read-compatibility",
        "participant-access-and-admin-exclusion",
        "rate-limit-read-state-notification-retention-and-deletion",
        "expansion-backfill-and-safe-rollback",
        "migration-and-security-test-evidence",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g4_forbids_unsafe_interim_implementation() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "relabel-v2-as-pq",
        "classical-only-fallback",
        "partial-copy-commit",
        "destructive-rollback",
        "classical-writes-after-upgraded-traffic",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

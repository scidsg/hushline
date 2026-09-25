import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0002-complete-protocol-design-readiness.md"
G2_EVIDENCE_PATH = PQ_CHAT_DOCS / "g2-evidence.json"


def _readiness() -> dict[str, Any]:
    with READINESS_PATH.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g3_readiness_is_linked_and_records_the_blocked_disposition() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g3-readiness.json" in index
    assert "adr-0002-complete-protocol-design-readiness.md" in index
    assert "Status: **Blocked before design**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False


def test_g3_cannot_advance_while_a_prerequisite_is_unsatisfied() -> None:
    readiness = _readiness()
    prerequisites = readiness["prerequisites"]
    prerequisites_by_gate = {item["gate"]: item for item in prerequisites}
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    with G2_EVIDENCE_PATH.open(encoding="utf-8") as evidence_file:
        g2_evidence = json.load(evidence_file)

    assert prerequisites_by_gate.keys() == {"G1", "G2"}
    assert all(item["artifact_commit"] for item in prerequisites)
    assert all(item["evidence"] for item in prerequisites)
    assert any(not item["satisfied"] for item in prerequisites)
    assert "Status: **Proposed for human approval**" in index
    assert prerequisites_by_gate["G1"]["observed_result"] == ("proposed-for-human-approval")
    assert prerequisites_by_gate["G2"]["observed_result"] == g2_evidence["decision"]
    assert readiness["decision"] not in {"ready-for-review", "approved"}


def test_g3_inventory_covers_every_required_design_and_evidence_area() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "protocol-and-reviewed-suite",
        "library-interfaces",
        "authenticated-envelope-bindings",
        "archive-construction-and-copy-inventory",
        "account-identity-and-device-membership",
        "prekey-lifecycle",
        "state-transactions-and-storage-recovery",
        "password-kdf-and-wrapping-lifecycle",
        "archive-epochs-revocation-reset-and-migration",
        "authentication-deniability-erasure-and-forward-secrecy-claims",
        "key-and-data-flow-diagrams",
        "wire-fixtures",
        "state-transition-tables",
        "failure-matrix",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g3_independent_human_review_remains_pending() -> None:
    reviewers = _readiness()["reviewers"]

    assert {reviewer["role"] for reviewer in reviewers} == {
        "cryptographic engineer",
        "independent design reviewer",
    }
    assert all(reviewer["reviewer"] is None for reviewer in reviewers)
    assert all(reviewer["disposition"] == "pending" for reviewer in reviewers)
    assert all(reviewer["evidence"] is None for reviewer in reviewers)

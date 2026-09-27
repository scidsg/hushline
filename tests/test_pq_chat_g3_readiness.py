import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0002-complete-protocol-design-readiness.md"
G2_EVIDENCE_PATH = PQ_CHAT_DOCS / "g2-evidence.json"
G1_APPROVAL_PATH = PQ_CHAT_DOCS / "g1-approval-record.json"


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
    assert readiness["issue"] == "scidsg/hushline#2398"
    assert readiness["replaces_issue"] == "scidsg/hushline#2368"
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False


def test_g3_cannot_advance_while_a_prerequisite_is_unsatisfied() -> None:
    readiness = _readiness()
    prerequisites = readiness["prerequisites"]
    prerequisites_by_gate = {item["gate"]: item for item in prerequisites}
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    with G2_EVIDENCE_PATH.open(encoding="utf-8") as evidence_file:
        g2_evidence = json.load(evidence_file)
    with G1_APPROVAL_PATH.open(encoding="utf-8") as approval_file:
        g1_approval = json.load(approval_file)

    assert prerequisites_by_gate.keys() == {"G1", "G2"}
    assert all(item["artifact_commit"] for item in prerequisites)
    assert all(item["evidence"] for item in prerequisites)
    assert any(not item["satisfied"] for item in prerequisites)
    assert "Status: **Proposed for human approval**" in index
    assert prerequisites_by_gate["G1"]["issue"] == g1_approval["issue"]
    assert prerequisites_by_gate["G1"]["observed_result"] == g1_approval["decision"]
    assert prerequisites_by_gate["G2"]["issue"] == g2_evidence["issue"]
    assert prerequisites_by_gate["G2"]["observed_result"] == g2_evidence["decision"]
    assert readiness["decision"] not in {"ready-for-review", "approved"}


def test_g3_does_not_treat_the_unexecuted_g2_harness_as_a_passing_prototype() -> None:
    readiness = _readiness()
    with G2_EVIDENCE_PATH.open(encoding="utf-8") as evidence_file:
        g2_evidence = json.load(evidence_file)

    assert g2_evidence["prototype"]["status"] == "implemented-not-executed"
    assert g2_evidence["prototype"]["reference_peer"] == "not_implemented"
    assert g2_evidence["prototype"]["results"] is None
    assert all(scenario["status"] == "not_run" for scenario in g2_evidence["protocol_scenarios"])
    assert readiness["decision"] == "blocked-prerequisites"


def test_g3_records_the_fixed_automation_safeguard_without_claiming_acceptance() -> None:
    readiness = _readiness()
    safeguard = readiness["automation_safeguard"]
    completion = readiness["completion"]

    assert safeguard["issue"] == "scidsg/hushline#2395"
    assert safeguard["satisfied"] is True
    assert safeguard["artifact_commit"] == ("f64157494059066efedb11df0396e5aa0c22745b")
    assert completion["status"] == "open-blocked-on-prerequisites-and-human-review"
    assert completion["acceptance_criteria_complete"] is False
    assert (
        "explicit-maintainer-acceptance-of-exact-deliverable-revision"
        in (completion["blocking_inputs"])
    )


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

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
APPROVAL_PATH = PQ_CHAT_DOCS / "g1-approval-record.json"


def _approval() -> dict[str, Any]:
    with APPROVAL_PATH.open(encoding="utf-8") as approval_file:
        return json.load(approval_file)


def test_g1_approval_record_is_linked_and_pins_the_review_packet() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    approval = _approval()
    review_subject = approval["review_subject"]

    assert "g1-approval-record.json" in index
    assert approval["issue"] == "scidsg/hushline#2396"
    assert approval["replaces_issue"] == "scidsg/hushline#2366"
    assert review_subject["packet_commit"] == ("37abae6e11dd9c0e8306f5e962ae97504f5c0888")
    assert {artifact["path"] for artifact in review_subject["artifacts"]} == {
        "docs/pq-chat/baseline-flows.md",
        "docs/pq-chat/unchanged-ux-contract.md",
        "docs/pq-chat/threat-model.md",
    }

    for artifact in review_subject["artifacts"]:
        artifact_path = REPO_ROOT / artifact["path"]
        observed_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        assert observed_digest == artifact["sha256"]


def test_g1_record_covers_every_required_decision_and_approval_role() -> None:
    approval = _approval()
    decisions = {decision["id"]: decision for decision in approval["decisions"]}
    reviewers = {reviewer["role"]: reviewer for reviewer in approval["reviewers"]}

    assert decisions.keys() == {f"G1-D{number}" for number in range(1, 9)}
    assert reviewers.keys() == {"product-maintainer", "security-reviewer"}
    assert {
        decision_id
        for decision_id, decision in decisions.items()
        if decision["product_authority"] == "approval-required"
    } == {"G1-D1", "G1-D6", "G1-D7", "G1-D8"}
    assert {
        decision_id
        for decision_id, decision in decisions.items()
        if decision["security_authority"] == "approval-required"
    } == {"G1-D2", "G1-D3", "G1-D4", "G1-D5", "G1-D6", "G1-D7"}


def test_g1_record_links_every_acceptance_evidence_area() -> None:
    evidence = _approval()["evidence_inventory"]

    assert evidence.keys() == {
        "baseline_flow_checklist",
        "synthetic_playwright_artifacts",
        "browser_and_storage_support",
        "participant_topology",
        "security_claim_matrix",
        "history_availability",
        "ux_and_performance_budgets",
        "private_browsing_and_storage",
        "trust_and_compromise_boundaries",
        "revocation_and_repair",
    }
    assert all("#" in link for link in evidence.values())


def test_g1_gate_stays_open_without_actual_human_decisions() -> None:
    approval = _approval()
    decisions = approval["decisions"]
    reviewers = approval["reviewers"]
    completion = approval["completion"]

    assert approval["decision"] == "pending-human-approval"
    assert approval["production_changes"] is False
    assert completion["status"] == "open-blocked-on-human-decisions"
    assert completion["acceptance_criteria_complete"] is False
    assert all(decision["product_disposition"] == "pending" for decision in decisions)
    assert all(decision["security_disposition"] == "pending" for decision in decisions)
    assert all(decision["evidence"] is None for decision in decisions)
    assert all(reviewer["reviewer"] is None for reviewer in reviewers)
    assert all(reviewer["disposition"] == "pending" for reviewer in reviewers)
    assert all(reviewer["reviewed_packet_commit"] is None for reviewer in reviewers)
    assert all(reviewer["decided_at_utc"] is None for reviewer in reviewers)
    assert all(reviewer["evidence"] is None for reviewer in reviewers)


def test_g1_evidence_is_synthetic_and_cannot_be_presented_as_human_review() -> None:
    safety = _approval()["evidence_safety"]

    assert safety == {
        "synthetic_only": True,
        "not_user_research": True,
        "not_independent_audit": True,
        "agent_must_not_supply_human_dispositions": True,
    }

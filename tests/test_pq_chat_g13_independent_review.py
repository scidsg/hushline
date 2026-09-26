import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
REVIEW_PATH = PQ_CHAT_DOCS / "g13-independent-review.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0012-independent-review-readiness.md"
PREREQUISITE_PATH = PQ_CHAT_DOCS / "g12-validation-report.json"


def _review(path: Path = REVIEW_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as review_file:
        return json.load(review_file)


def _assert_blocked_without_evidence(items: list[dict[str, Any]]) -> None:
    assert all(item["status"] == "blocked" for item in items)
    assert all(item["evidence"] is None for item in items)


def test_g13_packet_is_linked_without_claiming_review_or_production_change() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    review = _review()

    assert "g13-independent-review.json" in index
    assert "adr-0012-independent-review-readiness.md" in index
    assert "Status: **Blocked before independent review**" in adr
    assert review["decision"] == "blocked-prerequisite-and-human-review"
    assert review["release_approved"] is False
    assert review["production_changes"] is False
    assert review["findings"] == []


def test_g13_cannot_advance_until_g12_has_a_validated_release_candidate() -> None:
    review = _review()
    prerequisite = review["prerequisites"][0]
    observed = _review(PREREQUISITE_PATH)

    assert len(review["prerequisites"]) == 1
    assert prerequisite["gate"] == "G12"
    assert prerequisite["artifact_commit"] == review["repository_baseline"]
    assert prerequisite["observed_result"] == observed["decision"]
    assert prerequisite["required_result"] == "approved"
    assert prerequisite["satisfied"] is False
    assert observed["release_approved"] is False
    assert review["decision"] != prerequisite["required_result"]


def test_g13_keeps_booking_review_subject_and_release_decision_human_owned() -> None:
    review = _review()
    engagement = review["review_engagement"]
    subject = review["review_subject"]
    gate = review["release_gate"]

    assert engagement["status"] == "pending-human-booking"
    assert all(
        engagement[field] is None
        for field in (
            "engagement_owner",
            "independent_reviewer",
            "review_organization",
            "independence_and_conflict_attestation",
            "scope_accepted_at_utc",
            "scheduled_start_at_utc",
            "scheduled_final_assessment_at_utc",
            "scheduled_retest_window",
            "secure_reporting_channel",
            "booking_evidence",
        )
    )
    assert "Book before" in engagement["required_timing"]
    assert "exact pinned release candidate" in engagement["required_timing"]

    assert subject["status"] == "blocked"
    assert all(value is None for field, value in subject.items() if field != "status")

    assert gate["status"] == "pending-human-decision"
    assert all(value is None for field, value in gate.items() if field != "status")


def test_g13_scope_covers_the_complete_deployed_design_and_claim_limits() -> None:
    review = _review()
    scope = {item["id"] for item in review["review_scope"]}

    assert scope == {
        "protocol-adapter-and-reference-interoperability",
        "build-supply-chain-source-pin-integrity-sbom-and-reproducibility",
        "key-hierarchy-archive-wrapping-recovery-and-deletion",
        "device-enrollment-authorization-prekeys-revocation-and-churn",
        "concurrency-tabs-workers-retries-and-atomic-state",
        "api-storage-authentication-authorization-and-limits",
        "csp-served-assets-worker-boundaries-and-server-served-javascript-trust",
        "conversation-migration-downgrade-stale-client-and-mixed-history",
        "password-guessing-credential-session-device-and-account-lifecycle",
        "transport-archive-and-every-alternate-content-copy",
        "claimed-guarantees-classical-authentication-and-compromise-boundaries",
        "deployment-feature-control-operational-rollback-and-compromise-recovery",
    }
    _assert_blocked_without_evidence(review["review_scope"])

    claims = set(review["mandatory_claim_checks"])
    assert claims >= {
        (
            "complete-copy-hybrid-pq-confidentiality-for-transport-archive-self-"
            "history-offline-retry-notification-export-backup-and-deletion-paths"
        ),
        "classical-authentication-is-a-limit-and-is-never-described-as-pq-authentication",
        (
            "server-served-javascript-and-a-compromised-active-origin-remain-"
            "outside-the-confidentiality-claim"
        ),
        (
            "offline-password-guessing-resistance-is-measured-against-the-pinned-"
            "credential-and-archive-design"
        ),
        (
            "browser-state-loss-stale-restore-cross-context-concurrency-and-"
            "transaction-rollback-fail-closed"
        ),
        (
            "device-revocation-archive-rotation-and-compromise-recovery-do-not-"
            "claim-retroactive-protection-or-erasure"
        ),
    }


def test_g13_finding_contract_requires_owners_reproducers_and_retests() -> None:
    contract = _review()["finding_record_contract"]
    fields = set(contract["required_fields"])

    assert fields >= {
        "finding_id",
        "severity",
        "affected_guarantee",
        "affected_data_paths",
        "affected_revision_and_dependencies",
        "reproducer_location",
        "reproducer",
        "remediation_owner",
        "remediation_link",
        "regression_test_evidence",
        "independent_retest_reviewer",
        "independent_retest_status",
        "independent_retest_evidence",
        "residual_scope",
        "maintainer_disposition",
        "reviewer_disposition",
        "follow_up_owner",
        "follow_up_link",
        "target_date",
    }
    assert contract["allowed_severities"] == [
        "critical",
        "high",
        "medium",
        "low",
        "informational",
    ]
    assert "independent reviewer" in contract["critical_retest_rule"]
    assert "maintainer and reviewer dispositions" in (contract["nonblocking_disposition_rule"])
    assert "cannot be waived" in contract["nonwaivable_rule"]
    assert "private-disclosure" in contract["public_record_rule"]


def test_g13_requires_remediation_retest_and_affected_evidence_reruns() -> None:
    review = _review()
    remediation = review["remediation_and_retest"]
    reruns = {item["id"] for item in review["required_evidence_reruns"]}

    assert remediation["status"] == "blocked"
    assert remediation["evidence"] is None
    assert remediation["required_sequence"] == [
        "reviewer-records-finding-and-private-reproducer",
        "maintainer-assigns-remediation-owner",
        "owner-links-minimal-remediation-and-regression-tests",
        "author-verification-runs-on-remediated-pinned-build",
        "independent-reviewer-reproduces-and-records-retest",
        "affected-g12-evidence-is-rerun",
        "public-security-wording-is-reconciled",
        "maintainer-and-reviewer-dispose-any-bounded-nonblocking-residual",
    ]
    assert reruns == {
        "protocol-reference-and-continuous-pq-epochs",
        "adversarial-authorization-downgrade-replay-and-boundary-matrix",
        "fault-concurrency-retry-and-atomic-complete-copy-matrix",
        "complete-copy-storage-notification-export-backup-and-deletion-audit",
        "chromium-firefox-webkit-private-mode-and-storage-restriction-matrix",
        "unchanged-ux-accessibility-performance-and-csp-evidence",
        "migration-lifecycle-disable-rollback-and-compromise-recovery-drills",
        "ci-codeql-workflow-security-and-dependency-audits",
    }
    _assert_blocked_without_evidence(review["required_evidence_reruns"])


def test_g13_forbids_false_completion_and_protects_review_evidence() -> None:
    review = _review()
    forbidden = set(review["forbidden_completion_outcomes"])
    safety = review["evidence_safety"]

    assert forbidden >= {
        "upstream-protocol-review-substituted-for-hush-line-review",
        "author-only-verification-substituted-for-independent-retest",
        ("security-critical-finding-waived-without-remediation-and-passed-" "independent-retest"),
        "confidentiality-complete-copy-or-ux-contract-invalidating-finding-waived",
        "affected-g12-evidence-not-rerun-after-remediation",
        "public-security-wording-left-in-conflict-with-reviewer-conclusions",
        "agent-authored-reviewer-disposition-or-release-approval",
    }
    assert safety["synthetic_only"] is True
    assert safety["private_disclosure_required_for_exploit_details"] is True
    assert "real-user-or-production-data" in safety["forbidden"]
    assert "premature-public-vulnerability-reproducers" in safety["forbidden"]

    wording = review["security_wording_reconciliation"]
    assert wording["status"] == "blocked"
    assert all(value is None for field, value in wording.items() if field != "status")

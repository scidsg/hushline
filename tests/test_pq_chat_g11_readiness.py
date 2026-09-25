import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g11-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0010-conversation-migration-readiness.md"
PREREQUISITE_PATHS = {
    "G9": PQ_CHAT_DOCS / "g9-readiness.json",
    "G10": PQ_CHAT_DOCS / "g10-readiness.json",
}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g11_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g11-readiness.json" in index
    assert "adr-0010-conversation-migration-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g11_cannot_advance_until_g9_and_g10_are_approved() -> None:
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

    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g11_inventory_covers_migration_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "authenticated-current-capability-and-version-negotiation",
        "automatic-eligible-conversation-upgrade-without-extra-step",
        "atomic-first-protected-write-and-floor-advance",
        "authoritative-monotonic-conversation-minimum-version",
        "server-rejects-explicit-missing-stripped-and-stale-below-floor-writes",
        "client-rejects-downgrade-before-protected-write",
        "legacy-and-protected-history-in-one-chronological-timeline",
        "authenticated-per-message-version-and-security-truth",
        "accessible-conversation-status-and-message-details",
        "classical-authentication-limitation-remains-explicit",
        "old-client-update-needed-state-preserves-draft",
        "transient-failure-retry-state-preserves-draft-and-operation",
        "success-only-after-protected-storage-acknowledgement",
        "feature-disable-and-kill-switch-preserve-floor-and-protected-reads",
        "rollback-floor-retains-readers-and-below-floor-write-refusal",
        "normal-flow-click-prompt-accessibility-and-performance-contract",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g11_records_monotonic_version_and_history_truth_invariants() -> None:
    assert set(_readiness()["state_invariants"]) == {
        "server-authoritative-conversation-minimum-write-version",
        "conversation-minimum-write-version-never-decreases",
        "first-protected-write-and-version-floor-advance-are-atomic",
        "absent-stripped-stale-or-conflicting-negotiation-never-authorizes-below-floor-write",
        "server-enforcement-is-independent-of-client-checks-and-feature-flags",
        "feature-controls-never-reactivate-classical-writers-in-upgraded-conversations",
        "rollback-retains-protected-readers-and-authoritative-version-floor",
        "per-message-authenticated-version-drives-security-description",
        "conversation-floor-never-relabels-legacy-ciphertext",
        "success-and-draft-clearing-require-protected-storage-acknowledgement",
    }


def test_g11_inventory_covers_downgrade_rollback_and_browser_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "eligible-and-ineligible-authenticated-capability-combinations",
        "zero-new-normal-path-field-credential-prompt-page-confirmation-or-click",
        "concurrent-first-upgrade-write-and-monotonic-floor-linearization",
        "legacy-only-protected-only-and-interleaved-history-chronology",
        "per-message-version-status-details-classical-authentication-limitation-and-no-legacy-relabel",
        "explicit-absent-stripped-substituted-replayed-forged-and-stale-negotiation-rejection",
        "browser-and-direct-api-below-floor-write-rejection",
        "stale-cached-assets-and-old-client-update-needed-draft-preservation",
        "supported-client-recovery-after-old-client-refusal",
        "network-protocol-storage-transaction-response-and-acknowledgement-faults",
        "exact-operation-retry-single-commit-and-no-premature-success",
        "feature-enable-disable-reenable-and-kill-switch-before-and-after-upgrade",
        "protected-read-and-version-floor-preservation-during-feature-disable",
        "expand-deploy-rollback-and-roll-forward-with-mixed-application-versions",
        "unsafe-binary-rollback-refusal-below-reader-and-enforcement-floor",
        "chromium-firefox-webkit-normal-and-private-modes",
        "keyboard-screen-reader-accessibility-performance-and-csp",
        "synthetic-before-after-click-prompt-timing-and-capture-free-playwright-artifacts",
    }


def test_g11_forbids_downgrades_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "unauthenticated-or-client-controlled-capability-negotiation",
        "missing-negotiation-treated-as-classical-write-permission",
        "protected-version-or-eligibility-invented-before-prerequisite-approval",
        "conversation-floor-advance-without-complete-protected-write",
        "protected-write-visible-without-conversation-floor-advance",
        "conversation-version-decrease-clear-or-bypass",
        "classical-write-after-upgrade-by-stale-client-direct-api-flag-or-rollback",
        "legacy-ciphertext-rewrapped-relabelled-or-described-as-pq",
        "conversation-status-used-to-overstate-per-message-protection",
        "pq-authentication-claim-from-classically-authenticated-negotiation",
        "draft-cleared-or-success-shown-before-protected-storage-acknowledgement",
        "old-client-silent-fallback-or-false-success",
        "feature-disable-or-kill-switch-removes-protected-read-access",
        "rollback-to-binary-without-protected-reader-or-floor-enforcement",
        "new-opt-in-setup-credential-pairing-confirmation-or-normal-path-prompt",
        "secret-plaintext-draft-private-state-ciphertext-token-or-fingerprint-telemetry",
        "unverified-migration-browser-accessibility-performance-rollback-or-review-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

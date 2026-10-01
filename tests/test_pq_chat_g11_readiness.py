import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g11-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0010-conversation-migration-readiness.md"
PREREQUISITE_GATES = {"G9", "G10"}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g11_readiness_is_linked_and_records_implemented_surfaces() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g11-readiness.json" in index
    assert "adr-0010-conversation-migration-readiness.md" in index
    assert "Status: **Implemented for integration; validation and review pending**" in adr
    assert readiness["decision"] == "implemented-pending-validation-review"
    assert readiness["production_changes"] is True
    changed = {
        surface["path"] for surface in readiness["production_surfaces"] if surface["changed"]
    }
    assert changed == {
        "assets/js/chat-key-lifecycle.js",
        "docker-compose*.yaml",
        "hushline/config.py",
        "hushline/routes/message.py",
        "hushline/templates/conversation.html",
    }


def test_g11_records_implemented_g9_and_g10_inputs_without_claiming_approval() -> None:
    readiness = _readiness()
    prerequisites = {item["gate"]: item for item in readiness["prerequisites"]}

    assert prerequisites.keys() == PREREQUISITE_GATES
    assert all(item["required_result"] == "implemented" for item in prerequisites.values())
    assert all(item["observed_result"] == "implemented" for item in prerequisites.values())
    assert all(item["satisfied"] is True for item in prerequisites.values())
    assert all(item["blocker"] is None for item in prerequisites.values())
    assert readiness["decision"] != "approved"


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
    pending = deliverables["normal-flow-click-prompt-accessibility-and-performance-contract"]
    implemented = [item for item in deliverables.values() if item is not pending]
    assert all(item["status"] == "implemented" for item in implemented)
    assert all(item["evidence"] for item in implemented)
    assert pending == {
        "id": "normal-flow-click-prompt-accessibility-and-performance-contract",
        "status": "pending-validation",
        "evidence": None,
    }


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
        "protected-version-or-eligibility-without-implemented-protocol-inputs",
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

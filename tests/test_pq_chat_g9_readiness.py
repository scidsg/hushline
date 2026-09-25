import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g9-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0008-protected-delivery-readiness.md"
PREREQUISITE_PATHS = {
    "G7": PQ_CHAT_DOCS / "g7-readiness.json",
    "G8": PQ_CHAT_DOCS / "g8-readiness.json",
}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g9_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g9-readiness.json" in index
    assert "adr-0008-protected-delivery-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g9_cannot_advance_until_g7_and_g8_are_approved() -> None:
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


def test_g9_inventory_covers_protected_delivery_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "shared-opening-and-reply-protected-delivery-coordinator",
        "protected-opening-message-without-classical-bypass",
        "authenticated-sender-and-recipient-records",
        "required-recipient-device-results",
        "required-sender-self-history-and-archive-copies",
        "reviewed-canonical-signed-envelope",
        "bound-initial-nonce-and-authenticated-context",
        "stable-logical-message-and-idempotency-identity",
        "atomic-complete-copy-server-commit",
        "commit-coupled-logical-acknowledgement",
        "exact-byte-offline-and-ambiguous-result-retry",
        "one-visible-message-and-side-effect-set",
        "draft-submit-unlock-and-success-flow-preservation",
        "chronology-unread-read-and-notification-preservation",
        "participant-deletion-and-placeholder-preservation",
        "missing-javascript-and-protocol-failure-closed",
        "malformed-unauthorized-and-replayed-envelope-rejection",
        "adjacent-legacy-intake-regression-coverage",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g9_inventory_covers_delivery_and_fault_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "chromium-firefox-webkit-opening-message-and-replies",
        "sender-recipient-device-self-history-and-archive-copy-audit",
        "offline-recipient-opening-message-and-replies",
        "signed-envelope-and-authorization-negative-tests",
        "nonce-context-logical-id-and-conversation-substitution-rejection",
        "participant-device-version-suite-epoch-purpose-and-direction-substitution-rejection",
        "missing-extra-mixed-malformed-and-replayed-copy-rejection",
        "faults-before-and-after-browser-state-and-outbox-persistence",
        "faults-before-and-after-server-validation-each-copy-write-and-commit",
        "faults-before-and-after-response-acknowledgement-notification-and-cleanup",
        "offline-and-ambiguous-result-exact-byte-retry",
        "idempotency-same-result-replay-and-different-byte-collision-rejection",
        "single-visible-message-count-notification-and-acknowledgement-recovery",
        "missing-javascript-malformed-payload-protocol-archive-and-storage-failure-closed",
        (
            "draft-unlock-submit-success-chronology-unread-read-notification-"
            "deletion-and-placeholder-regression"
        ),
        "adjacent-legacy-profile-and-anonymous-intake-regression",
        "accessibility-performance-csp-interaction-count-and-responsive-main-thread",
        "capture-free-synthetic-ui-artifacts",
    }


def test_g9_forbids_unsafe_partial_wiring_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "classical-only-opening-message-in-a-protected-conversation",
        "protocol-only-or-incomplete-copy-pq-claim",
        "invented-envelope-signature-nonce-context-or-copy-inventory",
        "unsigned-malformed-unauthorized-stale-replayed-or-substituted-envelope-acceptance",
        "acknowledgement-before-complete-copy-commit",
        "partial-required-copy-persistence",
        "retry-with-regenerated-protocol-output-or-ciphertext",
        "idempotency-identity-reuse-with-different-bytes-or-context",
        "duplicate-visible-message-unread-count-or-notification",
        "dropped-message-after-committed-acknowledgement",
        "plaintext-or-classical-fallback-for-protected-chat",
        "missing-javascript-bypass-of-protected-delivery",
        "server-side-reconstruction-from-plaintext",
        "changed-normal-flow-credential-prompt-confirmation-or-send-step",
        "secret-plaintext-private-state-ciphertext-or-token-telemetry",
        "unverified-browser-fault-ux-cryptographic-or-review-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

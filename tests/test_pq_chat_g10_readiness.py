import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g10-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0009-credential-lifecycle-readiness.md"
PREREQUISITE_PATHS = {
    "G5": PQ_CHAT_DOCS / "g5-readiness.json",
    "G8": PQ_CHAT_DOCS / "g8-readiness.json",
    "G9": PQ_CHAT_DOCS / "g9-readiness.json",
}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g10_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g10-readiness.json" in index
    assert "adr-0009-credential-lifecycle-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g10_cannot_advance_until_g5_g8_and_g9_are_approved() -> None:
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


def test_g10_inventory_covers_credential_lifecycle_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "current-secret-password-change-rewraps-approved-hierarchy",
        "password-change-atomic-rollback-and-history-preservation",
        "unchanged-password-unlock-prompt-and-session-scope",
        "reset-without-old-secret-locks-old-history",
        "accessible-reset-limitation-without-server-recovery-claim",
        "routine-fresh-browser-login-without-pairing",
        "revoked-device-prekey-publication-and-claim-denial",
        "revoked-device-new-transport-and-archive-access-denial",
        "affected-transport-session-replacement",
        "future-archive-epoch-rotation-and-current-device-grants",
        "stale-offline-device-rejection-and-accessible-recovery",
        "revocation-send-linearization-and-complete-copy-retry",
        "password-rewrap-distinct-from-key-revocation",
        "old-archive-key-retained-scope-access-is-explicit",
        "compromise-specific-future-key-rotation-set",
        "logout-expiry-and-browser-clear-lock-secret-state",
        "authenticated-emergency-exit-locks-local-chat-state",
        "account-deletion-cleanup-without-remaining-history-corruption",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g10_defines_future_rotation_sets_and_honest_limits() -> None:
    responses = {item["compromise"]: item for item in _readiness()["compromise_responses"]}

    assert responses.keys() == {
        "password-only-unlock-root-still-secret",
        "authenticated-web-session-only",
        "device-private-state-or-unused-private-prekey",
        "archive-epoch-key",
        "account-unlock-root",
        "identity-signing-key-or-live-ratchet-state",
    }
    assert set(responses["archive-epoch-key"]["future_protection_requires"]) >= {
        "archive-epoch-key",
        "archive-wrappers-and-current-device-access-grants",
        "all-eligible-future-archive-copies",
    }
    assert set(responses["archive-epoch-key"]["does_not_repair"]) >= {
        "old-retained-copies-in-compromised-scope",
        "captured-old-ciphertext",
    }
    assert set(responses["account-unlock-root"]["future_protection_requires"]) >= {
        "account-unlock-root",
        "all-device-identity-prekey-archive-and-wrapper-secrets-in-root-scope",
        "authenticated-and-chat-sessions",
    }
    assert all(item["future_protection_requires"] for item in responses.values())
    assert all(item["does_not_repair"] for item in responses.values())


def test_g10_inventory_covers_required_lifecycle_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "chromium-firefox-webkit-password-change-and-reset",
        "password-change-hierarchy-rewrap-success-and-atomic-failure-rollback",
        "password-change-history-prompt-session-and-sibling-revocation-regression",
        "reset-old-history-lock-clear-message-and-no-server-recovery",
        "reset-new-future-epoch-and-other-participant-history-integrity",
        "fresh-browser-login-with-2fa-and-without-device-pairing-or-extra-secret",
        "revocation-before-and-after-prekey-publication-and-claim",
        "revocation-before-and-after-session-establishment-and-archive-grant",
        "revoked-and-stale-device-publication-claim-send-and-copy-denial",
        "offline-device-reconnect-current-state-authentication-and-recovery",
        "concurrent-send-revocation-and-archive-epoch-linearization",
        "complete-current-copy-inventory-exact-byte-retry-and-collision-rejection",
        "old-archive-key-retained-scope-access-and-new-epoch-denial",
        "compromise-specific-future-key-rotation-and-non-retroactive-limits",
        "logout-local-and-remote-session-expiry-and-browser-clear-races",
        "authenticated-emergency-exit-lock-and-accessibility",
        "account-deletion-participant-history-backup-restore-and-non-resurrection",
        "accessibility-performance-csp-interaction-count-and-capture-free-artifacts",
    }


def test_g10_forbids_unsafe_lifecycle_claims_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "password-rewrap-presented-as-compromise-recovery",
        "password-reset-server-recovery-of-unavailable-old-secret",
        "password-reset-silent-old-history-loss-or-recovery-claim",
        "routine-new-browser-existing-device-pairing-or-extra-secret-requirement",
        "revoked-device-prekey-publication-or-claim",
        "revoked-device-new-transport-archive-or-delivery-access",
        "stale-membership-session-or-archive-epoch-restoration",
        "partial-old-and-new-epoch-required-copy-set",
        "concurrent-send-accepted-after-revocation-linearization",
        "ambiguous-retry-with-regenerated-ciphertext",
        "archive-key-rotation-retroactively-repairs-captured-material-claim",
        "password-change-revokes-stolen-root-or-archive-key-claim",
        "logout-expiry-deletion-or-emergency-exit-secure-erasure-claim",
        "authenticated-emergency-exit-leaves-restorable-unlocked-chat-state",
        "remaining-participant-history-corruption-or-deleted-state-resurrection",
        "plaintext-classical-only-or-incomplete-copy-fallback",
        "secret-plaintext-private-state-ciphertext-or-token-telemetry",
        "unverified-browser-race-fault-cryptographic-or-review-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

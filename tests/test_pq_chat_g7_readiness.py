import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g7-readiness.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0006-protocol-integration-readiness.md"
G2_EVIDENCE_PATH = PQ_CHAT_DOCS / "g2-evidence.json"
PREREQUISITE_PATHS = {
    "G5": PQ_CHAT_DOCS / "g5-readiness.json",
    "G6": PQ_CHAT_DOCS / "g6-readiness.json",
}


def _readiness(path: Path = READINESS_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as readiness_file:
        return json.load(readiness_file)


def test_g7_readiness_is_linked_and_records_no_production_changes() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    readiness = _readiness()

    assert "g7-readiness.json" in index
    assert "adr-0006-protocol-integration-readiness.md" in index
    assert "Status: **Blocked before implementation**" in adr
    assert readiness["decision"] == "blocked-prerequisites"
    assert readiness["production_changes"] is False
    assert all(not surface["changed"] for surface in readiness["production_surfaces"])


def test_g7_cannot_advance_until_g5_g6_and_protocol_candidate_pass() -> None:
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

    protocol_candidate = readiness["protocol_candidate"]
    candidate_evidence = _readiness(G2_EVIDENCE_PATH)
    assert protocol_candidate["gate"] == "G2"
    assert protocol_candidate["observed_result"] == candidate_evidence["decision"]
    assert protocol_candidate["required_result"] == "go"
    assert protocol_candidate["satisfied"] is False
    assert candidate_evidence["decision"] != protocol_candidate["required_result"]
    assert readiness["decision"] not in {"ready-for-implementation", "approved"}


def test_g7_inventory_covers_protocol_integration_acceptance_contract() -> None:
    deliverables = {item["id"]: item for item in _readiness()["required_deliverables"]}

    assert deliverables.keys() >= {
        "exact-reviewed-library-suite-and-serialization",
        "reproducible-self-hosted-worker-assets",
        "narrow-protocol-worker-adapter",
        "authenticated-application-context",
        "bound-version-suite-and-capability-negotiation",
        "offline-prekey-session-establishment",
        "bidirectional-protocol-traffic",
        "repeated-post-handshake-pq-epoch-refresh",
        "bounded-skipped-and-out-of-order-delivery",
        "authenticated-session-replacement",
        "context-substitution-tamper-and-replay-rejection",
        "bounded-failure-and-recovery-behavior",
        "truthful-continuous-pq-status",
        "complete-copy-transaction-integration",
        "non-secret-protocol-instrumentation",
        "csp-performance-and-unchanged-ux-evidence",
    }
    assert all(item["status"] == "blocked" for item in deliverables.values())
    assert all(item["evidence"] is None for item in deliverables.values())


def test_g7_inventory_covers_required_protocol_and_adversarial_validation() -> None:
    assert set(_readiness()["required_validation"]) == {
        "official-vectors-and-pinned-reference-peer",
        "offline-prekey-session-establishment",
        "bidirectional-traffic-and-reload",
        "two-independent-post-handshake-pq-epochs",
        "skipped-delayed-duplicate-and-out-of-order-delivery",
        "participant-device-context-capability-and-version-substitution",
        "prekey-session-epoch-transcript-and-ciphertext-tampering",
        "replay-duplicate-and-cross-context-rejection",
        "authenticated-session-replacement-and-stale-replacement-rejection",
        "classical-contribution-failure-without-fallback",
        "pq-contribution-failure-without-fallback",
        "malformed-input-prekey-depletion-and-reviewed-failure-bounds",
        "storage-worker-concurrency-termination-and-retry-faults",
        "complete-copy-atomicity-and-confidentiality",
        "secret-bearing-telemetry-absence",
        "reproducible-build-sbom-license-vulnerability-integrity-and-csp",
        "chromium-firefox-webkit-accessibility-performance-and-ux",
    }


def test_g7_forbids_unsafe_partial_integration_and_keeps_reviews_pending() -> None:
    readiness = _readiness()

    assert set(readiness["forbidden_interim_outcomes"]) == {
        "unreviewed-protocol-dependency",
        "custom-kem-mixing-or-altered-ratchet-logic",
        "unreviewed-serialization-translation",
        "handshake-only-pq-compliance",
        "disabled-failed-or-unobserved-refresh-pq-compliance",
        "unbound-context-version-suite-or-capability",
        "unauthenticated-session-replacement",
        "accepted-substitution-tampering-or-replay",
        "unbounded-skipped-keys-pending-epochs-retries-or-failures",
        "classical-only-fallback",
        "partial-required-copy-write",
        "ui-thread-protocol-cryptography",
        "secret-bearing-telemetry",
        "third-party-runtime-cryptographic-assets",
        "unapproved-csp-expansion",
        "unverified-vector-reference-browser-or-build-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in readiness["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in readiness["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in readiness["reviewers"])

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
ROLLOUT_PATH = PQ_CHAT_DOCS / "g14-rollout-record.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0013-staged-release-readiness.md"
PREREQUISITE_PATH = PQ_CHAT_DOCS / "g13-independent-review.json"
GATE_RECORD_PATHS = {
    f"G{gate}": PQ_CHAT_DOCS / filename
    for gate, filename in (
        (2, "g2-evidence.json"),
        (3, "g3-readiness.json"),
        (4, "g4-readiness.json"),
        (5, "g5-readiness.json"),
        (6, "g6-readiness.json"),
        (7, "g7-readiness.json"),
        (8, "g8-readiness.json"),
        (9, "g9-readiness.json"),
        (10, "g10-readiness.json"),
        (11, "g11-readiness.json"),
        (12, "g12-validation-report.json"),
        (13, "g13-independent-review.json"),
    )
}


def _record(path: Path = ROLLOUT_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as record_file:
        return json.load(record_file)


def test_g14_packet_is_linked_without_claiming_release_or_production_change() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    record = _record()

    assert "g14-rollout-record.json" in index
    assert "adr-0013-staged-release-readiness.md" in index
    assert "Status: **Blocked before release**" in adr
    assert record["decision"] == "blocked-prerequisite-and-human-release"
    assert record["release_approved"] is False
    assert record["production_deployed"] is False
    assert record["production_changes"] is False


def test_g14_cannot_advance_until_g13_has_human_release_approval() -> None:
    record = _record()
    prerequisite = record["prerequisites"][0]
    observed = _record(PREREQUISITE_PATH)

    assert len(record["prerequisites"]) == 1
    assert prerequisite["gate"] == "G13"
    assert prerequisite["artifact_commit"] == record["repository_baseline"]
    assert prerequisite["observed_result"] == observed["decision"]
    assert prerequisite["required_result"] == "approved"
    assert prerequisite["satisfied"] is False
    assert observed["release_approved"] is False

    audit = record["gate_audit"]
    assert [gate["gate"] for gate in audit] == [f"G{index}" for index in range(1, 14)]
    assert all(gate["satisfied"] is False for gate in audit)
    assert audit[0]["observed_result"] == "pending-human-approval"
    assert audit[1]["observed_result"] == "no-go"
    for gate in audit[1:]:
        observed_gate = _record(GATE_RECORD_PATHS[gate["gate"]])
        assert gate["issue"] == observed_gate["issue"]
        assert gate["observed_result"] == observed_gate["decision"]


def test_g14_keeps_release_identity_approvals_and_owners_human_owned() -> None:
    record = _record()
    subject = record["release_subject"]

    assert subject["status"] == "blocked"
    assert all(value is None for field, value in subject.items() if field != "status")
    assert all(value is None for value in record["human_approvals"].values())
    assert all(value is None for value in record["owners"].values())


def test_g14_stages_schema_and_readers_before_any_writer_population() -> None:
    phases = _record()["rollout_phases"]

    assert [phase["order"] for phase in phases] == list(range(6))
    assert [phase["id"] for phase in phases] == [
        "R0-prepare-writers-off",
        "R1-schema-and-readers",
        "R2-synthetic-writers",
        "R3-approved-eligible-canary",
        "R4-approved-population-expansion",
        "R5-complete-or-hold",
    ]
    assert phases[0]["writers"] == "off"
    assert phases[1]["writers"] == "off"
    assert phases[1]["activation"] == "off"
    assert phases[2]["writers"] == "synthetic-only"
    assert phases[2]["population"] == "explicitly-allowlisted-synthetic-accounts"
    assert phases[3]["population"] is None
    assert phases[4]["population"] is None
    assert all(phase["status"] == "blocked" for phase in phases)
    assert all(phase["gate_decision"] is None for phase in phases)
    assert all(phase["approver"] is None for phase in phases)
    assert all(phase["evidence"] is None for phase in phases)


def test_g14_synthetic_smoke_covers_protection_and_operational_edges() -> None:
    smoke = _record()["synthetic_smoke"]

    assert smoke["status"] == "blocked"
    assert smoke["synthetic_only"] is True
    assert set(smoke["scenarios"]) == {
        "offline-handshake-bidirectional-traffic-and-multiple-pq-refresh-epochs",
        "complete-copy-self-history-recipient-device-offline-retry-and-archive",
        "fresh-browser-recovery-and-long-offline-delivery",
        "ambiguous-retry-concurrent-tabs-and-process-termination",
        "password-device-revocation-deletion-export-and-notification-lifecycle",
        "kill-switch-deploy-rollback-stale-client-and-restore",
    }
    assert smoke["result"] is None
    assert smoke["evidence"] is None


def test_g14_health_contract_requires_approved_aggregate_thresholds() -> None:
    health = _record()["health_observations"]

    assert health["status"] == "pending-privacy-review"
    assert health["thresholds"] == []
    assert health["approved_dimensions"] == []
    assert health["minimum_aggregation_threshold"] is None
    assert set(health["required_metric_fields"]) == {
        "owner",
        "numerator",
        "denominator",
        "minimum_aggregation_threshold",
        "alert_threshold",
        "observation_window",
        "retention",
        "access_policy",
        "dashboard",
        "response_action",
    }
    forbidden = set(health["forbidden"])
    assert forbidden >= {
        "plaintext-disclosures-or-drafts",
        "private-keys-prekeys-or-credentials",
        "ciphertext-or-serialized-private-state",
        "stable-user-account-device-conversation-message-or-operation-identifiers",
        "stable-pseudonyms-hashes-or-fingerprints",
        "sensitive-user-level-events-or-cross-event-joins",
    }


def test_g14_stop_conditions_and_kill_switch_never_enable_downgrade() -> None:
    record = _record()
    stop_conditions = set(record["immediate_stop_conditions"])
    switch = record["kill_switch"]

    assert stop_conditions >= {
        "classical-only-write-to-an-upgraded-conversation",
        "protected-history-unreadable-or-lost",
        "authorization-or-complete-copy-invariant-failure",
        "duplicate-visible-message-or-lost-acknowledged-message",
        "secret-content-ciphertext-or-stable-identifier-in-observability",
    }
    assert switch["operations"] == [
        "stop-new-activation",
        "stop-new-protected-writes",
    ]
    assert set(switch["must_preserve"]) >= {
        "monotonic-conversation-version-floor",
        "legacy-and-protected-history-readers",
        "pending-drafts-operation-identities-and-safe-retry-bytes",
        "accessible-actionable-blocked-send-errors",
    }
    assert set(switch["must_never"]) >= {
        "enable-classical-send-for-an-upgraded-conversation",
        "disable-protected-readers",
        "clear-a-pending-draft",
        "mark-a-pending-or-rejected-send-as-delivered",
    }


def test_g14_rollback_drill_preserves_history_drafts_and_exactly_once_retry() -> None:
    drill = _record()["rollback_drill"]

    assert drill["status"] == "blocked"
    assert drill["synthetic_only"] is True
    assert set(drill["required_results"]) >= {
        "pending-draft-and-ambiguous-operation-preserved",
        "no-classical-send-duplicate-or-false-success-while-stopped",
        "legacy-and-protected-history-readable-while-writers-stopped",
        "previous-reader-compatible-build-restored-without-schema-contraction",
        "safe-retry-produces-exactly-one-visible-and-acknowledged-message",
        "stale-client-send-blocked-with-actionable-error",
    }
    assert drill["result"] is None
    assert drill["evidence"] is None


def test_g14_requires_truthful_security_docs_and_complete_release_evidence() -> None:
    record = _record()
    docs = record["documentation_gate"]
    production = record["production_record"]

    assert docs["status"] == "blocked"
    assert docs["current_documents_remain_classical_until_release"] is True
    assert set(docs["documents"]) == {
        "docs/TWO-WAY-CHAT-E2EE.md",
        "docs/USE-CASES.md",
    }
    assert set(docs["required_topics"]) >= {
        "complete-copy-hybrid-pq-confidentiality",
        "continuous-post-handshake-pq-refresh",
        "legacy-history-exclusion",
        "archive-fresh-browser-offline-deletion-export-and-recovery-behavior",
        "archive-compromise-stale-restore-and-recovery-limits",
        "classical-authentication-limit",
        "eligibility-stale-client-fail-closed-send-and-pending-draft-recovery",
    }
    assert production["status"] == "not-deployed"
    assert production["release_version"] is None
    assert production["approved_population"] is None
    assert production["reached_population"] is None
    assert production["phase_decisions"] == []
    assert production["final_gate_decision"] is None
    assert production["evidence"] is None


def test_g14_forbids_false_completion_and_sensitive_release_evidence() -> None:
    record = _record()
    forbidden = set(record["forbidden_completion_outcomes"])
    safety = record["evidence_safety"]

    assert forbidden >= {
        "merged-library-disabled-flag-or-research-prototype-treated-as-release",
        "writers-enabled-before-compatible-schema-and-readers",
        "real-account-writes-before-complete-synthetic-smoke",
        "classical-fallback-on-upgraded-conversation",
        "kill-switch-or-rollback-disables-readers-or-loses-history-or-drafts",
        "release-completion-without-version-population-results-and-gate-evidence",
        "agent-authored-human-approval-or-production-result",
    }
    assert safety["synthetic_only_before-approved-production-canary"] is True
    assert safety["no_real_disclosure_data_in_artifacts"] is True
    assert "ciphertext-or-sensitive-user-level-telemetry" in safety["forbidden"]
    assert "stable-cross-account-or-user-identifiers" in safety["forbidden"]

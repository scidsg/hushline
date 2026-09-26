import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
REPORT_PATH = PQ_CHAT_DOCS / "g12-validation-report.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0011-release-validation-readiness.md"
PREREQUISITE_PATH = PQ_CHAT_DOCS / "g11-readiness.json"


def _report(path: Path = REPORT_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as report_file:
        return json.load(report_file)


def _assert_blocked_without_evidence(items: list[dict[str, Any]]) -> None:
    assert all(item["status"] == "blocked" for item in items)
    assert all(item["evidence"] is None for item in items)


def test_g12_report_is_linked_and_records_no_release_or_production_change() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    report = _report()

    assert "g12-validation-report.json" in index
    assert "adr-0011-release-validation-readiness.md" in index
    assert "Status: **Blocked before validation**" in adr
    assert report["decision"] == "blocked-prerequisite"
    assert report["release_approved"] is False
    assert report["production_changes"] is False


def test_g12_cannot_advance_until_g11_is_approved() -> None:
    report = _report()
    prerequisite = report["prerequisites"][0]
    observed = _report(PREREQUISITE_PATH)

    assert len(report["prerequisites"]) == 1
    assert prerequisite["gate"] == "G11"
    assert prerequisite["artifact_commit"] == report["repository_baseline"]
    assert prerequisite["observed_result"] == observed["decision"]
    assert prerequisite["required_result"] == "approved"
    assert prerequisite["satisfied"] is False
    assert observed["decision"] != prerequisite["required_result"]
    assert report["decision"] != "approved"


def test_g12_does_not_invent_an_integrated_build_or_result() -> None:
    report = _report()
    build = report["build_identity"]

    assert build["status"] == "blocked"
    assert build["evidence"] is None
    assert all(
        build[field] is None
        for field in (
            "implementation_commit",
            "production_bundle_sha256",
            "container_image_digest",
            "dependency_lock_sha256",
            "sbom_sha256",
            "protocol_dependency",
            "protocol_source_revision",
            "protocol_artifact_integrity",
            "protocol_suite",
            "serialization_version",
            "wire_version",
            "database_revision",
            "feature_configuration",
            "browser_driver_manifest",
            "operating_system",
            "hardware",
            "network_profile",
            "synthetic_corpus",
            "measured_at_utc",
            "reproduction_instructions",
            "ci_run",
        )
    )
    assert build["timing_runs_per_case"] == 0


def test_g12_inventory_covers_interoperability_and_adversarial_cases() -> None:
    report = _report()
    interoperability = {item["id"] for item in report["interoperability"]}
    adversarial = {item["id"] for item in report["adversarial_cases"]}

    assert interoperability == {
        "official-vectors-and-pinned-reference-peer-handshake",
        "bidirectional-traffic-and-multiple-observed-pq-epochs",
        "bounded-out-of-order-delayed-and-duplicate-traffic",
        "long-offline-gap-and-fresh-session-recovery",
        "prekey-depletion-replenishment-and-concurrent-claim",
    }
    assert adversarial == {
        "forged-substituted-and-stale-identity-device-membership",
        "context-purpose-direction-participant-and-conversation-substitution",
        "ciphertext-transcript-epoch-and-archive-wrapper-substitution",
        "version-suite-capability-and-component-downgrade",
        "message-prekey-session-copy-and-operation-replay",
        "unauthorized-read-write-and-cross-scope-access",
        "skipped-key-and-pending-state-exhaustion",
        "device-enrollment-revocation-and-churn",
        "malformed-boundary-and-oversized-payloads-without-truncation",
    }
    _assert_blocked_without_evidence(report["interoperability"])
    _assert_blocked_without_evidence(report["adversarial_cases"])


def test_g12_fault_matrix_requires_safe_acknowledged_retry_behavior() -> None:
    fault = _report()["fault_injection"]

    assert set(fault["boundaries"]) == {
        "browser-state-and-outbox-persistence",
        "cryptographic-state-transition",
        "request-dispatch",
        "server-authentication-and-validation",
        "each-required-copy-write",
        "transaction-commit",
        "response-delivery",
        "acknowledgement-persistence",
        "notification-enqueue",
        "timeline-render",
        "client-cleanup",
    }
    assert set(fault["conditions"]) == {
        "concurrent-tabs",
        "worker-tab-and-browser-termination",
        "offline-and-long-offline-intervals",
        "network-drop-duplicate-delay-and-reorder",
        "storage-unavailable-quota-and-transaction-failure",
        "ambiguous-response-and-retry",
        "known-stale-restore",
    }
    assert set(fault["required_invariants"]) == {
        "no-key-or-nonce-reuse",
        "no-divergent-ratchet-or-archive-state",
        "no-duplicate-visible-message",
        "no-duplicate-unread-count-or-notification-side-effect",
        "no-loss-of-server-acknowledged-message",
        "exact-operation-and-ciphertext-byte-reuse-on-ambiguous-retry",
        "collision-or-mismatched-retry-rejected",
    }
    assert fault["status"] == "blocked"
    assert fault["evidence"] is None


def test_g12_audits_every_content_copy_path() -> None:
    report = _report()
    inventory = {item["path"] for item in report["copy_inventory"]}

    assert inventory == {
        "transport-request-and-response",
        "sender-self-history",
        "current-recipient-and-device-history",
        "offline-queue",
        "retry-and-outbox",
        "archive-and-fresh-browser-recovery",
        "backup-and-restore",
        "generic-and-content-notification-modes",
        "account-export-and-deliberate-plaintext-export",
        "participant-account-deletion-and-retention",
        "logs-traces-errors-analytics-and-diagnostics",
    }
    _assert_blocked_without_evidence(report["copy_inventory"])
    assert "plaintext" in report["copy_invariant"]
    assert "classical-only" in report["copy_invariant"]


def test_g12_browser_matrix_and_quality_budgets_are_explicit() -> None:
    report = _report()
    browsers = {item["browser"] for item in report["browser_matrix"]}
    regressions = {item["id"] for item in report["browser_regressions"]}
    budgets = {item["id"]: item for item in report["quality_budgets"]}

    assert browsers == {
        "Chromium",
        "Firefox",
        "WebKit",
        "storage-capability-fault-injection",
    }
    assert regressions == {
        "fresh-browser-retained-history-without-extra-credential-or-pairing",
        "password-change-reset-logout-and-session-expiry",
        "device-participant-conversation-and-account-deletion",
        "generic-content-and-encrypted-email-notification-modes",
        "mixed-legacy-protected-history-and-stale-client-behavior",
        "anonymous-one-way-intake-and-adjacent-core-flow-regression",
        "csp-unchanged-or-approved-minimal-policy-and-regression",
    }
    assert budgets["lighthouse-accessibility"]["required"] == "score-equals-100"
    assert budgets["lighthouse-performance"]["required"] == "score-at-least-95"
    assert budgets["login-send-reply-and-thread-open-p95"]["minimum_runs_per_case"] == 30
    assert "50ms" in budgets["main-thread-responsiveness"]["required"]
    _assert_blocked_without_evidence(report["browser_matrix"])
    _assert_blocked_without_evidence(report["browser_regressions"])
    _assert_blocked_without_evidence(report["quality_budgets"])


def test_g12_requires_ci_supply_chain_safety_and_human_review() -> None:
    report = _report()
    checks = {item["id"] for item in report["required_checks"]}
    limits = report["operational_limits"]
    limitations = set(report["residual_limitations"])
    forbidden = set(report["forbidden_release_outcomes"])

    assert checks == {
        "make-lint",
        "focused-protocol-security-persistence-copy-lifecycle-and-browser-tests",
        "make-test",
        "ci-style-coverage",
        "workflow-security-checks",
        "codeql",
        "synthetic-end-to-end-playwright-screenshots-and-traces",
        "python-dependency-audit",
        "node-runtime-and-full-when-changed-dependency-audits",
        "rust-wasm-advisory-license-sbom-integrity-and-reproducible-build",
    }
    _assert_blocked_without_evidence(report["required_checks"])
    assert limits["status"] == "blocked"
    assert limits["evidence"] is None
    assert all(
        limits[field] is None
        for field in (
            "maximum_plaintext_bytes",
            "maximum_ciphertext_bytes",
            "maximum_devices_per_account",
            "prekey_low_watermark",
            "prekey_batch_and_retention",
            "maximum_skipped_keys",
            "maximum_pending_epochs",
            "maximum_history_corpus",
            "maximum_retry_age_and_attempts",
            "failure_and_recovery_behavior",
        )
    )
    assert report["evidence_safety"]["synthetic_only"] is True
    assert "production-data" in report["evidence_safety"]["forbidden"]
    assert "no-human-approved-threat-matrix-or-complete-copy-inventory-exists" in (limitations)
    assert forbidden == {
        "handshake-only-or-single-epoch-pq-claim",
        "same-implementation-roundtrip-presented-as-reference-interoperability",
        "classical-only-plaintext-missing-or-stale-protected-message-copy",
        "partial-copy-write-or-acknowledgement-before-complete-commit",
        "key-or-nonce-reuse-after-storage-network-crash-tab-or-retry-failure",
        "duplicate-visible-message-notification-or-unread-side-effect",
        "lost-server-acknowledged-message",
        "unauthorized-read-write-replay-substitution-or-downgrade-acceptance",
        "unbounded-skipped-key-prekey-device-payload-retry-or-state-exhaustion",
        "unsupported-browser-or-failed-private-storage-mode-omitted-from-report",
        "test-only-result-substituted-for-real-browser-evidence",
        "budget-met-by-reduced-corpus-copy-set-security-or-supported-matrix",
        (
            "failed-mandatory-check-marked-flaky-waived-or-passing-without-"
            "approved-risk-acceptance"
        ),
        "secret-bearing-log-trace-screenshot-report-or-ci-artifact",
        "unverified-user-research-independent-audit-or-release-approval-claim",
    }
    assert all(reviewer["reviewer"] is None for reviewer in report["reviewers"])
    assert all(reviewer["disposition"] == "pending" for reviewer in report["reviewers"])
    assert all(reviewer["evidence"] is None for reviewer in report["reviewers"])

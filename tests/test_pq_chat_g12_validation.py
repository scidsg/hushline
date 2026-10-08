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


def test_g12_report_is_linked_and_records_pending_release_evidence() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    report = _report()

    assert "g12-validation-report.json" in index
    assert "adr-0011-release-validation-readiness.md" in index
    assert "Status: **Validation harness implemented; execution and review pending**" in adr
    assert report["issue"] == "scidsg/hushline#2407"
    assert report["decision"] == "validation-harness-implemented-results-pending"
    assert report["release_approved"] is False
    assert report["production_changes"] is False


def test_g12_uses_the_implemented_g11_candidate_without_claiming_approval() -> None:
    report = _report()
    prerequisite = report["prerequisites"][0]
    observed = _report(PREREQUISITE_PATH)

    assert len(report["prerequisites"]) == 1
    assert prerequisite["gate"] == "G11"
    assert prerequisite["artifact_commit"] == report["repository_baseline"]
    assert prerequisite["observed_result"] == observed["decision"]
    assert prerequisite["required_result"] == "implemented"
    assert prerequisite["satisfied"] is True
    assert prerequisite["blocker"] is None
    assert observed["decision"].startswith(prerequisite["required_result"])
    assert report["decision"] != "approved"


def test_g12_does_not_invent_an_integrated_build_or_result() -> None:
    report = _report()
    build = report["build_identity"]

    assert build["status"] == "candidate-awaiting-ci-identity"
    assert build["evidence"] == [
        "playwright.pq-delivery.config.js",
        "tests/playwright/e2ee/client-side-encryption.spec.js",
        "scripts/pq_validation_manifest.mjs",
        ".github/workflows/tests.yml",
    ]
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
            "ci_run",
        )
    )
    assert build["timing_runs_per_case"] == 0
    assert build["reproduction_instructions"].startswith("make playwright-pq-delivery")


def test_g12_inventory_covers_interoperability_and_adversarial_cases() -> None:
    report = _report()
    interoperability = {item["id"]: item for item in report["interoperability"]}
    adversarial = {item["id"]: item for item in report["adversarial_cases"]}

    assert interoperability.keys() == {
        "official-vectors-and-pinned-reference-peer-handshake",
        "bidirectional-traffic-and-multiple-observed-pq-epochs",
        "bounded-out-of-order-delayed-and-duplicate-traffic",
        "long-offline-gap-and-fresh-session-recovery",
        "prekey-depletion-replenishment-and-concurrent-claim",
    }
    assert adversarial.keys() == {
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
    assert interoperability["official-vectors-and-pinned-reference-peer-handshake"] == {
        "id": "official-vectors-and-pinned-reference-peer-handshake",
        "status": "blocked",
        "evidence": None,
    }
    assert interoperability["long-offline-gap-and-fresh-session-recovery"] == {
        "id": "long-offline-gap-and-fresh-session-recovery",
        "status": "blocked",
        "evidence": None,
    }
    executable_interop = [
        item for item in interoperability.values() if item["status"] == "pending-ci"
    ]
    assert len(executable_interop) == 3
    assert all(item["evidence"] for item in executable_interop)
    assert all(item["status"] == "pending-ci" for item in adversarial.values())
    assert all(item["evidence"] for item in adversarial.values())


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
    assert fault["status"] == "pending-ci"
    assert fault["evidence"] == [
        "tests/playwright/pq-state/pq-browser-state.spec.js",
        "tests/playwright/e2ee/client-side-encryption.spec.js",
        "tests/test_pq_message_storage.py",
    ]


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
    assert all(item["status"] == "pending-ci" for item in report["browser_matrix"])
    assert all(item["evidence"] for item in report["browser_matrix"])
    csp = next(
        item
        for item in report["browser_regressions"]
        if item["id"] == "csp-unchanged-or-approved-minimal-policy-and-regression"
    )
    assert csp["status"] == "pending-ci"
    assert csp["evidence"] == "tests/test_security_headers.py"
    fresh_browser = next(
        item
        for item in report["browser_regressions"]
        if item["id"] == "fresh-browser-retained-history-without-extra-credential-or-pairing"
    )
    assert fresh_browser["status"] == "pending-ci"
    assert fresh_browser["evidence"] == ("tests/playwright/e2ee/client-side-encryption.spec.js")
    _assert_blocked_without_evidence(
        [
            item
            for item in report["browser_regressions"]
            if item is not csp and item is not fresh_browser
        ]
    )
    interaction_budget = next(
        item for item in report["quality_budgets"] if item["id"] == "normal-path-interactions"
    )
    assert interaction_budget["status"] == "pending-ci"
    assert interaction_budget["evidence"] == (
        "tests/playwright/e2ee/client-side-encryption.spec.js"
    )
    crypto_budget = next(
        item
        for item in report["quality_budgets"]
        if item["id"] == "approved-crypto-payload-storage-memory-and-amplification-budgets"
    )
    assert crypto_budget["status"] == "pending-ci-and-human-thresholds"
    assert crypto_budget["evidence"] == "prototypes/pq-ratchet/tests/prototype.spec.mjs"
    main_thread_budget = next(
        item for item in report["quality_budgets"] if item["id"] == "main-thread-responsiveness"
    )
    assert main_thread_budget["status"] == "pending-ci"
    assert main_thread_budget["evidence"] == ("prototypes/pq-ratchet/tests/prototype.spec.mjs")
    lighthouse_budgets = [
        budgets["lighthouse-accessibility"],
        budgets["lighthouse-performance"],
    ]
    assert all(item["status"] == "pending-ci" for item in lighthouse_budgets)
    assert all(item["evidence"] for item in lighthouse_budgets)
    _assert_blocked_without_evidence(
        [
            item
            for item in report["quality_budgets"]
            if item is not interaction_budget
            and item is not crypto_budget
            and item is not main_thread_budget
            and item not in lighthouse_budgets
        ]
    )


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
    codeql = next(item for item in report["required_checks"] if item["id"] == "codeql")
    assert codeql["status"] == "blocked"
    assert codeql["evidence"] is None
    executable_checks = [item for item in report["required_checks"] if item is not codeql]
    assert all(item["status"] == "pending-ci" for item in executable_checks)
    assert all(item["evidence"] for item in executable_checks)
    assert limits["status"] == "implemented-pending-review"
    assert limits["maximum_plaintext_bytes"] == 50_000
    assert limits["maximum_ciphertext_bytes"] == 200_000
    assert limits["maximum_devices_per_account"] == 5
    assert limits["prekey_low_watermark"] == 20
    assert limits["maximum_skipped_keys"] == 2_000
    assert limits["maximum_pending_epochs"] == 32
    assert limits["maximum_history_corpus"] is None
    assert limits["maximum_retry_age_and_attempts"] is None
    assert limits["evidence"]
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


def test_g12_integrated_browser_harness_retains_synthetic_evidence() -> None:
    config = (REPO_ROOT / "playwright.pq-delivery.config.js").read_text(encoding="utf-8")
    scenario = (
        REPO_ROOT / "tests" / "playwright" / "e2ee" / "client-side-encryption.spec.js"
    ).read_text(encoding="utf-8")
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["playwright:pq-delivery"] == (
        "playwright test --config=playwright.pq-delivery.config.js"
    )
    assert 'testMatch: "client-side-encryption.spec.js"' in config
    assert 'name: "chromium"' in config
    assert 'name: "firefox"' in config
    assert 'name: "webkit"' in config
    assert 'name: "webkit-mobile-emulation"' in config
    assert 'trace: "retain-on-failure"' in config
    assert "test-results/pq-delivery/results.json" in config
    assert 'testInfo.attach("protected-sender-timeline"' in scenario
    assert 'testInfo.attach("protected-recipient-timeline"' in scenario
    assert "contextOptionsForProject(testInfo)" in scenario
    assert "browser.newContext(contextOptions)" in scenario
    assert "expect(initialRequests[1]).toBe(initialRequests[0])" in scenario
    assert "expect(replyRequests[1]).toBe(replyRequests[0])" in scenario


def test_g12_ci_runs_candidate_matrix_and_records_exact_identity() -> None:
    workflow_directory = REPO_ROOT / ".github" / "workflows"
    workflow = (workflow_directory / "tests.yml").read_text(encoding="utf-8")
    audit_workflow = (workflow_directory / "dependency-security-audit.yml").read_text(
        encoding="utf-8"
    )
    protocol_config = (REPO_ROOT / "playwright.pq-protocol.config.js").read_text(encoding="utf-8")
    ratchet_config = (REPO_ROOT / "prototypes" / "pq-ratchet" / "playwright.config.mjs").read_text(
        encoding="utf-8"
    )
    manifest = (REPO_ROOT / "scripts" / "pq_validation_manifest.mjs").read_text(encoding="utf-8")

    assert "pq-delivery:" in workflow
    assert "codex/epic-2365" in workflow
    assert "project:" in workflow
    assert "webkit-mobile-emulation" in workflow
    assert "playwright install --with-deps chromium firefox webkit" in workflow
    assert "npm run playwright:pq-delivery -- --project=${{ matrix.project }}" in workflow
    assert "pq-delivery-${{ matrix.project }}-${{ github.sha }}" in workflow
    assert "node scripts/pq_validation_manifest.mjs" in workflow
    assert "pq-ratchet-evidence:" in workflow
    assert "npm run provenance > artifacts/provenance.json" in workflow
    assert "npm sbom --sbom-format cyclonedx" in workflow
    assert "npm audit --package-lock-only --json" in workflow
    assert "Measure synthetic PQ ratchet behavior and budgets" in workflow
    assert "fullyParallel: false" in protocol_config
    assert "workers: 1" in protocol_config
    assert "fullyParallel: false" in ratchet_config
    assert "workers: 1" in ratchet_config
    assert "branches: [main, codex/epic-2365]" in audit_workflow
    assert '"prototypes/pq-ratchet/package-lock.json"' in audit_workflow
    assert "python-audit:" in audit_workflow
    assert "needs: detect-python-lockfile-change" in audit_workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "process.env.GITHUB_SHA ||" in manifest
    assert "dependency: `@getmaapp/signal-wasm@${protocolDependency.version}`" in manifest
    assert 'wrapper_source_revision: "0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd"' in manifest
    assert 'libsignal_source_revision: "b056faa6dd02961cff24064c54c089c52e1a0753"' in manifest
    assert '"package-lock.json"' in manifest
    assert "browser.version()" in manifest
    assert "synthetic_data_only: true" in manifest
    assert "Playwright WebKit is not branded Safari" in manifest
    assert "Firefox automation is not a Tor Browser result" in manifest


def test_g12_accessibility_gate_requires_a_perfect_score() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow_directory = REPO_ROOT / ".github" / "workflows"
    workflow = (workflow_directory / "lighthouse.yml").read_text(encoding="utf-8")
    performance_workflow = (workflow_directory / "lighthouse-performance.yml").read_text(
        encoding="utf-8"
    )

    assert 'if [ "$$SCORE" -ne 100 ]' in makefile
    assert "Accessibility score must be 100" in makefile
    assert 'if [ "$SCORE" -ne 100 ]' in workflow
    assert "Accessibility score must be 100" in workflow
    assert "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020" in workflow
    assert "npm run build:prod" in workflow
    assert "lighthouse-accessibility-${{ github.sha }}" in workflow
    assert "codex/epic-2365" in performance_workflow
    assert 'if [ "$SCORE" -lt 95 ]' in performance_workflow
    assert "lighthouse-performance-${{ github.sha }}" in performance_workflow


def test_g12_separates_engine_coverage_from_external_browser_results() -> None:
    external = {item["browser"]: item for item in _report()["external_browser_matrix"]}

    assert external.keys() == {
        "Safari on macOS",
        "Safari on iOS hardware",
        "Tor Browser",
    }
    assert all(item["status"] == "pending-external-run" for item in external.values())
    assert all(item["evidence"] is None for item in external.values())

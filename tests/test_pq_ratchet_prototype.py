import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = REPO_ROOT / "prototypes" / "pq-ratchet"


def test_prototype_is_isolated_and_exact_version_pinned() -> None:
    package = json.loads((PROTOTYPE / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROTOTYPE / "package-lock.json").read_text(encoding="utf-8"))

    assert package["private"] is True
    assert package["dependencies"] == {"@getmaapp/signal-wasm": "0.6.6"}
    assert package["devDependencies"] == {"@playwright/test": "1.55.1"}
    candidate = lock["packages"]["node_modules/@getmaapp/signal-wasm"]
    assert candidate["version"] == "0.6.6"
    assert candidate["integrity"].startswith("sha512-")
    provenance = (PROTOTYPE / "scripts" / "provenance.mjs").read_text(encoding="utf-8")
    assert "0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd" in provenance
    assert "signal_wasm_bg.wasm" in provenance
    assert not (REPO_ROOT / "hushline" / "static" / "pq-ratchet").exists()


def test_prototype_observes_wire_epochs_and_required_faults() -> None:
    source = (PROTOTYPE / "src" / "prototype.mjs").read_text(encoding="utf-8")
    browser_test = (PROTOTYPE / "tests" / "prototype.spec.mjs").read_text(encoding="utf-8")

    assert "protobufBytesField(body.slice(1, -8), 5)" in source
    assert "pq[0] === 1" in source
    assert "epoch.value > 0" in source
    assert "handshakeResult.kyberPreKeyId !== undefined" in source
    assert "prekeyStore.export_pre_key(key.id)" in source
    assert 'kem: "round-3 Kyber1024"' in source
    assert "kem_is_fips_203_ml_kem: false" in source
    for requirement in (
        "bidirectional",
        "state_reload",
        "application_identity_binding_verified",
        "dropped_message_recovered",
        "reordered_messages_recovered",
        "replay.rejected",
        "observed_epochs.length",
        "timing_runs",
    ):
        assert requirement in browser_test


def test_prototype_keeps_evidence_non_secret_and_reference_peer_open() -> None:
    source = (PROTOTYPE / "src" / "prototype.mjs").read_text(encoding="utf-8")
    readme = (PROTOTYPE / "README.md").read_text(encoding="utf-8")

    report_start = source.index("return {\n    schema_version: 1")
    report_end = source.index("\n}\n\nexport async function resumePersistedPrototype")
    returned_report = source[report_start:report_end]
    assert "SYNTHETIC_MESSAGE" not in returned_report
    assert 'reference_peer: { status: "not_run" }' in returned_report
    assert "trusted_peer_identity" not in returned_report
    assert "must never contain\nplaintext, private keys, ratchet state" in readme
    assert "Keep issue `scidsg/hushline#2397` open" in readme


def test_prototype_tests_existing_csp_without_changing_production_policy() -> None:
    server = (PROTOTYPE / "server.mjs").read_text(encoding="utf-8")
    browser_test = (PROTOTYPE / "tests" / "prototype.spec.mjs").read_text(encoding="utf-8")

    assert 'url.searchParams.get("csp") === "conversation"' in server
    assert "strictCsp ? \"'self'\"" in server
    assert "\"'self' 'wasm-unsafe-eval'\"" in server
    assert "current conversation CSP does not silently broaden" in browser_test


def test_prototype_continues_in_memory_when_session_storage_is_unavailable() -> None:
    source = (PROTOTYPE / "src" / "prototype.mjs").read_text(encoding="utf-8")
    browser_test = (PROTOTYPE / "tests" / "prototype.spec.mjs").read_text(encoding="utf-8")

    assert "fail_closed_after_page_reload: true" in source
    assert "in_memory_export_import_passed: true" in source
    assert "expect(result.scenarioContinued).toBe(true)" in browser_test
    assert "expect(result.resume.resumed).toBe(false)" in browser_test


def test_manual_report_requires_reload_evidence_before_download() -> None:
    source = (PROTOTYPE / "src" / "prototype.mjs").read_text(encoding="utf-8")
    page = (PROTOTYPE / "src" / "index.html").read_text(encoding="utf-8")

    assert 'const REPORT_KEY = "hushline-pq-prototype-synthetic-report-v1"' in source
    assert 'document.querySelector("#resume").hidden = false' in source
    assert "page_reload: pageReload" in source
    assert 'id="resume"' in page
    assert 'id="download"' in page

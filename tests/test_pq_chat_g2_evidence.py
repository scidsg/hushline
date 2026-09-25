import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
EVIDENCE_PATH = PQ_CHAT_DOCS / "g2-evidence.json"
ADR_PATH = PQ_CHAT_DOCS / "adr-0001-browser-protocol-candidate.md"
EVALUATION_PATH = PQ_CHAT_DOCS / "candidate-evaluation.md"


def _evidence() -> dict[str, Any]:
    with EVIDENCE_PATH.open(encoding="utf-8") as evidence_file:
        return json.load(evidence_file)


def test_g2_evidence_is_linked_and_keeps_the_no_go_disposition() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = ADR_PATH.read_text(encoding="utf-8")
    evaluation = EVALUATION_PATH.read_text(encoding="utf-8")
    evidence = _evidence()

    assert "candidate-evaluation.md" in index
    assert "g2-evidence.json" in index
    assert "adr-0001-browser-protocol-candidate.md" in index
    assert "Status: **No-go**" in adr
    assert "Status: **No-go at reviewed revisions" in evaluation
    assert evidence["decision"] == "no-go"
    assert evidence["production_changes"] is False


def test_g2_candidate_pin_distinguishes_kyber_from_ml_kem() -> None:
    candidate = _evidence()["candidate"]

    assert candidate["package"] == "@getmaapp/signal-wasm"
    assert candidate["package_version"] == "0.6.6"
    assert candidate["upstream_version"] == "0.101.0"
    assert candidate["upstream_revision"] == ("b056faa6dd02961cff24064c54c089c52e1a0753")
    assert candidate["kem"] == "round-3 Kyber1024"
    assert candidate["kem_is_fips_203_ml_kem"] is False
    assert candidate["kem_wire_type"] == "0x08"
    assert candidate["mlkem1024_wire_type"] == "0x0A"
    assert candidate["mlkem1024_enabled"] is False


def test_g2_manifest_cannot_claim_go_with_missing_required_evidence() -> None:
    evidence = _evidence()
    candidate = evidence["candidate"]

    missing_provenance = (
        candidate["package_integrity"] is None
        or candidate["wrapper_source_revision"] is None
        or candidate["reproducible_build"] != "passed"
        or candidate["sbom"] != "generated-and-reviewed"
        or candidate["vulnerability_status"] != "passed"
        or candidate["named_maintenance_owner"] is None
        or candidate["named_security_reviewer"] is None
    )
    missing_protocol_evidence = any(
        scenario["status"] != "passed" or not scenario["evidence"]
        for scenario in evidence["protocol_scenarios"]
    )
    missing_browser_evidence = any(
        result["status"] != "passed" or not result["version"] or not result["os"]
        for result in evidence["browser_matrix"]
    )
    benchmarks = evidence["benchmarks"]
    missing_benchmarks = benchmarks["timing_runs_per_case"] < 30 or any(
        benchmarks[field] == "not_run"
        for field in (
            "cold_latency",
            "warm_latency",
            "bundle_transfer_bytes",
            "peak_memory_bytes",
            "main_thread_blocking_ms",
            "session_prekey_storage_bytes",
            "ciphertext_amplification",
        )
    )
    missing_csp_evidence = evidence["csp"]["status"] != "passed"

    assert all(
        (
            missing_provenance,
            missing_protocol_evidence,
            missing_browser_evidence,
            missing_benchmarks,
            missing_csp_evidence,
        )
    )
    assert evidence["decision"] != "go"


def test_g2_manifest_covers_required_protocol_browser_and_benchmark_cases() -> None:
    evidence = _evidence()

    assert {scenario["id"] for scenario in evidence["protocol_scenarios"]} == {
        "offline-recipient-pqxdh",
        "bidirectional-messages",
        "two-independent-post-handshake-pq-epochs",
        "save-reload-state",
        "dropped-reordered-messages",
        "official-libsignal-reference-peer",
    }
    assert {result["browser"] for result in evidence["browser_matrix"]} == {
        "Safari on macOS",
        "Safari on iOS",
        "Firefox",
        "Tor Browser",
        "Chromium",
        "Storage capability fault injection",
    }
    assert evidence["benchmarks"].keys() >= {
        "cold_latency",
        "warm_latency",
        "bundle_transfer_bytes",
        "peak_memory_bytes",
        "main_thread_blocking_ms",
        "session_prekey_storage_bytes",
        "ciphertext_amplification",
    }


def test_g2_evidence_contract_forbids_secret_material() -> None:
    safety = _evidence()["evidence_safety"]
    forbidden = " ".join(safety["forbidden"])

    assert safety["synthetic_only"] is True
    for secret in ("plaintext", "private keys", "shared secrets", "message keys"):
        assert secret in forbidden


def test_g2_csp_review_records_no_policy_expansion() -> None:
    csp = _evidence()["csp"]

    assert csp["profile_route_script_src"] == "'self' 'wasm-unsafe-eval'"
    assert csp["conversation_route_script_src"] == "'self'"
    assert csp["worker_src"] == "'self' blob:"
    assert csp["new_cdn_dependency"] is False
    assert csp["unsafe_eval_allowed"] is False
    assert csp["policy_changed"] is False

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PQ_CHAT_DOCS = REPO_ROOT / "docs" / "pq-chat"
READINESS_PATH = PQ_CHAT_DOCS / "g3-readiness.json"
SPEC_PATH = PQ_CHAT_DOCS / "protocol-design.md"
FIXTURE_PATH = PQ_CHAT_DOCS / "g3-wire-fixtures.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source_file:
        return json.load(source_file)


def _jcs(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_g3_links_the_complete_proposed_design_and_keeps_release_review_open() -> None:
    index = (PQ_CHAT_DOCS / "README.md").read_text(encoding="utf-8")
    adr = (PQ_CHAT_DOCS / "adr-0002-complete-protocol-design-readiness.md").read_text(
        encoding="utf-8"
    )
    readiness = _read_json(READINESS_PATH)

    assert "protocol-design.md" in index
    assert "g3-wire-fixtures.json" in index
    assert "Status: **Proposed for independent cryptographic review**" in adr
    assert readiness["issue"] == "scidsg/hushline#2398"
    assert readiness["replaces_issue"] == "scidsg/hushline#2368"
    assert readiness["decision"] == "proposed-for-independent-review"
    assert readiness["development_deliverables_complete"] is True
    assert readiness["production_changes"] is False
    assert readiness["completion"]["acceptance_criteria_complete"] is False


def test_g3_pins_transport_archive_password_and_canonical_suites() -> None:
    readiness = _read_json(READINESS_PATH)
    suite = readiness["suite"]
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert readiness["specification"] == {
        "protocol": "HL-PQCHAT-1",
        "version": 1,
        "path": "protocol-design.md",
        "fixture_path": "g3-wire-fixtures.json",
    }
    assert "round-3 Kyber1024 type 0x08" in suite["transport"]
    assert "libsignal 0.101.0" in suite["transport"]
    assert "draft-irtf-cfrg-concrete-hybrid-kems-04 MLKEM768-X25519" in (suite["archive"])
    assert "draft-ietf-hpke-pq-05" in suite["archive"]
    assert "draft-ietf-hpke-hpke-03 HPKE base mode" in suite["archive"]
    assert "KEM ID 0x647a" in suite["archive"]
    assert "m=65536 KiB, t=3, p=4" in suite["password_root"]
    assert suite["canonicalization"] == "RFC 8785 JCS UTF-8"
    assert "Hush Line does not concatenate\nindependent shared secrets" in spec
    assert "not labelled FIPS 203 ML-KEM" in spec


def test_g3_covers_every_authenticated_binding_and_design_area() -> None:
    readiness = _read_json(READINESS_PATH)
    deliverables = {item["id"]: item for item in readiness["required_deliverables"]}

    assert set(readiness["authenticated_bindings"]) == {
        "message-id",
        "conversation-id",
        "sender-account-and-device",
        "recipient-account-and-device",
        "purpose",
        "key-version",
        "archive-epoch",
        "sender-and-recipient-membership-sequence",
        "capability-offer-and-selection",
        "protocol-and-suite",
        "exact-transport-ciphertext-hashes",
        "archive-ciphertext-hashes",
        "complete-copy-inventory",
    }
    assert deliverables.keys() == {
        "protocol-and-reviewed-suite",
        "library-interfaces",
        "authenticated-envelope-bindings",
        "archive-construction-and-copy-inventory",
        "account-identity-and-device-membership",
        "prekey-lifecycle",
        "state-transactions-and-storage-recovery",
        "password-kdf-and-wrapping-lifecycle",
        "archive-epochs-revocation-reset-and-migration",
        "authentication-deniability-erasure-and-forward-secrecy-claims",
        "key-and-data-flow-diagrams",
        "wire-fixtures",
        "state-transition-tables",
        "failure-matrix",
    }
    assert all(item["status"] != "blocked" for item in deliverables.values())
    assert all(item["evidence"] for item in deliverables.values())


def test_g3_wire_fixture_pins_jcs_bytes_hashes_and_complete_copy_inventory() -> None:
    fixture = _read_json(FIXTURE_PATH)
    contexts = {item["id"]: item for item in fixture["contexts"]}
    copies = {item["id"]: item for item in fixture["copies"]}

    assert fixture["fixture_status"] == ("structural-only-not-a-cryptographic-known-answer-vector")
    assert fixture["suite"] == {
        "protocol": "HL-PQCHAT-1",
        "transport": "SIGNAL-PQXDH3-KYBER1024-SPQR1",
        "archive": "MLKEM768-X25519-HKDF-SHA256-AES256GCM",
        "archive_kem_id": "0x647a",
        "archive_kdf_id": "0x0001",
        "archive_aead_id": "0x0002",
    }
    assert set(contexts) == {
        "archive-sender",
        "archive-recipient",
        "transport-sender",
        "transport-recipient",
    }
    assert set(copies) == set(contexts)
    assert (
        contexts["transport-sender"]["value"]["device_recipient_id"]
        != (contexts["transport-sender"]["value"]["sender_device_id"])
    )
    assert contexts["archive-sender"]["value"]["recipient_membership_sequence"] == 12
    assert contexts["archive-recipient"]["value"]["recipient_membership_sequence"] == 18
    assert fixture["archive_framing"] == {
        "encapsulation_length": 1120,
        "minimum_ciphertext_length": 1136,
        "aead_tag_length": 16,
    }

    for fixture_id, context in contexts.items():
        canonical = _jcs(context["value"])
        ciphertext = _decode_base64url(copies[fixture_id]["ciphertext_base64url"])

        assert canonical.hex() == context["jcs_utf8_hex"]
        assert hashlib.sha256(canonical).hexdigest() == context["sha256"]
        assert len(ciphertext) == copies[fixture_id]["ciphertext_length"]
        assert hashlib.sha256(ciphertext).hexdigest() == copies[fixture_id]["ciphertext_sha256"]
        if context["value"]["purpose"] == "archive":
            assert len(ciphertext) >= fixture["archive_framing"]["minimum_ciphertext_length"]

    manifest_copies = fixture["manifest"]["value"]["copies"]
    assert [item["purpose"] for item in manifest_copies] == [
        "archive",
        "archive",
        "transport",
        "transport",
    ]
    assert {item["ciphertext_sha256"] for item in manifest_copies} == {
        item["ciphertext_sha256"] for item in copies.values()
    }
    assert {item["context_sha256"] for item in manifest_copies} == {
        item["sha256"] for item in contexts.values()
    }


def test_g3_wire_fixture_pins_manifest_signature_input_and_idempotency_key() -> None:
    fixture = _read_json(FIXTURE_PATH)
    manifest = _jcs(fixture["manifest"]["value"])
    signature = _decode_base64url(fixture["signature"]["synthetic_signature_base64url"])
    signature_input = fixture["signature"]["domain"].encode() + b"\x00" + manifest

    assert manifest.hex() == fixture["manifest"]["jcs_utf8_hex"]
    assert hashlib.sha256(manifest).hexdigest() == fixture["manifest"]["sha256"]
    assert len(signature) == 64
    assert (
        hashlib.sha256(signature_input).hexdigest()
        == fixture["signature"]["signature_input_sha256"]
    )
    assert hashlib.sha256(manifest + signature).hexdigest() == fixture["idempotency_key"]

    contexts = {item["id"]: item["value"] for item in fixture["contexts"]}
    request = _jcs(
        {
            "copies": [
                {
                    "ciphertext": item["ciphertext_base64url"],
                    "context": contexts[item["context_id"]],
                }
                for item in fixture["copies"]
            ],
            "manifest": fixture["manifest"]["value"],
            "signature": fixture["signature"]["synthetic_signature_base64url"],
        }
    )
    assert len(request) == fixture["request"]["jcs_utf8_length"]
    assert hashlib.sha256(request).hexdigest() == fixture["request"]["sha256"]


def test_g3_fixture_covers_tamper_downgrade_freshness_and_retry_failures() -> None:
    fixture = _read_json(FIXTURE_PATH)
    mutations = {item["id"]: item["expected_error"] for item in fixture["mutations"]}

    assert mutations == {
        "ciphertext-bit-flip": "AUTHENTICATION_FAILED",
        "archive-purpose-to-transport": "AUTHENTICATION_FAILED",
        "short-archive-ciphertext": "MALFORMED_WIRE",
        "recipient-substitution": "AUTHENTICATION_FAILED",
        "missing-archive-copy": "STATE_CONFLICT",
        "duplicate-copy": "STATE_CONFLICT",
        "capability-downgrade": "SUITE_MISMATCH",
        "membership-rollback": "STALE_MEMBERSHIP",
        "unknown-field": "MALFORMED_WIRE",
        "message-id-reuse-with-different-bytes": "STATE_CONFLICT",
    }


def test_g3_records_unrun_inputs_and_pending_human_review() -> None:
    readiness = _read_json(READINESS_PATH)
    inputs = {item["gate"]: item for item in readiness["inputs"]}
    reviewers = readiness["reviewers"]

    assert inputs["G1"]["release_disposition"] == "pending-human-approval"
    assert inputs["G2"]["release_disposition"] == "implemented-not-executed"
    assert all(item["release_satisfied"] is False for item in inputs.values())
    assert {reviewer["role"] for reviewer in reviewers} == {
        "cryptographic engineer",
        "independent design reviewer",
    }
    assert all(reviewer["reviewer"] is None for reviewer in reviewers)
    assert all(reviewer["disposition"] == "pending" for reviewer in reviewers)
    assert all(reviewer["blocking_findings"] == [] for reviewer in reviewers)
    assert readiness["completion"]["status"] == (
        "implementation-deliverables-complete-review-pending"
    )

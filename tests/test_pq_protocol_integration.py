import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependency_is_exact_and_integrity_pinned() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))

    assert package["dependencies"]["@getmaapp/signal-wasm"] == "0.6.6"
    pinned = lock["packages"]["node_modules/@getmaapp/signal-wasm"]
    assert pinned == {
        "version": "0.6.6",
        "resolved": ("https://registry.npmjs.org/@getmaapp/signal-wasm/" "-/signal-wasm-0.6.6.tgz"),
        "integrity": (
            "sha512-cYpzAe+HV1xfiXJ1tfDEvAjNkIsKwQApmFgniWJw/"
            "dTonOx4By6NzJ7J5izi+pjvfrn5zuXa0TmcHJ7Y/bLZYg=="
        ),
        "license": "AGPL-3.0-only",
    }
    assert "RUN npm ci" in (ROOT / "Dockerfile.prod").read_text(encoding="utf-8")
    assert "RUN npm install" not in (ROOT / "Dockerfile.prod").read_text(encoding="utf-8")


def test_worker_is_narrow_context_bound_and_non_telemetric() -> None:
    source = (ROOT / "assets/js/pq-protocol-worker.js").read_text(encoding="utf-8")

    for operation in (
        'operation === "createDevice"',
        'operation === "beginSession"',
        'operation === "ratchetEncrypt"',
        'operation === "ratchetDecrypt"',
    ):
        assert operation in source
    assert "processPreKeyBundle(" in source
    assert "encryptMessage(" in source
    assert "decryptMessage(" in source
    assert "protobufBytesField(body.slice(1, -8), 5)" in source
    assert "observedEpochs.length >= 2" in source
    assert "context_sha256" in source
    assert "assertContextAddresses(" in source
    assert "membershipSequence <= participant.peerMembershipSequence" in source
    assert "prekeyId !== kyberPrekeyId" in source
    assert "prekey.id !== participant.kyberPrekeys[index].id" in source
    assert "TRANSPORT_FRAME_VERSION = 1" in source
    assert "MAX_CIPHERTEXT_BYTES = 200000" in source
    assert "encodeTransportCiphertext(" in source
    assert "decodeTransportCiphertext(" in source
    assert "console." not in source


def test_protocol_adapter_uses_transactional_state_boundaries() -> None:
    source = (ROOT / "assets/js/pq-protocol.js").read_text(encoding="utf-8")
    webpack = (ROOT / "webpack.config.js").read_text(encoding="utf-8")

    assert "state.commitSend({" in source
    assert "state.commitReceive({" in source
    assert "state.deliverOutbox({" in source
    assert "verifyPqPrekeyClaim" in source
    assert "beginVerifiedSession" in source
    assert "window.HushLinePqProtocol" in source
    assert '"pq-protocol-worker",' in webpack
    assert "asyncWebAssembly: true" in webpack
    assert "filename: '[name][ext]'" in webpack


def test_real_browser_scenario_covers_required_ratchet_behaviors() -> None:
    source = (ROOT / "tests/playwright/pq-protocol/pq-protocol.spec.js").read_text(encoding="utf-8")

    for evidence in (
        "beginSession",
        "handshakeType",
        "handshakeContinuous",
        "responseType",
        "observedEpochs.length",
        "outOfOrderRecovered",
        "replacementRejected",
        "replacementPendingCompliant",
        "replacementSucceeded",
        "staleReplacementRejected",
        "substitutedContextRejected",
        "substitutedParticipantRejected",
        "ciphertextRejected",
        "replayRejected",
        "classicalRejected",
        "pqRejected",
        "continuousPq",
        "createPersistedSession",
        "listOutbox",
        "deliverOutbox",
    ):
        assert evidence in source

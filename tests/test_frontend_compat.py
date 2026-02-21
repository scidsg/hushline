import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_package_json_declares_node_18_plus() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    engines = package_json.get("engines", {})
    assert engines.get("node") == ">=18"


def test_client_side_encryption_has_platform_guards() -> None:
    js = (ROOT / "assets/js/client-side-encryption.js").read_text(encoding="utf-8")

    assert "function assertClientCryptoSupport()" in js
    assert "window.isSecureContext" in js
    assert "window.crypto.subtle" in js
    assert "window.ReadableStream" in js
    assert "typeof BigInt === \"undefined\"" in js
    assert "assertClientCryptoSupport();" in js

import ipaddress
import json
import re
from pathlib import Path

SCREENSHOT_MANIFESTS = sorted(Path("docs/screenshots").glob("scenes*.json"))
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RESERVED_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)


def _raw_header_samples(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text())
    scenes = manifest.get("scenes", manifest)
    samples: list[str] = []
    for scene in scenes:
        for action in scene.get("actions", []):
            if action.get("type") == "fill" and action.get("selector") == "#raw_headers":
                samples.append(action.get("value", ""))
    return samples


def test_email_validation_screenshot_headers_use_documentation_addresses() -> None:
    for manifest_path in SCREENSHOT_MANIFESTS:
        for sample in _raw_header_samples(manifest_path):
            domains = {match.group(1).lower() for match in EMAIL_RE.finditer(sample)}
            assert domains <= RESERVED_EMAIL_DOMAINS


def test_email_validation_screenshot_headers_use_documentation_ips() -> None:
    for manifest_path in SCREENSHOT_MANIFESTS:
        for sample in _raw_header_samples(manifest_path):
            for match in IPV4_RE.finditer(sample):
                address = ipaddress.ip_address(match.group(0))
                assert any(address in network for network in DOCUMENTATION_NETWORKS)

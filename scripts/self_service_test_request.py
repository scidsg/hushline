"""Validate private test config, produce Terraform inputs, and publish safe outputs."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
MAX_HOSTNAME_LENGTH = 253
MAX_PUBLIC_KEY_BYTES = 8192
BLOCKED_HOSTS = {"hushline.app", "tips.hushline.app", "staging.hushline.app"}


def emit(name: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError("Invalid workflow output")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def pointer(path: Path) -> None:
    if not path.is_file():
        emit("enabled", "false")
        return
    data = json.loads(path.read_text())
    if set(data) != {"order_id", "config_ref"}:
        raise ValueError("Invalid test request pointer")
    if not re.fullmatch(r"[a-f0-9]{32}", data["order_id"]):
        raise ValueError("Invalid order identifier")
    if not re.fullmatch(r"[a-f0-9]{40}", data["config_ref"]):
        raise ValueError("A test config must reference an immutable Git commit")
    emit("enabled", "true")
    emit("config_ref", data["config_ref"])
    emit("order_path", f"self-service-tests/orders/{data['order_id']}.auto.tfvars.json")


def validate_config(data: dict) -> None:
    if set(data) != {"order_id", "custom_domain", "license_limit", "claim_public_key"}:
        raise ValueError("Unexpected test configuration keys")
    if not re.fullmatch(r"[a-f0-9]{32}", data["order_id"]):
        raise ValueError("Invalid order identifier")
    domain = data["custom_domain"]
    if (
        not isinstance(domain, str)
        or len(domain) > MAX_HOSTNAME_LENGTH
        or not DOMAIN.fullmatch(domain)
    ):
        raise ValueError("Invalid test hostname")
    if domain in BLOCKED_HOSTS or domain.endswith(
        (".onion", ".local", ".localhost", ".invalid", ".example")
    ):
        raise ValueError("Test deployment cannot claim shared production or reserved hosts")
    limit = data["license_limit"]
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Invalid license selection")
    key = base64.b64decode(data["claim_public_key"], validate=True)
    if len(key) > MAX_PUBLIC_KEY_BYTES or not key.startswith(b"-----BEGIN PUBLIC KEY-----"):
        raise ValueError("Invalid admin invitation encryption key")


def prepare(path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        destination.write_text(json.dumps({"custom_domain": "", "self_service_claim_code": ""}))
        return
    data = json.loads(path.read_text())
    validate_config(data)
    claim_code = secrets.token_urlsafe(16)
    print(f"::add-mask::{claim_code}")
    destination.write_text(
        json.dumps({"custom_domain": data["custom_domain"], "self_service_claim_code": claim_code})
    )
    destination.chmod(0o600)
    public_key = destination.parent / "claim-public.pem"
    public_key.write_bytes(base64.b64decode(data["claim_public_key"], validate=True))
    encrypted = subprocess.run(  # noqa: S603 — fixed executable and validated local key path
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-encrypt",
            "-pubin",
            "-inkey",
            str(public_key),
            "-pkeyopt",
            "rsa_padding_mode:oaep",
            "-pkeyopt",
            "rsa_oaep_md:sha256",
        ],
        input=claim_code.encode(),
        capture_output=True,
        check=False,
    )
    if encrypted.returncode:
        raise ValueError("Unable to encrypt the admin invitation")
    Path("self-service-status").mkdir(exist_ok=True)
    Path("self-service-status/admin-claim.enc").write_bytes(encrypted.stdout)
    emit("custom_domain", data["custom_domain"])
    emit("order_id", data["order_id"])


def guard_plan(path: Path, name: str) -> None:
    if not re.fullmatch(r"hushline-staging-pr-[1-9][0-9]*", name):
        raise ValueError("Only a disposable test workspace may be applied")
    allowed = {
        "digitalocean_project.staging",
        "digitalocean_database_cluster.db",
        "digitalocean_app.staging",
        "digitalocean_database_firewall.staging",
    }
    plan = json.loads(path.read_text())
    for resource in plan.get("resource_changes", []):
        if resource["address"] not in allowed:
            raise ValueError("Plan includes resources outside the isolated test root")
        actions = resource["change"]["actions"]
        if "delete" in actions:
            raise ValueError("Test deployment cannot destroy or replace existing resources")
        values = resource["change"].get("after") or {}
        resource_name = values.get("name")
        if resource["address"] == "digitalocean_app.staging":
            resource_name = (values.get("spec") or [{}])[0].get("name")
        if resource_name is not None and resource_name != name:
            raise ValueError("Plan escaped the expected test resource namespace")


def status(destination: Path) -> None:
    ingress = os.environ["APP_DEFAULT_INGRESS"].removeprefix("https://").rstrip("/")
    if not re.fullmatch(r"[a-z0-9-]+\.ondigitalocean\.app", ingress):
        raise ValueError("Terraform did not return a valid DigitalOcean CNAME target")
    data = {
        "order_id": os.environ["ORDER_ID"],
        "custom_domain": os.environ["CUSTOM_DOMAIN"],
        "app_id": os.environ["APP_ID"],
        "ingress": ingress,
        "workspace": os.environ["WORKSPACE_NAME"],
        "infrastructure_ready": True,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["pointer", "prepare", "guard", "status"])
    parser.add_argument("path", type=Path)
    parser.add_argument("extra", nargs="?")
    args = parser.parse_args()
    if args.operation == "pointer":
        pointer(args.path)
    elif args.operation == "prepare":
        prepare(args.path, Path(args.extra or ""))
    elif args.operation == "guard":
        guard_plan(args.path, args.extra or "")
    else:
        status(args.path)


if __name__ == "__main__":
    main()

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
    emit("order_id", data["order_id"])
    emit("order_path", f"self-service-tests/orders/{data['order_id']}.json")


def validate_config(data: dict) -> None:
    expected = {"order_id", "custom_domain", "license_limit", "claim_public_key"}
    if set(data) not in [expected, expected | {"stripe_payment"}]:
        raise ValueError("Unexpected test configuration keys")
    if not re.fullmatch(r"[a-f0-9]{32}", data["order_id"]):
        raise ValueError("Invalid order identifier")
    domain = data["custom_domain"]
    from scripts.self_service_stripe_payment import is_clock_order

    clock_order = is_clock_order(data)
    if not clock_order and (
        not isinstance(domain, str)
        or len(domain) > MAX_HOSTNAME_LENGTH
        or not DOMAIN.fullmatch(domain)
    ):
        raise ValueError("Invalid test hostname")
    if domain in BLOCKED_HOSTS or domain.endswith(
        (".hushline.app", ".onion", ".local", ".localhost", ".invalid", ".example")
    ):
        raise ValueError("Test deployment cannot claim shared production or reserved hosts")
    limit = data["license_limit"]
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ValueError("Invalid license selection")
    key = base64.b64decode(data["claim_public_key"], validate=True)
    if len(key) > MAX_PUBLIC_KEY_BYTES or not key.startswith(b"-----BEGIN PUBLIC KEY-----"):
        raise ValueError("Invalid admin invitation encryption key")
    if "stripe_payment" in data:
        from scripts.self_service_stripe_payment import verify

        verify(data)


def prepare(path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        destination.write_text(json.dumps({"custom_domain": "", "self_service_claim_code": ""}))
        return
    data = json.loads(path.read_text())
    validate_config(data)
    claim_code = secrets.token_urlsafe(16)
    print(f"::add-mask::{claim_code}")
    values = {"custom_domain": data["custom_domain"], "self_service_claim_code": claim_code}
    from scripts.self_service_stripe_payment import is_clock_order

    if is_clock_order(data):
        from scripts.self_service_test_smtp import approved_smtp

        values.update(enable_paid_clock_smtp=True, single_tenant_smtp=approved_smtp())
    destination.write_text(json.dumps(values))
    destination.chmod(0o600)
    public_key = destination.parent / "claim-public.pem"
    public_key.write_bytes(base64.b64decode(data["claim_public_key"], validate=True))
    command = [
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
    ]
    encrypted = subprocess.run(
        command,  # noqa: S603 — fixed executable and validated local key path
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
    if not re.fullmatch(r"hushline-self-service-test-[a-f0-9]{32}", name):
        raise ValueError("Only an order-owned test workspace may be applied")
    allowed = {
        "digitalocean_project.staging",
        "digitalocean_database_cluster.db",
        "digitalocean_app.staging",
        "digitalocean_database_firewall.staging",
    }
    plan = json.loads(path.read_text())
    changes = plan.get("resource_changes", [])
    if len(changes) != len(allowed) or {item["address"] for item in changes} != allowed:
        raise ValueError("Plan must create exactly the four isolated test resources")
    prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
    if prior.get("resources") or prior.get("child_modules") or plan.get("resource_drift"):
        raise ValueError("Plan cannot adopt or refresh existing resources")
    for resource in changes:
        change = resource["change"]
        if (
            change["actions"] != ["create"]
            or change.get("before") is not None
            or change.get("importing")
            or resource.get("previous_address")
            or resource.get("module_address")
        ):
            raise ValueError("Plan cannot update, import, move, replace, or destroy resources")
        values = change.get("after") or {}
        address = resource["address"]
        if address == "digitalocean_app.staging":
            resource_name = (values.get("spec") or [{}])[0].get("name")
        else:
            resource_name = values.get("name")
        expected_name = (
            "hlst-" + name.removeprefix("hushline-self-service-test-")[:27]
            if address == "digitalocean_app.staging"
            else name
        )
        if address != "digitalocean_database_firewall.staging" and resource_name != expected_name:
            raise ValueError("Plan escaped the expected test resource namespace")
        unknown = change.get("after_unknown", {})
        if address in {"digitalocean_database_cluster.db", "digitalocean_app.staging"} and (
            values.get("project_id") is not None or unknown.get("project_id") is not True
        ):
            raise ValueError("Plan cannot attach resources to an existing project")
        if address == "digitalocean_database_firewall.staging" and (
            values.get("cluster_id") is not None or unknown.get("cluster_id") is not True
        ):
            raise ValueError("Plan cannot alter an existing database firewall")

    from scripts.self_service_stripe_payment import CLOCK_FIXTURE_ORDER

    if name == "hushline-self-service-test-" + CLOCK_FIXTURE_ORDER:
        from scripts.self_service_test_smtp import approved_smtp

        expected = approved_smtp()
        app = next(item for item in changes if item["address"] == "digitalocean_app.staging")
        services = app["change"]["after"]["spec"][0].get("service", [])
        if {item.get("name") for item in services} != {"app", "app-onion"}:
            raise ValueError("Paid clock plan requires exactly its two application services")
        for service in services:
            env = [item for item in service.get("env", []) if item.get("key") in expected]
            if (
                len(env) != len(expected)
                or any(
                    item.get("value") != expected.get(item.get("key"))
                    or item.get("type") != "SECRET"
                    or item.get("scope") != "RUN_TIME"
                    for item in env
                )
                or {item.get("key") for item in env} != set(expected)
            ):
                raise ValueError("Paid clock SMTP plan differs from the approved configuration")


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

"""Inspect and configure SMTP only for the recorded original paid test order."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import urllib.error
from pathlib import Path

from scripts import self_service_test_ownership as ownership

SMTP_KEYS = {
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_ENCRYPTION",
    "NOTIFICATIONS_ADDRESS",
}


def original(order: str) -> tuple[dict, dict]:
    if order != ownership.RECOVERY_ORDER or os.environ.get("CUSTOM_DOMAIN") != "hushline.foo":
        raise ValueError("SMTP operation requires the original authorized order and hostname")
    ownership.owned(order)
    ownership.finalize_original(order)
    workspace = ownership.workspace(order)
    if workspace is None:
        raise ValueError("Original workspace is missing")
    state = ownership.read_state(workspace)
    live = ownership.do(f"/apps/{ownership.RECOVERY_APP}")["app"]
    return state, live


def inspect(order: str) -> dict:
    state, live = original(order)
    deployment = ownership.do(
        f"/apps/{ownership.RECOVERY_APP}/deployments/{live['active_deployment']['id']}"
    )["deployment"]
    specs = [live["spec"], deployment["spec"]]
    presence = []
    for spec in specs:
        app_env = {item["key"]: item for item in spec.get("envs", [])}
        services = {}
        for service in spec["services"]:
            env = {**app_env, **{item["key"]: item for item in service.get("envs", [])}}
            services[service["name"]] = {
                key: bool(env.get(key, {}).get("value")) for key in sorted(SMTP_KEYS)
            }
        presence.append(services)
    return {
        "order_id": order,
        "hostname": "hushline.foo",
        "app_id": ownership.RECOVERY_APP,
        "database_id": state["digitalocean_database_cluster.db"]["id"],
        "ownership_verified": True,
        "healthy": True,
        "pending_deployment": False,
        "configured_spec_smtp_presence": presence[0],
        "active_runtime_spec_smtp_presence": presence[1],
    }


def approved_smtp() -> dict[str, str]:
    username = os.environ["HUSHLINE_SINGLE_TENANT_SMTP_USERNAME"]
    password = os.environ["HUSHLINE_SINGLE_TENANT_SMTP_PASSWORD"]
    if not re.fullmatch(r"[A-Za-z0-9._+-]+(?:@riseup\.net)?", username) or not password:
        raise ValueError("Dedicated single-tenant SMTP credentials are missing or invalid")
    return {
        "SMTP_USERNAME": username.removesuffix("@riseup.net"),
        "SMTP_PASSWORD": password,
        "SMTP_SERVER": "mail.riseup.net",
        "SMTP_PORT": "587",
        "SMTP_ENCRYPTION": "StartTLS",
        "NOTIFICATIONS_ADDRESS": username if "@" in username else username + "@riseup.net",
    }


def prepare(order: str, destination: Path) -> None:
    state, _ = original(order)
    spec = state["digitalocean_app.staging"]["spec"][0]
    service = next(item for item in spec["service"] if item["name"] == "app")
    worker = next(item for item in spec["worker"] if item["name"] == "onion-service")
    env = {item["key"]: item["value"] for item in service["env"] + worker["env"]}
    keys = [
        "SECRET_KEY",
        "ENCRYPTION_KEY",
        "SESSION_FERNET_KEY",
        "ONION_HOSTNAME",
        "ONION_PUBLIC_KEY_B64",
        "ONION_SECRET_KEY_B64",
    ]
    values = {key: env[key] for key in keys}
    if not re.fullmatch(r"[a-f0-9]{64}", values["SECRET_KEY"]):
        raise ValueError("Original secret is unavailable; rotation is forbidden")
    for key in ["ENCRYPTION_KEY", "SESSION_FERNET_KEY"]:
        if len(base64.urlsafe_b64decode(values[key])) != 32:  # noqa: PLR2004
            raise ValueError("Original encryption key is unavailable; rotation is forbidden")
    for key in ["ONION_PUBLIC_KEY_B64", "ONION_SECRET_KEY_B64"]:
        if not base64.b64decode(values[key], validate=True):
            raise ValueError("Original onion key is unavailable; rotation is forbidden")
    expected = ownership.claim_repair_command(state["digitalocean_database_cluster.db"]["host"])
    if len(spec["job"]) != 1 or spec["job"][0]["run_command"] != expected:
        raise ValueError("SMTP configuration cannot change the existing initializer")
    values.update(
        {
            "DO_TOKEN": os.environ["STAGING_DO_TOKEN"],
            "name": ownership.identity(order)[0],
            "branch": f"self-service-test/{order}",
            "custom_domain": "hushline.foo",
            "self_service_claim_code": env["SELF_SERVICE_TEST_CLAIM_CODE"],
            "repair_original_claim": True,
            "enable_single_tenant_smtp": True,
            "single_tenant_smtp": approved_smtp(),
            "ONION_SERVICE_IMAGE_DIGEST": worker["image"][0]["digest"],
        }
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(values, output)


def guard(path: Path, order: str) -> None:
    state, _ = original(order)
    ids = ownership.validate_resources(state, order)
    plan = json.loads(path.read_text())
    changes = plan.get("resource_changes", [])
    if len(changes) != len(ids) or {item["address"] for item in changes} != set(ids):
        raise ValueError("SMTP plan escaped the original resource set")
    prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
    if (
        prior.get("child_modules")
        or {
            item["address"]: item.get("values", {}).get("id") for item in prior.get("resources", [])
        }
        != ids
    ):
        raise ValueError("SMTP plan prior state has different ownership")
    for drift in plan.get("resource_drift", []):
        change = drift.get("change", {})
        if (
            drift.get("address") != "digitalocean_app.staging"
            or change.get("actions") != ["update"]
            or change.get("before", {}).get("id") != ownership.RECOVERY_APP
            or change.get("after", {}).get("id") != ownership.RECOVERY_APP
            or not ownership.app_refresh_equivalent(change["before"], change["after"])
        ):
            raise ValueError("SMTP refresh changed more than provider representations")
    expected = approved_smtp()
    for item in changes:
        address, change = item["address"], item["change"]
        before, after = change.get("before") or {}, change.get("after") or {}
        if (
            item.get("module_address")
            or item.get("previous_address")
            or change.get("importing")
            or before.get("id") != ids[address]
            or after.get("id") != ids[address]
        ):
            raise ValueError("SMTP cannot move, import or replace a resource")
        if address != "digitalocean_app.staging":
            if change.get("actions") != ["no-op"] or before != after:
                raise ValueError("SMTP cannot change the project, database or firewall")
            continue
        if not ownership.app_refresh_equivalent(state[address], before):
            raise ValueError("SMTP plan does not start from the original app settings")
        if change.get("actions") != ["update"]:
            raise ValueError("SMTP requires an in-place original-app update")
        adjusted = copy.deepcopy(after)
        for service in adjusted["spec"][0]["service"]:
            fields = {entry["key"]: entry for entry in service["env"] if entry["key"] in SMTP_KEYS}
            if set(fields) != SMTP_KEYS or any(
                fields[key] != {"key": key, "value": value, "type": "SECRET", "scope": "RUN_TIME"}
                for key, value in expected.items()
            ):
                raise ValueError("SMTP fields differ from the approved dedicated TLS routing")
            old = next(
                entry for entry in before["spec"][0]["service"] if entry["name"] == service["name"]
            )
            service["env"] = sorted(
                [entry for entry in service["env"] if entry["key"] not in SMTP_KEYS]
                + [entry for entry in old["env"] if entry["key"] in SMTP_KEYS],
                key=lambda entry: entry["key"],
            )
        normalized_before = copy.deepcopy(before)
        for service in normalized_before["spec"][0]["service"]:
            service["env"].sort(key=lambda entry: entry["key"])
        if not ownership.app_refresh_equivalent(normalized_before, adjusted):
            raise ValueError("SMTP plan changed an unrelated setting or initializer")
        original_spec = state[address]["spec"][0]
        for kind in ["service", "worker", "job"]:
            for component in after["spec"][0].get(kind, []):
                source = next(
                    entry for entry in original_spec[kind] if entry["name"] == component["name"]
                )
                secrets = {
                    entry["key"]: entry["value"]
                    for entry in component.get("env", [])
                    if entry["type"] == "SECRET" and entry["key"] not in SMTP_KEYS
                }
                original_secrets = {
                    entry["key"]: entry["value"]
                    for entry in source.get("env", [])
                    if entry["type"] == "SECRET" and entry["key"] not in SMTP_KEYS
                }
                if secrets != original_secrets:
                    raise ValueError("SMTP cannot rotate unrelated secrets")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["inspect", "prepare", "guard"])
    parser.add_argument("order")
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    if args.operation == "inspect":
        print(json.dumps(inspect(args.order)))
    elif args.path is None:
        raise ValueError("SMTP mutation requires a checked private path")
    elif args.operation == "prepare":
        prepare(args.order, args.path)
    else:
        guard(args.path, args.order)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Original-order SMTP control plane failed: HTTP {error.code}") from None
    except (ValueError, KeyError, OSError, StopIteration):
        raise SystemExit(
            "Original-order SMTP safeguard failed; details withheld; no apply allowed"
        ) from None

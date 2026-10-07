"""Exact new-customer Terraform plan guards, separate from legacy test roots.

These checks do not replace fresh Stripe authority, provider ownership checks or
saved-plan application. They never grant access to an existing workspace.
"""

from __future__ import annotations

import hmac
import re
from typing import Any

SERVICE_COUNT = 2
APP_REPOSITORY = "https://github.com/scidsg/hushline.git"
PREFIX = "hushline-single-tenant-"
RESOURCES = {
    "digitalocean_project.tenant",
    "digitalocean_database_cluster.tenant",
    "digitalocean_app.tenant",
    "digitalocean_database_firewall.tenant",
}
PROTECTED_TEST_ORDERS = {
    "de44b913bbc22b3ac75d8e5b114bdc45",
    "d9a565c4b17aca835b1f23a0b69b482b",
    "1c08c360da985ca24e9e246371ffc97f",
    "d9096a7ac4a4a90198550588df08fdcd",
    "6368ab5a5987358f9a9083f8ec2707b7",
}


def identity(order: str) -> tuple[str, str]:
    if not re.fullmatch(r"[a-f0-9]{32}", order) or order in PROTECTED_TEST_ORDERS:
        raise ValueError("A new customer order is required")
    return PREFIX + order, "hls-" + order[:28]


def changes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    values = plan.get("resource_changes", [])
    if (
        not isinstance(values, list)
        or len({value.get("address") for value in values}) != len(values)
        or any(
            value.get("address") not in RESOURCES
            or value.get("module_address")
            or value.get("previous_address")
            or value.get("mode", "managed") != "managed"
            or value.get("change", {}).get("importing")
            for value in values
        )
    ):
        raise ValueError("Plan escaped the exact customer resource root")
    return values


def guard_credentials(plan: dict[str, Any], automation_token: str) -> None:
    actual = plan.get("variables", {}).get("DO_TOKEN", {}).get("value")
    config = plan.get("configuration", {}).get("provider_config", {})
    if (
        not automation_token
        or not isinstance(actual, str)
        or not hmac.compare_digest(actual, automation_token)
        or set(config) != {"digitalocean"}
        or config["digitalocean"].get("full_name")
        != "registry.terraform.io/digitalocean/digitalocean"
        or config["digitalocean"].get("expressions", {}).get("token", {}).get("references")
        != ["var.DO_TOKEN"]
    ):
        raise ValueError("Plan does not use the approved dedicated cloud credential")


def guard_create(
    plan: dict[str, Any],
    order: str,
    license_limit: int | None,
    *,
    automation_token: str,
    app_secrets: dict[str, str],
) -> None:
    name, app_name = identity(order)
    guard_credentials(plan, automation_token)
    keys = {"SECRET_KEY", "ENCRYPTION_KEY", "SESSION_FERNET_KEY"}
    if set(app_secrets) != keys or any(not value for value in app_secrets.values()):
        raise ValueError("Fresh per-instance secrets are required")
    if any(
        plan.get("variables", {}).get(key, {}).get("value") != value
        for key, value in app_secrets.items()
    ):
        raise ValueError("Plan inherited secrets outside this new instance")
    if license_limit is not None and (
        isinstance(license_limit, bool) or not isinstance(license_limit, int) or license_limit < 1
    ):
        raise ValueError("Invalid paid license allowance")
    resources = changes(plan)
    prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
    if (
        {value["address"] for value in resources} != RESOURCES
        or prior.get("resources")
        or prior.get("child_modules")
        or plan.get("resource_drift")
    ):
        raise ValueError("Creation cannot adopt or refresh an existing instance")
    for resource in resources:
        change = resource["change"]
        after = change.get("after") or {}
        unknown = change.get("after_unknown") or {}
        address = resource["address"]
        if change["actions"] != ["create"] or change.get("before") is not None:
            raise ValueError("Creation cannot update, replace or delete any resource")
        if address == "digitalocean_app.tenant":
            specs = after.get("spec", [])
            if len(specs) != 1 or specs[0].get("name") != app_name:
                raise ValueError("App escaped its new customer name")
            services = specs[0].get("service", [])
            if len(services) != SERVICE_COUNT or {s.get("name") for s in services} != {
                "app",
                "app-onion",
            }:
                raise ValueError("Only the two owned app services are allowed")
            for service in services:
                git = service.get("git", [{}])[0]
                if (
                    git.get("branch") != "single-tenant/" + order
                    or git.get("repo_clone_url") != APP_REPOSITORY
                    or service.get("dockerfile_path") != "Dockerfile.prod"
                ):
                    raise ValueError("App build branch belongs to another order")
                env = service.get("env", [])
                if len({e.get("key") for e in env}) != len(env):
                    raise ValueError("Ambiguous application configuration")
                for key, value in app_secrets.items():
                    private = [entry for entry in env if entry.get("key") == key]
                    if len(private) != 1 or private[0] != {
                        "key": key,
                        "value": value,
                        "type": "SECRET",
                        "scope": "RUN_TIME",
                    }:
                        raise ValueError("Runtime inherited a secret outside this new instance")
                instance = [e for e in env if e.get("key") == "SINGLE_TENANT_INSTANCE_ORDER"]
                allowance = [e for e in env if e.get("key") == "SINGLE_TENANT_LICENSE_LIMIT"]
                if len(instance) != 1 or instance[0] != {
                    "key": "SINGLE_TENANT_INSTANCE_ORDER",
                    "value": order,
                    "type": "GENERAL",
                    "scope": "RUN_TIME",
                }:
                    raise ValueError("Instance ownership marker is missing")
                if license_limit is None:
                    if allowance:
                        raise ValueError("Unlimited must not inherit a finite allowance")
                elif len(allowance) != 1 or allowance[0] != {
                    "key": "SINGLE_TENANT_LICENSE_LIMIT",
                    "value": str(license_limit),
                    "type": "GENERAL",
                    "scope": "RUN_TIME",
                }:
                    raise ValueError("Runtime license allowance differs from the paid order")
        elif address != "digitalocean_database_firewall.tenant" and after.get("name") != name:
            raise ValueError("Resource escaped its new customer name")
        if address in {"digitalocean_app.tenant", "digitalocean_database_cluster.tenant"} and (
            after.get("project_id") is not None or unknown.get("project_id") is not True
        ):
            raise ValueError("Resources cannot join an existing project")
        if address == "digitalocean_database_firewall.tenant" and (
            after.get("cluster_id") is not None or unknown.get("cluster_id") is not True
        ):
            raise ValueError("Firewall cannot attach to an existing database")


def guard_delete(
    plan: dict[str, Any],
    order: str,
    owned_ids: dict[str, str],
    *,
    phase: str,
    automation_token: str,
) -> None:
    identity(order)
    guard_credentials(plan, automation_token)
    if set(owned_ids) != RESOURCES or any(not value for value in owned_ids.values()):
        raise ValueError("Exact independently verified resource IDs are required")
    expected = (
        RESOURCES - {"digitalocean_project.tenant"}
        if phase == "services"
        else {"digitalocean_project.tenant"}
    )
    if phase not in {"services", "project"}:
        raise ValueError("Unsupported retirement phase")
    resources = changes(plan)
    deletes = set()
    for resource in resources:
        change = resource["change"]
        address = resource["address"]
        if change.get("before", {}).get("id") != owned_ids[address]:
            raise ValueError("Retirement attempted another instance's resource")
        if change["actions"] == ["delete"] and change.get("after") is None:
            deletes.add(address)
        elif change["actions"] != ["no-op"] or change.get("after") != change.get("before"):
            raise ValueError("Retirement permits only exact-ID deletion")
    if deletes != expected:
        raise ValueError("Retirement must use the complete guarded two-phase sequence")

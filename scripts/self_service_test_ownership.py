"""Fail closed before any mutation of the disposable self-service workspace."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Any

PROJECT = "prj-iEruEQFmaNTCRAtA"
DIRECTORY = "hushline-self-service-test"
RECOVERY_ORDER = "de44b913bbc22b3ac75d8e5b114bdc45"
RECOVERY_IDS = {
    "digitalocean_project.staging": "c668d9b7-e17b-4817-85e3-ed78d3b55af9",
    "digitalocean_database_cluster.db": "e4de185b-6961-424d-8924-4acd92abec95",
}
APP_REFRESH_FIELDS = {
    "urn",
    "default_ingress",
    "live_url",
    "live_domain",
    "active_deployment_id",
    "updated_at",
    "created_at",
    "dedicated_ips",
}
SERVICE_COUNT = 2
RECOVERY_APP = "11ce3bed-e389-4510-81d2-3bdad9146eda"
ORG = "science-and-design"
ADDRESSES = {
    "digitalocean_project.staging",
    "digitalocean_database_cluster.db",
    "digitalocean_app.staging",
    "digitalocean_database_firewall.staging",
}


def identity(order: str) -> tuple[str, str]:
    if not re.fullmatch(r"[a-f0-9]{32}", order):
        raise ValueError("Invalid order ownership identifier")
    return f"hushline-self-service-test-{order}", f"scidsg/hushline self-service-test {order}"


def app_name(order: str) -> str:
    identity(order)
    return "hlst-" + order[:27]


def request(
    host: str, path: str, token: str | None, body: dict | None = None, method: str = "GET"
) -> dict:
    if host not in {"app.terraform.io", "api.digitalocean.com", "archivist.terraform.io"}:
        raise ValueError("Control-plane host is not authorized")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid control-plane path")
    headers = {"Content-Type": "application/vnd.api+json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    query = urllib.request.Request(  # noqa: S310 — allowlisted HTTPS cloud endpoints
        f"https://{host}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )

    # Never forward a bearer token to a redirect target.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    with urllib.request.build_opener(NoRedirect()).open(query, timeout=60) as response:
        payload = response.read()
    return json.loads(payload) if payload else {}


def tf(path: str, body: dict | None = None, method: str = "GET") -> dict:
    return request(
        "app.terraform.io", f"/api/v2{path}", os.environ["STAGING_TF_TOKEN"], body, method
    )


def workspace(order: str) -> dict | None:
    name, _ = identity(order)
    try:
        return tf(f"/organizations/{ORG}/workspaces/{name}")["data"]
    except urllib.error.HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return None
        raise


def validate_workspace(data: dict, order: str) -> dict:
    name, source = identity(order)
    attributes = data["attributes"]
    relationships = data["relationships"]
    if (
        not re.fullmatch(r"ws-[A-Za-z0-9]+", data["id"])
        or attributes.get("name") != name
        or attributes.get("source-name") != source
        or attributes.get("working-directory") != DIRECTORY
        or attributes.get("execution-mode") != "remote"
        or attributes.get("terraform-version") != "1.13.5"
        or attributes.get("auto-apply") is not False
        or attributes.get("auto-apply-run-trigger") is not False
        or attributes.get("global-remote-state") is not False
        or attributes.get("auto-destroy-activity-duration") is not None
        or attributes.get("auto-destroy-at") is not None
        or attributes.get("vcs-repo") is not None
        or relationships["project"]["data"]["id"] != PROJECT
    ):
        raise ValueError("Workspace ownership or isolation does not match this order")
    manifest = json.loads(attributes.get("description", ""))
    if manifest.get("order_id") != order or manifest.get("schema") != 1:
        raise ValueError("Workspace ownership manifest does not match this order")
    return manifest


def create(order: str) -> None:
    name, source = identity(order)
    # Existing workspaces are never adopted, refreshed, or modified by deployment.
    if workspace(order) is not None:
        raise ValueError(
            "Test workspace already exists; deployment cannot adopt existing resources"
        )
    manifest = {"schema": 1, "order_id": order, "resources": None}
    body = {
        "data": {
            "type": "workspaces",
            "attributes": {
                "name": name,
                "source-name": source,
                "description": json.dumps(manifest),
                "working-directory": DIRECTORY,
                "auto-apply": False,
                "auto-apply-run-trigger": False,
                "global-remote-state": False,
                "queue-all-runs": False,
                "execution-mode": "remote",
                "terraform-version": "1.13.5",
                "allow-destroy-plan": True,
            },
            "relationships": {"project": {"data": {"id": PROJECT, "type": "projects"}}},
        }
    }
    data = tf(f"/organizations/{ORG}/workspaces", body, "POST")["data"]
    validate_workspace(data, order)
    tf(
        f"/workspaces/{data['id']}/relationships/tags",
        {"data": [{"type": "tags", "attributes": {"name": "self-service-test"}}]},
        "POST",
    )


def do(path: str) -> dict:
    return request("api.digitalocean.com", f"/v2{path}", os.environ["STAGING_DO_TOKEN"])


def inventory(path: str, key: str) -> list[dict]:
    results = []
    for page in range(1, 100):
        response = do(f"{path}?per_page=200&page={page}")
        results.extend(response[key])
        if not response.get("links", {}).get("pages", {}).get("next"):
            return results
    raise ValueError("Cloud inventory exceeded the safety limit")


def preflight(order: str, domain: str) -> None:
    name, _ = identity(order)
    for project in inventory("/projects", "projects"):
        if project["name"] == name:
            raise ValueError("Test project name already belongs to an existing resource")
    for database in inventory("/databases", "databases"):
        if database["name"] == name:
            raise ValueError("Test database name already belongs to an existing resource")
    check_app_availability(order, domain)


def check_app_availability(order: str, domain: str) -> None:
    for app in inventory("/apps", "apps"):
        domains = []
        for entry in app["spec"].get("domains", []):
            if "domain" not in entry:
                # DEFAULT selects DigitalOcean's generated .ondigitalocean.app host.
                if entry.get("type") == "DEFAULT":
                    continue
                raise ValueError("Custom domain inventory is missing its hostname")
            domains.append(entry["domain"])
        if app["spec"]["name"] == app_name(order) or domain in domains:
            raise ValueError("Test name or hostname already belongs to an existing instance")


def validate_live(ids: dict, order: str) -> None:
    name, _ = identity(order)
    project_id = ids["digitalocean_project.staging"]
    app_id = ids["digitalocean_app.staging"]
    db_id = ids["digitalocean_database_cluster.db"]
    project = do(f"/projects/{project_id}")["project"]
    app = do(f"/apps/{app_id}")["app"]
    database = do(f"/databases/{db_id}")["database"]
    if (
        project.get("id") != project_id
        or project.get("name") != name
        or project.get("description") != f"Owned disposable Hush Line test {name}"
        or app.get("id") != app_id
        or app["spec"].get("name") != app_name(order)
        or database.get("id") != db_id
        or database.get("name") != name
        or database.get("project_id") != project_id
    ):
        raise ValueError("Live cloud resources do not match the recorded order")
    members = {
        entry["urn"] for entry in inventory(f"/projects/{project_id}/resources", "resources")
    }
    if members != {f"do:app:{app_id}", f"do:dbaas:{db_id}"}:
        raise ValueError("Test project contains resources with different ownership")


def state_resources(data: dict) -> dict:
    results = {}
    seen = set()
    for resource in data.get("resources", []):
        address = f"{resource['type']}.{resource['name']}"
        if resource.get("mode") != "managed" or resource.get("module") or address not in ADDRESSES:
            raise ValueError("State contains a resource outside the isolated test root")
        instances = resource["instances"]
        if address in seen:
            raise ValueError("State contains ambiguous resource ownership")
        seen.add(address)
        # Failed creates can leave an address with no owned resource instance.
        if not instances:
            continue
        if len(instances) != 1 or instances[0].get("deposed"):
            raise ValueError("State contains ambiguous resource ownership")
        results[address] = instances[0]["attributes"]
    return results


def read_raw_state(data: dict) -> dict:
    version = tf(f"/workspaces/{data['id']}/current-state-version")["data"]
    return read_state_version(version)


def read_state_version(version: dict) -> dict:
    url = version["attributes"]["hosted-state-download-url"]
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"app.terraform.io", "archivist.terraform.io"}
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not (
            (parsed.hostname == "archivist.terraform.io" and parsed.path.startswith("/v1/object/"))
            or (
                parsed.hostname == "app.terraform.io"
                and re.fullmatch(
                    r"/api/(?:v2/)?state-versions/sv-[A-Za-z0-9]+/hosted_state", parsed.path
                )
            )
        )
    ):
        raise ValueError("Invalid state download URL")
    # HCP hosted-state downloads require authentication. The common requester
    # rejects redirects, so the token cannot be forwarded to another host.
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    token = os.environ["STAGING_TF_TOKEN"] if parsed.hostname == "app.terraform.io" else None
    try:
        payload = request(parsed.hostname, path, token)
    except urllib.error.HTTPError as error:
        if error.code != HTTPStatus.FOUND:
            raise
        redirect = urllib.parse.urlsplit(error.headers.get("Location", ""))
        if (
            redirect.scheme != "https"
            or redirect.hostname != "archivist.terraform.io"
            or redirect.port not in {None, 443}
            or redirect.username is not None
            or redirect.password is not None
            or redirect.fragment
            or not redirect.path.startswith("/v1/object/")
        ):
            raise ValueError("State redirect is not an approved HCP storage URL") from None
        redirect_path = redirect.path + ("?" + redirect.query if redirect.query else "")
        # The storage URL is signed. Never forward the API token to the redirect.
        payload = request("archivist.terraform.io", redirect_path, None)
    return payload


def read_state(data: dict) -> dict:
    return state_resources(read_raw_state(data))


def validate_resources(resources: dict, order: str) -> dict:
    name, _ = identity(order)
    if set(resources) != ADDRESSES:
        raise ValueError("Ownership requires exactly the four resources created for this order")
    project = resources["digitalocean_project.staging"]
    database = resources["digitalocean_database_cluster.db"]
    app = resources["digitalocean_app.staging"]
    firewall = resources["digitalocean_database_firewall.staging"]
    if (
        project.get("name") != name
        or project.get("description") != f"Owned disposable Hush Line test {name}"
        or database.get("name") != name
        or app["spec"][0].get("name") != app_name(order)
        or database.get("project_id") != project.get("id")
        or app.get("project_id") != project.get("id")
        or firewall.get("cluster_id") != database.get("id")
        or len(firewall.get("rule", [])) != 1
        or firewall["rule"][0].get("type") != "app"
        or firewall["rule"][0].get("value") != app.get("id")
    ):
        raise ValueError("Resource names or relationships escaped the owned test project")
    ids = {address: value.get("id") for address, value in resources.items()}
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]+", value)
        for value in ids.values()
    ):
        raise ValueError("Resource ownership IDs are missing")
    return ids


def record(order: str) -> None:
    data = workspace(order)
    if data is None:
        raise ValueError("Owned test workspace is missing")
    manifest = validate_workspace(data, order)
    if manifest.get("resources") is not None:
        raise ValueError("Cannot overwrite the original resource ownership record")
    manifest["resources"] = validate_resources(read_state(data), order)
    tf(
        f"/workspaces/{data['id']}",
        {"data": {"type": "workspaces", "attributes": {"description": json.dumps(manifest)}}},
        "PATCH",
    )


def owned(order: str) -> dict:
    data = workspace(order)
    if data is None:
        raise ValueError("Owned test workspace is missing")
    manifest = validate_workspace(data, order)
    if set(manifest.get("resources") or {}) != ADDRESSES:
        raise ValueError("Cleanup requires the original resource ownership record")
    resources = read_state(data)
    if validate_resources(resources, order) != manifest["resources"]:
        raise ValueError("Cleanup cannot touch resources with different ownership IDs")
    validate_live(manifest["resources"], order)
    return manifest["resources"]


def guard_destroy(path: Path, order: str, ids: dict) -> None:
    name, _ = identity(order)
    plan = json.loads(path.read_text())
    changes = plan.get("resource_changes", [])
    if {item["address"] for item in changes} != ADDRESSES or len(changes) != len(ADDRESSES):
        raise ValueError("Cleanup plan escaped the owned resource set")
    before = {}
    for item in changes:
        change = item["change"]
        if (
            change["actions"] != ["delete"]
            or change.get("importing")
            or item.get("previous_address")
        ):
            raise ValueError("Cleanup must only delete the recorded test resources")
        before[item["address"]] = change["before"]
    if validate_resources(before, order) != ids:
        raise ValueError("Cleanup plan has different resource ownership IDs")
    if name != os.environ.get("WORKSPACE_NAME", name):
        raise ValueError("Cleanup workspace does not match this order")


def remove_workspace(order: str) -> None:
    data = workspace(order)
    if data is None:
        return
    manifest = validate_workspace(data, order)
    if set(manifest.get("resources") or {}) != ADDRESSES or read_state(data):
        raise ValueError("Cannot delete a workspace until its owned resources are gone")
    tf(f"/workspaces/{data['id']}/actions/safe-delete", method="POST")


def recovery(order: str) -> dict:
    """Continue only the original partial apply, never adopt an existing instance."""
    if order != RECOVERY_ORDER or os.environ.get("CUSTOM_DOMAIN") != "hushline.foo":
        raise ValueError("Recovery is restricted to the original authorized test order")
    data = workspace(order)
    if data is None:
        raise ValueError("Original test workspace is missing")
    manifest = validate_workspace(data, order)
    if manifest.get("resources") is not None:
        raise ValueError("Recovery cannot alter an already completed instance")
    resources = read_state(data)
    if set(resources) not in [set(RECOVERY_IDS), set(RECOVERY_IDS) | {"digitalocean_app.staging"}]:
        raise ValueError(
            "Recovery requires the original project and database, "
            "with only the original failed app"
        )
    name, _ = identity(order)
    project = resources["digitalocean_project.staging"]
    database = resources["digitalocean_database_cluster.db"]
    project_id = RECOVERY_IDS["digitalocean_project.staging"]
    db_id = RECOVERY_IDS["digitalocean_database_cluster.db"]
    if (
        any(
            resources[address].get("id") != identifier
            for address, identifier in RECOVERY_IDS.items()
        )
        or project.get("name") != name
        or project.get("description") != f"Owned disposable Hush Line test {name}"
        or database.get("name") != name
        or database.get("project_id") != project_id
    ):
        raise ValueError("Partial resource ownership does not match the original apply")
    live_project = do(f"/projects/{project_id}")["project"]
    live_database = do(f"/databases/{db_id}")["database"]
    members = {item["urn"] for item in inventory(f"/projects/{project_id}/resources", "resources")}
    if (
        live_project.get("id") != project_id
        or live_project.get("name") != name
        or live_project.get("description") != project.get("description")
        or live_database.get("id") != db_id
        or live_database.get("name") != name
        or live_database.get("project_id") != project_id
        or members
        != (
            {f"do:dbaas:{db_id}"}
            | ({f"do:app:{RECOVERY_APP}"} if "digitalocean_app.staging" in resources else set())
        )
    ):
        raise ValueError("Live partial resource ownership is not exclusively the original order")
    if "digitalocean_app.staging" in resources:
        app = resources["digitalocean_app.staging"]
        live = do(f"/apps/{RECOVERY_APP}")["app"]
        if (
            app.get("id") != RECOVERY_APP
            or app.get("project_id") != project_id
            or (app.get("spec") or [{}])[0].get("name") != app_name(order)
            or live.get("id") != RECOVERY_APP
            or live.get("active_deployment")
            or any(
                (live.get(key) or {}).get("phase") not in {None, "ERROR", "CANCELED"}
                for key in ["pending_deployment", "in_progress_deployment"]
            )
            or live.get("spec", {}).get("name") != app_name(order)
            or {entry.get("domain") for entry in live.get("spec", {}).get("domains", [])}
            != {"hushline.foo"}
            or len(live.get("spec", {}).get("services", [])) != SERVICE_COUNT
            or any(
                service.get("git", {}).get("branch") != f"self-service-test/{order}"
                or service.get("git", {}).get("repo_clone_url")
                != "https://github.com/scidsg/hushline.git"
                for service in live["spec"]["services"]
            )
        ):
            raise ValueError("Recovery requires the original never-live failed app")
    else:
        check_app_availability(order, "hushline.foo")
    return resources


def app_refresh_equivalent(before: dict, after: dict) -> bool:
    """Allow provider secret encoding and the platform's single default route."""

    def normalize(data: dict) -> dict:
        result = json.loads(json.dumps(data))
        for spec in result.get("spec", []):
            domains = {entry["name"] for entry in spec.get("domain", [])}
            if set(spec.get("domains") or []) - domains:
                raise ValueError("Refresh added a different domain")
            spec.pop("domains", None)
            ingress = spec.pop("ingress", [])
            if ingress:
                rules = ingress[0].get("rule", [])
                if len(ingress) != 1 or len(rules) != 1 or ingress[0].get("secure_header"):
                    raise ValueError("Refresh added non-default routing")
                rule = rules[0]
                component = rule.get("component", [])
                matches = rule.get("match", [])
                if (
                    rule.get("cors")
                    or rule.get("redirect")
                    or len(component) != 1
                    or component[0].get("name") != "app"
                    or component[0].get("rewrite")
                    or len(matches) != 1
                    or matches[0].get("authority")
                    or matches[0].get("path") != [{"prefix": "/"}]
                ):
                    raise ValueError("Refresh added non-default routing")
            for component in [spec, *spec.get("service", []), *spec.get("worker", [])]:
                for env in component.get("env", []):
                    if env.get("type") == "SECRET":
                        # The API returns encrypted secret representations. Keys,
                        # types, scopes and all non-secret values still compare.
                        env["value"] = "private-provider-representation"
        return {key: value for key, value in result.items() if key not in APP_REFRESH_FIELDS}

    return normalize(before) == normalize(after)


def guard_recovery(path: Path, order: str) -> None:
    resources = recovery(order)
    existing_ids = {address: value["id"] for address, value in resources.items()}
    plan = json.loads(path.read_text())
    changes = plan.get("resource_changes", [])
    if len(changes) != len(ADDRESSES) or {item["address"] for item in changes} != ADDRESSES:
        raise ValueError("Recovery plan escaped the original owned resource set")
    # Refresh differences are not mutations. Only the original IDs may be
    # refreshed; the resource_changes checks below still require exact no-ops.
    for drift in plan.get("resource_drift", []):
        address = drift.get("address")
        change = drift.get("change", {})
        before = change.get("before") or {}
        after = change.get("after") or {}
        if (
            address not in existing_ids
            or drift.get("module_address")
            or drift.get("previous_address")
            or change.get("importing")
            or change.get("actions") != ["update"]
            or before.get("id") != existing_ids[address]
            or after.get("id") != existing_ids[address]
            or before.get("name") != resources[address].get("name")
            or after.get("name") != resources[address].get("name")
            or (
                address == "digitalocean_database_cluster.db"
                and after.get("project_id") != RECOVERY_IDS["digitalocean_project.staging"]
            )
            or (
                address == "digitalocean_app.staging"
                and (
                    after.get("urn") != f"do:app:{RECOVERY_APP}"
                    or after.get("active_deployment_id") not in {None, ""}
                    or not app_refresh_equivalent(before, after)
                )
            )
        ):
            changed = sorted(
                key for key in set(before) | set(after) if before.get(key) != after.get(key)
            )
            safe_fields = [
                key
                for key in changed
                if key
                in APP_REFRESH_FIELDS
                | {"id", "name", "spec", "project_id", "deployment_per_page", "timeouts"}
            ]
            raise ValueError(
                "Recovery refresh escaped the original owned resource IDs; "
                f"changed fields: {safe_fields}"
            )
    prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
    if prior.get("child_modules"):
        raise ValueError("Recovery cannot include modules")
    prior_resources = prior.get("resources", [])
    existing_ids = {address: value["id"] for address, value in resources.items()}
    if (
        len(prior_resources) != len(existing_ids)
        or {item.get("address") for item in prior_resources} != set(existing_ids)
        or any(
            item.get("values", {}).get("id") != existing_ids[item["address"]]
            for item in prior_resources
        )
    ):
        raise ValueError("Recovery prior state must contain only the original resource IDs")
    for item in changes:
        address = item["address"]
        change = item["change"]
        if change.get("importing") or item.get("previous_address") or item.get("module_address"):
            raise ValueError("Recovery cannot import, move, or adopt resources")
        before = change.get("before")
        after = change.get("after") or {}
        if address in RECOVERY_IDS:
            if (
                change["actions"] != ["no-op"]
                or not isinstance(before, dict)
                or before.get("id") != existing_ids[address]
                or after != before
                or before.get("name") != resources[address].get("name")
            ):
                raise ValueError("Recovery cannot modify the original project or database")
        elif address == "digitalocean_app.staging" and address in existing_ids:
            if (
                change["actions"] not in [["update"], ["no-op"]]
                or not isinstance(before, dict)
                or before.get("id") != RECOVERY_APP
                or after.get("id") != RECOVERY_APP
                or after.get("project_id") != RECOVERY_IDS["digitalocean_project.staging"]
                or (after.get("spec") or [{}])[0].get("name") != app_name(order)
                or (after.get("spec") or [{}])[0].get("domain")
                != (before.get("spec") or [{}])[0].get("domain")
                or any(
                    service.get("git") != prior_service.get("git")
                    for service, prior_service in zip(
                        (after.get("spec") or [{}])[0].get("service", []),
                        (before.get("spec") or [{}])[0].get("service", []),
                        strict=True,
                    )
                )
            ):
                raise ValueError("Recovery may only update the original failed app in place")
        elif change["actions"] != ["create"] or before is not None:
            raise ValueError("Recovery may only create the missing app and firewall")
        elif address == "digitalocean_app.staging":
            if (after.get("spec") or [{}])[0].get("name") != app_name(order) or after.get(
                "project_id"
            ) != RECOVERY_IDS["digitalocean_project.staging"]:
                raise ValueError("Recovery app escaped the original project")
        elif address == "digitalocean_database_firewall.staging" and (
            after.get("cluster_id") != RECOVERY_IDS["digitalocean_database_cluster.db"]
            or len(after.get("rule", [])) != 1
            or after["rule"][0].get("type") != "app"
            or (
                after["rule"][0].get("value") != RECOVERY_APP
                if "digitalocean_app.staging" in existing_ids
                else (
                    after["rule"][0].get("value") is not None
                    or (change.get("after_unknown", {}).get("rule") or [{}])[0].get("value")
                    is not True
                )
            )
        ):
            raise ValueError("Recovery firewall escaped the original database or new app")


def repair_failed_app_state(order: str) -> None:
    """Preserve the original failed app instead of Terraform replacing it."""
    resources = recovery(order)
    name, _ = identity(order)
    if "digitalocean_app.staging" not in resources or os.environ.get("TF_WORKSPACE") != name:
        raise ValueError("State repair requires the original app and exact workspace")

    def command(*args: str) -> str:
        result = subprocess.run(
            ["terraform", *args],  # noqa: S603,S607 — fixed CLI and arguments, no shell
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if result.returncode:
            raise ValueError("Guarded Terraform state command failed; output withheld")
        return result.stdout

    if command("workspace", "show").strip() != name:
        raise ValueError("Terraform selected a different workspace")
    current = workspace(order)
    if current is None:
        raise ValueError("Original workspace is missing")
    raw = read_raw_state(current)
    local = json.loads(command("state", "pull"))
    if local != raw or not raw.get("lineage") or not isinstance(raw.get("serial"), int):
        raise ValueError("CLI state does not match the verified original workspace")
    instances = [
        instance
        for resource in raw.get("resources", [])
        if resource.get("type") == "digitalocean_app" and resource.get("name") == "staging"
        for instance in resource.get("instances", [])
    ]
    if len(instances) != 1 or instances[0].get("status") != "tainted":
        raise ValueError("Only the original failed app taint marker may be repaired")
    if state_resources(raw) != resources:
        raise ValueError("State resources changed after ownership proof")
    command("untaint", "-lock-timeout=30s", "digitalocean_app.staging")
    after = json.loads(command("state", "pull"))
    verify_app_state_repair(raw, after)


def verify_app_state_repair(before: dict, after: dict) -> None:
    """Ignore serialization order; permit only the original app marker removal."""
    if state_resources(before) != state_resources(after):
        raise ValueError("State repair changed original resource attributes")
    expected = json.loads(json.dumps(before))
    expected["serial"] += 1
    app = next(
        resource
        for resource in expected["resources"]
        if resource["type"] == "digitalocean_app" and resource["name"] == "staging"
    )
    if len(app["instances"]) != 1 or app["instances"][0].get("status") != "tainted":
        raise ValueError("State repair did not start from the original app taint marker")
    app["instances"][0].pop("status")

    def normalize(data: dict) -> dict:
        result = json.loads(json.dumps(data))
        # Terraform rewrites resource ordering and omits empty resource shells.
        # The strict state_resources checks above reject foreign or duplicate shells.
        result["resources"] = sorted(
            [resource for resource in result["resources"] if resource["instances"]],
            key=lambda resource: (resource["type"], resource["name"]),
        )
        return result

    if normalize(after) != normalize(expected):
        raise ValueError("State repair changed more than the original app taint marker")


def previous_state(order: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "filter[workspace][name]": identity(order)[0],
            "filter[organization][name]": ORG,
            "filter[status]": "finalized",
            "page[size]": "2",
        }
    )
    versions = tf(f"/state-versions?{query}")["data"]
    if len(versions) != SERVICE_COUNT:
        raise ValueError("Original app state repair history is missing")
    return read_state_version(versions[1])


def inspect_original_plan(data: dict) -> list:
    run = tf("/runs/run-2H5ufxagxtt3yuZp")["data"]
    if run["relationships"]["workspace"]["data"]["id"] != data["id"]:
        raise ValueError("Diagnostic plan belongs to a different workspace")
    plan_id = run["relationships"]["plan"]["data"]["id"]
    if not re.fullmatch(r"plan-[A-Za-z0-9]+", plan_id):
        raise ValueError("Invalid diagnostic plan identity")
    try:
        plan = tf(f"/plans/{plan_id}/json-output")
    except urllib.error.HTTPError as error:
        if error.code not in {HTTPStatus.FOUND, HTTPStatus.TEMPORARY_REDIRECT}:
            raise
        url = urllib.parse.urlsplit(error.headers.get("Location", ""))
        if (
            url.scheme != "https"
            or url.hostname != "archivist.terraform.io"
            or url.port not in {None, 443}
            or url.username
            or url.password
            or url.fragment
            or not url.path.startswith("/v1/object/")
        ):
            raise ValueError("Plan download redirect is not approved") from None
        plan = request(
            "archivist.terraform.io", url.path + ("?" + url.query if url.query else ""), None
        )

    def fields(before: Any, after: Any, prefix: str = "") -> list[str]:
        if isinstance(before, dict) and isinstance(after, dict):
            results = []
            for key in sorted(set(before) | set(after)):
                # Schema fields only, never dictionary values or dynamic names.
                if re.fullmatch(r"[a-z_]+", key):
                    results.extend(fields(before.get(key), after.get(key), prefix + "." + key))
            return results
        if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
            return [
                path
                for index, pair in enumerate(zip(before, after, strict=True))
                for path in fields(*pair, prefix + f"[{index}]")
            ]
        return [prefix] if before != after else []

    return [
        fields(change["change"].get("before"), change["change"].get("after"))
        for change in plan.get("resource_drift", [])
        if change.get("address") == "digitalocean_app.staging"
    ]


def sanitized_runtime_logs(app_id: str, deployment_id: str, component: str) -> dict:
    response = {}
    for log_type in ["DEPLOY", "RUN_RESTARTED"]:
        try:
            response = do(
                f"/apps/{app_id}/deployments/{deployment_id}/logs"
                f"?type={log_type}&follow=false&tail_lines=200&component_name={component}"
            )
        except urllib.error.HTTPError as error:
            if error.code not in {HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND}:
                raise
            continue
        if response.get("historic_urls") or response.get("live_url"):
            break
    urls = response.get("historic_urls", [])
    if not urls and response.get("live_url"):
        urls = [response["live_url"]]
    logs = ""
    hosts = []
    for url in urls[-3:]:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        hosts.append(host)
        if (
            parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not (host.endswith((".digitalocean.com", ".digitaloceanspaces.com")))
        ):
            continue

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        try:
            # Signed URL, no API token, no redirect and no raw log output.
            with urllib.request.build_opener(NoRedirect()).open(url, timeout=20) as source:
                payload = source.read(262144)
                if payload.startswith(b"\x1f\x8b"):
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as archive:
                        payload = archive.read(262144)
                logs += payload.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, gzip.BadGzipFile, EOFError):
            continue
    markers = {
        "migrations_started": "> Running migrations",
        "migrations_skipped": "> Skipping startup migrations",
        "bootstrap_failed": "Private test bootstrap failed",
        "connection_refused": "Connection refused",
        "connection_timeout": "timeout expired",
        "network_timeout": "Connection timed out",
        "missing_table": "does not exist",
        "duplicate_table": "already exists",
        "unknown_migration": "Can't locate revision",
        "server_started": "> Starting the server",
        "ssl_failure": "certificate verify failed",
    }
    errors = [
        name
        for name in [
            "OperationalError",
            "ProgrammingError",
            "IntegrityError",
            "UndefinedTable",
            "DuplicateTable",
            "DeadlockDetected",
            "RuntimeError",
            "ValueError",
        ]
        if name in logs
    ]
    return {
        "available": bool(logs),
        "log_hosts": hosts,
        "markers": [key for key, value in markers.items() if value.lower() in logs.lower()],
        "error_classes": errors,
        "migration_ids": re.findall(r"Running upgrade [a-f0-9]* -> ([a-f0-9]{12})", logs)[-5:],
    }


def inspect_original_deployment(order: str) -> dict:
    if order != RECOVERY_ORDER or os.environ.get("CUSTOM_DOMAIN") != "hushline.foo":
        raise ValueError("Inspection is restricted to the original authorized test")
    data = workspace(order)
    if data is None:
        raise ValueError("Original workspace is missing")
    validate_workspace(data, order)
    raw_state = read_raw_state(data)
    state = state_resources(raw_state)
    if any(
        state.get(address, {}).get("id") != identifier
        for address, identifier in RECOVERY_IDS.items()
    ):
        raise ValueError("Original resource IDs no longer match")
    app_id = "11ce3bed-e389-4510-81d2-3bdad9146eda"
    if state.get("digitalocean_app.staging", {}).get("id") not in {None, app_id}:
        raise ValueError("Application ID does not match the original creation run")
    live = do(f"/apps/{app_id}")["app"]
    spec = live["spec"]
    domains = {entry.get("domain") for entry in spec.get("domains", [])}
    project_id = RECOVERY_IDS["digitalocean_project.staging"]
    db_id = RECOVERY_IDS["digitalocean_database_cluster.db"]
    members = {item["urn"] for item in inventory(f"/projects/{project_id}/resources", "resources")}
    if (
        live.get("id") != app_id
        or spec.get("name") != app_name(order)
        or "hushline.foo" not in domains
        or members != {f"do:dbaas:{db_id}", f"do:app:{app_id}"}
        or any(
            service.get("git", {}).get("branch") != f"self-service-test/{order}"
            for service in spec.get("services", [])
        )
    ):
        raise ValueError("Live application ownership does not match the original order")
    previous = previous_state(order)
    diff_keys = [
        key
        for key in sorted(set(previous) | set(raw_state))
        if previous.get(key) != raw_state.get(key)
    ]
    previous_app: dict = next(
        (
            resource
            for resource in previous.get("resources", [])
            if resource.get("type") == "digitalocean_app" and resource.get("name") == "staging"
        ),
        {},
    )
    current_app: dict = next(
        (
            resource
            for resource in raw_state.get("resources", [])
            if resource.get("type") == "digitalocean_app" and resource.get("name") == "staging"
        ),
        {},
    )
    app_diff = [
        key
        for key in sorted(set(previous_app) | set(current_app))
        if previous_app.get(key) != current_app.get(key)
    ]
    previous_instance = (previous_app.get("instances") or [{}])[0]
    current_instance = (current_app.get("instances") or [{}])[0]
    instance_diff = [
        key
        for key in sorted(set(previous_instance) | set(current_instance))
        if previous_instance.get(key) != current_instance.get(key)
    ]
    latest = live.get("pending_deployment") or live.get("active_deployment")
    if not latest:
        deployments = do(f"/apps/{app_id}/deployments?per_page=1")["deployments"]
        if not deployments:
            raise ValueError("Original app deployment history is missing")
        latest = deployments[0]
    deployment_id = latest.get("id")
    if not isinstance(deployment_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", deployment_id):
        raise ValueError("Invalid original-app deployment identity")
    deployment = do(f"/apps/{app_id}/deployments/{deployment_id}")["deployment"]

    def steps(values: list) -> list:
        result = []
        for step in values:
            reason = step.get("reason")
            code = reason.get("code") if isinstance(reason, dict) else reason
            result.append(
                {
                    "name": step.get("name"),
                    "component": step.get("component_name"),
                    "status": step.get("status"),
                    "code": code
                    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_-]+", code)
                    else None,
                    "steps": steps(step.get("steps", [])),
                }
            )
        return result

    app_status = [
        instance.get("status", "ready")
        for resource in raw_state.get("resources", [])
        if resource.get("type") == "digitalocean_app" and resource.get("name") == "staging"
        for instance in resource.get("instances", [])
    ]
    migration_flags = [
        next(
            (
                entry.get("value")
                for entry in service.get("envs", [])
                if entry.get("key") == "RUN_STARTUP_MIGRATIONS"
            ),
            None,
        )
        for service in spec.get("services", [])
    ]
    return {
        "order_id": order,
        "app_id": app_id,
        "plan_refresh_fields": inspect_original_plan(data),
        "app_state_status": app_status,
        "state_changed_fields": diff_keys,
        "app_state_changed_fields": app_diff,
        "app_instance_changed_fields": instance_diff,
        "state_serial_advance": raw_state.get("serial", 0) - previous.get("serial", 0),
        "active_deployment_phase": (live.get("active_deployment") or {}).get("phase"),
        "startup_migrations_enabled": bool(migration_flags)
        and all(flag == "true" for flag in migration_flags),
        "phase": deployment.get("phase"),
        "runtime": {
            component: sanitized_runtime_logs(app_id, deployment_id, component)
            for component in ["app", "app-onion"]
        },
        "steps": steps(
            deployment.get("progress", {}).get("steps", [])
            + deployment.get("progress", {}).get("summary_steps", [])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=[
            "preflight",
            "create",
            "record",
            "owned",
            "destroy-plan",
            "remove",
            "recover-check",
            "recover-plan",
            "repair-app-state",
            "inspect",
        ],
    )
    parser.add_argument("order")
    parser.add_argument("plan", nargs="?", type=Path)
    args = parser.parse_args()
    if args.operation == "inspect":
        print(json.dumps(inspect_original_deployment(args.order)))
    elif args.operation == "repair-app-state":
        repair_failed_app_state(args.order)
    elif args.operation == "recover-check":
        resources = recovery(args.order)
        data = workspace(args.order)
        if data is None:
            raise ValueError("Original workspace is missing")
        raw = read_raw_state(data)
        if (
            any(
                instance.get("status") == "tainted"
                for resource in raw.get("resources", [])
                if resource.get("type") == "digitalocean_app" and resource.get("name") == "staging"
                for instance in resource.get("instances", [])
            )
            and "digitalocean_app.staging" in resources
        ):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                print("needs_state_repair=true", file=output)
        elif "digitalocean_app.staging" in resources:
            verify_app_state_repair(previous_state(args.order), raw)
    elif args.operation == "recover-plan":
        if args.plan is None:
            raise ValueError("Recovery requires a checked plan")
        guard_recovery(args.plan, args.order)
    elif args.operation == "preflight":
        preflight(args.order, os.environ["CUSTOM_DOMAIN"])
    elif args.operation == "create":
        create(args.order)
    elif args.operation == "record":
        record(args.order)
    elif args.operation == "owned":
        owned(args.order)
    elif args.operation == "destroy-plan":
        if args.plan is None:
            raise ValueError("Cleanup requires a checked plan")
        guard_destroy(args.plan, args.order, owned(args.order))
    else:
        remove_workspace(args.order)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"Test control-plane request failed with HTTP {error.code}; no mutations permitted."
        ) from None
    except ValueError as error:
        raise SystemExit(f"Test ownership check failed: {error}; no mutations permitted.") from None
    except KeyError as error:
        field = error.args[0]
        if field not in {
            "projects",
            "databases",
            "apps",
            "name",
            "spec",
            "CUSTOM_DOMAIN",
            "STAGING_DO_TOKEN",
        }:
            field = "required field"
        raise SystemExit(
            f"Test cloud inventory is missing {field}; no mutations permitted."
        ) from None
    except OSError:
        raise SystemExit("Test ownership check failed; no further mutations permitted.") from None

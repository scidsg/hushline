"""Fail closed before any mutation of the disposable self-service workspace."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Any

PROJECT = "prj-iEruEQFmaNTCRAtA"
DIRECTORY = "hushline-self-service-test"
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


def request(
    host: str, path: str, token: str, body: dict | None = None, method: str = "GET"
) -> dict:
    if host not in {"app.terraform.io", "api.digitalocean.com"}:
        raise ValueError("Control-plane host is not authorized")
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid control-plane path")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.api+json"}
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
    for app in inventory("/apps", "apps"):
        if app["spec"]["name"] == name or any(
            entry["name"] == domain for entry in app["spec"].get("domains", [])
        ):
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
        or app["spec"].get("name") != name
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
    for resource in data.get("resources", []):
        address = f"{resource['type']}.{resource['name']}"
        if resource.get("mode") != "managed" or resource.get("module") or address not in ADDRESSES:
            raise ValueError("State contains a resource outside the isolated test root")
        instances = resource["instances"]
        if address in results or len(instances) != 1 or instances[0].get("deposed"):
            raise ValueError("State contains ambiguous resource ownership")
        results[address] = instances[0]["attributes"]
    return results


def read_state(data: dict) -> dict:
    version = tf(f"/workspaces/{data['id']}/current-state-version")["data"]
    url = version["attributes"]["hosted-state-download-url"]
    # State URLs are signed by HCP; do not include the API bearer token.
    if not url.startswith("https://"):
        raise ValueError("Invalid state download URL")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 — HTTPS URL returned by authenticated HCP API
        return state_resources(json.loads(response.read()))


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
        or app["spec"][0].get("name") != name
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation", choices=["preflight", "create", "record", "owned", "destroy-plan", "remove"]
    )
    parser.add_argument("order")
    parser.add_argument("plan", nargs="?", type=Path)
    args = parser.parse_args()
    if args.operation == "preflight":
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
    except (ValueError, KeyError, OSError):
        raise SystemExit("Test ownership check failed; no further mutations permitted.") from None

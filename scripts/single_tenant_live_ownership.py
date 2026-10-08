"""Customer-only ownership checks; no production defaults or recovery/adoption path.

Payment authority and saved-plan guards remain independent requirements. These
helpers only address the explicitly configured Single Tenant HCP project and new
customer resource root. API responses and Terraform state must remain private.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

import requests

from scripts.single_tenant_identity import valid_team_id
from scripts.single_tenant_live_plan import RESOURCES, identity

DIRECTORY = "hushline-single-tenant"
PROJECT_NAME = "Hush Line Single Tenant"
MAX_RESPONSE_BYTES = 1048576
MAX_INVENTORY_PAGES = 100
EXPECTED_PROJECT_MEMBERS = 2
MAX_MANIFEST_BYTES = 256
SOURCE_PREFIX = "Hush Line Single Tenant "
PROJECT_ADDRESS = "digitalocean_project.tenant"
APP_ADDRESS = "digitalocean_app.tenant"
DATABASE_ADDRESS = "digitalocean_database_cluster.tenant"
FIREWALL_ADDRESS = "digitalocean_database_firewall.tenant"


class MissingResource(Exception):
    """Only a verified provider HTTP 404 means absence."""


class CloudAPI:
    def __init__(self, *, terraform_token: str, digitalocean_token: str) -> None:
        if not terraform_token or not digitalocean_token:
            raise ValueError("Dedicated Single Tenant cloud credentials are required")
        self.tokens = {
            "https://app.terraform.io": terraform_token,
            "https://api.digitalocean.com": digitalocean_token,
        }

    def request(
        self, method: str, url: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        origin = next((host for host in self.tokens if url.startswith(host + "/")), None)
        if origin is None or method not in {"GET", "POST", "PATCH"}:
            raise ValueError("Unsupported cloud control-plane request")
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(
                    method,
                    url,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + self.tokens[origin],
                        "Content-Type": "application/vnd.api+json"
                        if origin == "https://app.terraform.io"
                        else "application/json",
                    },
                    allow_redirects=False,
                    timeout=(5, 60),
                    stream=True,
                ) as response:
                    if method == "GET" and (
                        (
                            re.fullmatch(
                                r"https://app\.terraform\.io/api/v2/plans/plan-[A-Za-z0-9]+/json-output",
                                url,
                            )
                            and response.status_code == HTTPStatus.TEMPORARY_REDIRECT
                        )
                        or (
                            re.fullmatch(
                                r"https://app\.terraform\.io/api/state-versions/sv-[A-Za-z0-9]+/hosted_state",
                                url,
                            )
                            and response.status_code
                            in {HTTPStatus.FOUND, HTTPStatus.TEMPORARY_REDIRECT}
                        )
                    ):
                        location = response.headers.get("Location", "")
                        if not location.startswith("https://archivist.terraform.io/"):
                            raise ValueError("Private plan redirect escaped its approved host")
                        return {"location": location}
                    if response.status_code == HTTPStatus.NOT_FOUND:
                        raise MissingResource
                    if not HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES:
                        raise ValueError("Cloud control-plane request failed")
                    # HCP run actions acknowledge queuing with 202 and no
                    # resource document. The saved run is polled independently;
                    # an accepted action does not mean its apply has completed.
                    if (
                        method == "POST"
                        and response.status_code == HTTPStatus.ACCEPTED
                        and re.fullmatch(
                            r"https://app\.terraform\.io/api/v2/runs/run-[A-Za-z0-9]+/actions/(apply|discard)",
                            url,
                        )
                    ):
                        return {}
                    body = bytearray()
                    for chunk in response.iter_content(8192):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError("Cloud control-plane response exceeded safety limit")
            result = json.loads(body) if body else {}
            if not isinstance(result, dict):
                raise ValueError("Invalid cloud control-plane response")
            return result
        except (requests.RequestException, ValueError):
            raise ValueError(
                "Cloud control-plane request failed; ownership is unverified"
            ) from None


def verify_team(request: Callable[..., dict[str, Any]], expected: str) -> None:
    """Reject credentials for production or any unreviewed provider team."""
    if not valid_team_id(expected):
        raise ValueError("An explicit reviewed development team identity is required")
    account = request("GET", "https://api.digitalocean.com/v2/account", None).get("account", {})
    if (
        account.get("status") != "active"
        or account.get("team", {}).get("uuid") != expected
        or account.get("team", {}).get("name") != "HushLineDev"
    ):
        raise ValueError("Cloud credential team does not match the isolated development team")


def validate_ids(ids: Any) -> dict[str, str]:
    uuid = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
    if (
        not isinstance(ids, dict)
        or set(ids) != RESOURCES
        or any(
            not isinstance(ids[address], str) or not re.fullmatch(uuid, ids[address])
            for address in RESOURCES - {FIREWALL_ADDRESS}
        )
        or not isinstance(ids[FIREWALL_ADDRESS], str)
        or not re.fullmatch(
            re.escape(ids[DATABASE_ADDRESS]) + r"-[0-9]{18}[0-9a-f]{8}",
            ids[FIREWALL_ADDRESS],
        )
    ):
        raise ValueError("Four exact provider resource IDs are required")
    return ids


def state_resources(state: dict[str, Any]) -> dict[str, Any]:
    result = {}
    seen = set()
    for resource in state.get("resources", []):
        address = str(resource.get("type")) + "." + str(resource.get("name"))
        if (
            address not in RESOURCES
            or address in seen
            or resource.get("module")
            or resource.get("mode") != "managed"
            or resource.get("provider")
            != 'provider["registry.terraform.io/digitalocean/digitalocean"]'
        ):
            raise ValueError("State escaped the exact Single Tenant root")
        seen.add(address)
        instances = resource.get("instances", [])
        if not instances:
            continue
        if len(instances) != 1 or instances[0].get("deposed") or "index_key" in instances[0]:
            raise ValueError("State contains ambiguous resource ownership")
        result[address] = instances[0]["attributes"]
    return result


def validate_state(resources: dict[str, Any], order: str) -> dict[str, str]:
    name, app_name = identity(order)
    if set(resources) != RESOURCES:
        raise ValueError("Ownership requires the complete exact customer resource set")
    project = resources[PROJECT_ADDRESS]
    app = resources[APP_ADDRESS]
    database = resources[DATABASE_ADDRESS]
    firewall = resources[FIREWALL_ADDRESS]
    if (
        project.get("name") != name
        or project.get("description") != "Owned Hush Line Single Tenant " + name
        or app.get("spec", [{}])[0].get("name") != app_name
        or database.get("name") != name
        or app.get("project_id") != project.get("id")
        or database.get("project_id") != project.get("id")
        or firewall.get("cluster_id") != database.get("id")
        or len(firewall.get("rule", [])) != 1
        or firewall["rule"][0].get("type") != "app"
        or firewall["rule"][0].get("value") != app.get("id")
    ):
        raise ValueError("Resource names or relationships escaped this customer project")
    return validate_ids({address: value.get("id") for address, value in resources.items()})


class Ownership:
    def __init__(
        self,
        *,
        organization: str,
        project_id: str,
        request: Callable[..., dict[str, Any]],
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", organization) or not re.fullmatch(
            r"prj-[A-Za-z0-9]+", project_id
        ):
            raise ValueError("An explicit isolated HCP organization and project are required")
        self.organization = organization
        self.project_id = project_id
        self.request = request

    def tf(
        self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.request(method, "https://app.terraform.io/api/v2" + path, payload)

    def do(self, path: str) -> dict[str, Any]:
        return self.request("GET", "https://api.digitalocean.com/v2" + path, None)

    def verify_project(self) -> None:
        data = self.tf("/projects/" + self.project_id)["data"]
        if (
            data.get("id") != self.project_id
            or data.get("attributes", {}).get("name") != PROJECT_NAME
            or data.get("relationships", {}).get("organization", {}).get("data", {}).get("id")
            != self.organization
        ):
            raise ValueError("Configured HCP project is not the isolated Single Tenant project")

    def workspace(self, order: str) -> dict[str, Any] | None:
        name, _ = identity(order)
        try:
            return self.tf(f"/organizations/{self.organization}/workspaces/{name}")["data"]
        except MissingResource:
            return None

    def validate_workspace(self, data: dict[str, Any], order: str) -> dict[str, Any]:
        name, _ = identity(order)
        attrs = data.get("attributes", {})
        if (
            not re.fullmatch(r"ws-[A-Za-z0-9]+", data.get("id", ""))
            or attrs.get("name") != name
            or attrs.get("source-name") != SOURCE_PREFIX + order
            or attrs.get("working-directory") != DIRECTORY
            or attrs.get("execution-mode") != "remote"
            or attrs.get("terraform-version") != "1.13.5"
            or attrs.get("auto-apply") is not False
            or attrs.get("auto-apply-run-trigger") is not False
            or attrs.get("global-remote-state") is not False
            or attrs.get("queue-all-runs") is not False
            or attrs.get("vcs-repo") is not None
            or attrs.get("auto-destroy-at") is not None
            or attrs.get("auto-destroy-activity-duration") is not None
            or data.get("relationships", {}).get("project", {}).get("data", {}).get("id")
            != self.project_id
        ):
            raise ValueError("Workspace ownership or isolation differs from the customer order")
        manifest = json.loads(attrs.get("description", ""))
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"v", "o", "r"}
            or not isinstance(manifest.get("v"), int)
            or isinstance(manifest.get("v"), bool)
            or manifest.get("v") != 1
            or manifest.get("o") != order
        ):
            raise ValueError("Workspace manifest belongs to another order")
        if manifest["r"] is not None:
            if not isinstance(manifest["r"], list) or len(manifest["r"]) != len(RESOURCES):
                raise ValueError("Invalid recorded resource ownership")
            manifest["r"] = validate_ids(dict(zip(sorted(RESOURCES), manifest["r"], strict=True)))
        return manifest

    def create_workspace(self, order: str) -> str:
        name, _ = identity(order)
        self.verify_project()
        if self.workspace(order) is not None:
            raise ValueError("Creation cannot adopt an existing workspace")
        attrs = {
            "name": name,
            "source-name": SOURCE_PREFIX + order,
            "description": json.dumps({"v": 1, "o": order, "r": None}),
            "working-directory": DIRECTORY,
            "auto-apply": False,
            "auto-apply-run-trigger": False,
            "global-remote-state": False,
            "queue-all-runs": False,
            "execution-mode": "remote",
            "terraform-version": "1.13.5",
            "allow-destroy-plan": True,
        }
        data = self.tf(
            f"/organizations/{self.organization}/workspaces",
            method="POST",
            payload={
                "data": {
                    "type": "workspaces",
                    "attributes": attrs,
                    "relationships": {
                        "project": {"data": {"type": "projects", "id": self.project_id}}
                    },
                }
            },
        )["data"]
        self.validate_workspace(data, order)
        self.tf(
            f"/workspaces/{data['id']}/relationships/tags",
            method="POST",
            payload={"data": [{"type": "tags", "attributes": {"name": "single-tenant"}}]},
        )
        return str(data["id"])

    def inventory(self, path: str, key: str) -> list[dict[str, Any]]:
        values = []
        for page in range(1, MAX_INVENTORY_PAGES + 1):
            data = self.do(f"{path}?per_page=200&page={page}")
            next_page = data.get("links", {}).get("pages", {}).get("next")
            if key not in data and path == "/apps" and key == "apps":
                metadata = data.get("meta")
                if (
                    not isinstance(metadata, dict)
                    or not isinstance(metadata.get("total"), int)
                    or isinstance(metadata.get("total"), bool)
                    or metadata["total"] != 0
                    or next_page is not None
                ):
                    raise ValueError("Missing app inventory is not verified empty")
                items = []
            else:
                items = data[key]
            if items is None and path == "/databases" and key == "databases":
                # The live API returns an explicit null for no database clusters.
                # Never normalize missing fields, API errors or an incomplete page.
                metadata = data.get("meta")
                if next_page is not None or (
                    metadata is not None
                    and (
                        not isinstance(metadata, dict)
                        or not isinstance(metadata.get("total", 0), int)
                        or isinstance(metadata.get("total", 0), bool)
                        or metadata.get("total", 0) != 0
                    )
                ):
                    raise ValueError("Null database inventory is not verified empty")
                items = []
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("Invalid cloud resource inventory")
            values.extend(items)
            if not next_page:
                return values
        raise ValueError("Cloud inventory exceeded its safety limit")

    def preflight(self, order: str, domain: str) -> None:
        name, app_name = identity(order)
        self.verify_project()
        if self.workspace(order) is not None:
            raise ValueError("Creation cannot adopt an existing workspace")
        for path, key in [("/projects", "projects"), ("/databases", "databases")]:
            if any(item.get("name") == name for item in self.inventory(path, key)):
                raise ValueError("Customer name already belongs to an existing resource")
        for app in self.inventory("/apps", "apps"):
            spec = app["spec"]
            domains = spec.get("domains", [])
            if any("domain" not in item and item.get("type") != "DEFAULT" for item in domains):
                raise ValueError("Custom domain inventory lacks its hostname")
            if spec.get("name") == app_name or any(
                item.get("domain") == domain for item in domains
            ):
                raise ValueError("Customer hostname or app name already belongs to an instance")

    def verify_live(self, order: str, ids: dict[str, str]) -> None:
        validate_ids(ids)
        name, app_name = identity(order)
        project = self.do("/projects/" + ids[PROJECT_ADDRESS])["project"]
        app = self.do("/apps/" + ids[APP_ADDRESS])["app"]
        database = self.do("/databases/" + ids[DATABASE_ADDRESS])["database"]
        if (
            project.get("id") != ids[PROJECT_ADDRESS]
            or project.get("name") != name
            or project.get("description") != "Owned Hush Line Single Tenant " + name
            or app.get("id") != ids[APP_ADDRESS]
            or app.get("spec", {}).get("name") != app_name
            or database.get("id") != ids[DATABASE_ADDRESS]
            or database.get("name") != name
            or database.get("project_id") != ids[PROJECT_ADDRESS]
        ):
            raise ValueError("Provider resources do not match the recorded customer order")
        members = self.inventory("/projects/" + ids[PROJECT_ADDRESS] + "/resources", "resources")
        if len(members) != EXPECTED_PROJECT_MEMBERS or {item["urn"] for item in members} != {
            "do:app:" + ids[APP_ADDRESS],
            "do:dbaas:" + ids[DATABASE_ADDRESS],
        }:
            raise ValueError("Project includes resources with different ownership")

    def verify_services_absent(self, order: str, ids: dict[str, str]) -> None:
        validate_ids(ids)
        name, _ = identity(order)
        for path, address in [("/apps/", APP_ADDRESS), ("/databases/", DATABASE_ADDRESS)]:
            try:
                self.do(path + ids[address])
            except MissingResource:
                continue
            raise ValueError("An owned service remains; project deletion is forbidden")
        project = self.do("/projects/" + ids[PROJECT_ADDRESS])["project"]
        if (
            project.get("id") != ids[PROJECT_ADDRESS]
            or project.get("name") != name
            or project.get("description") != "Owned Hush Line Single Tenant " + name
        ):
            raise ValueError("Remaining project ownership changed")
        if self.inventory("/projects/" + ids[PROJECT_ADDRESS] + "/resources", "resources"):
            raise ValueError("Project membership must be empty before project deletion")

    def record(self, order: str, resources: dict[str, Any]) -> dict[str, str]:
        self.verify_project()
        data = self.workspace(order)
        if data is None:
            raise ValueError("Owned customer workspace is missing")
        manifest = self.validate_workspace(data, order)
        if manifest["r"] is not None:
            raise ValueError("The original ownership record cannot be overwritten")
        ids = validate_state(resources, order)
        self.verify_live(order, ids)
        manifest["r"] = [ids[address] for address in sorted(RESOURCES)]
        description = json.dumps(manifest, separators=(",", ":"))
        if len(description.encode()) > MAX_MANIFEST_BYTES:
            raise ValueError("Ownership manifest exceeds the metadata safety limit")
        self.tf(
            "/workspaces/" + data["id"],
            method="PATCH",
            payload={
                "data": {
                    "id": data["id"],
                    "type": "workspaces",
                    "attributes": {"description": description},
                }
            },
        )
        return ids

    def owned(self, order: str, resources: dict[str, Any]) -> dict[str, str]:
        self.verify_project()
        data = self.workspace(order)
        if data is None:
            raise ValueError("Owned customer workspace is missing")
        manifest = self.validate_workspace(data, order)
        ids = validate_state(resources, order)
        if manifest["r"] != ids:
            raise ValueError("Resource IDs differ from the original ownership record")
        self.verify_live(order, ids)
        return ids

    def verify_project_absent(self, order: str, ids: dict[str, str]) -> None:
        identity(order)
        validate_ids(ids)
        for path, address in [
            ("/apps/", APP_ADDRESS),
            ("/databases/", DATABASE_ADDRESS),
            ("/projects/", PROJECT_ADDRESS),
        ]:
            try:
                self.do(path + ids[address])
            except MissingResource:
                continue
            raise ValueError("An owned provider resource remains")

    def remove_empty_workspace(self, order: str, state: dict[str, Any]) -> None:
        self.verify_project()
        data = self.workspace(order)
        if data is None:
            raise ValueError("The recorded workspace is missing")
        manifest = self.validate_workspace(data, order)
        if manifest["r"] is None or state_resources(state):
            raise ValueError("Only an empty, recorded customer workspace may be removed")
        self.verify_project_absent(order, manifest["r"])
        self.tf("/workspaces/" + data["id"] + "/actions/safe-delete", method="POST")

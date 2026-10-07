"""HCP saved-run application and private artifacts for the isolated customer root.

Automatic application means applying the exact guarded run, never enabling
workspace auto-apply or bypassing policy/task checks. No logs are downloaded.
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import time
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

MAX_ARTIFACT_BYTES = 16777216
POLL_SECONDS = 5
MAX_POLLS = 720


class HCP:
    def __init__(
        self,
        *,
        request: Callable[..., dict[str, Any]],
        transfer: Callable[..., bytes] | None = None,
    ) -> None:
        self.request = request
        self.transfer = transfer or self.artifact

    def tf(
        self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self.request(method, "https://app.terraform.io/api/v2" + path, payload)

    @staticmethod
    def artifact(url: str, *, data: bytes | None = None) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "archivist.terraform.io"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Private artifact URL escaped its approved HCP host")
        # Signed artifact URLs are credentials. Never print them or forward an
        # API bearer credential to this origin or any redirect.
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.request(
                    "PUT" if data is not None else "GET",
                    url,
                    data=data,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=(5, 60),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if not HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES:
                        raise ValueError("Private artifact transfer failed")
                    body = bytearray()
                    for chunk in response.iter_content(8192):
                        body.extend(chunk)
                        if len(body) > MAX_ARTIFACT_BYTES:
                            raise ValueError("Private artifact exceeded safety limit")
                    return bytes(body)
        except requests.RequestException:
            raise ValueError("Private artifact transfer failed") from None

    def configuration(self, workspace: str, root: Path, variables: dict[str, Any]) -> str:
        if not re.fullmatch(r"ws-[A-Za-z0-9]+", workspace) or root.name != "hushline-single-tenant":
            raise ValueError("Only the isolated customer configuration may be uploaded")
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as output:
            files = sorted([*root.glob("*.tf"), root / ".terraform.lock.hcl"])
            if not files or any(path.is_symlink() or not path.is_file() for path in files):
                raise ValueError("Customer root files are incomplete or ambiguous")
            for path in files:
                output.add(path, arcname="hushline-single-tenant/" + path.name, recursive=False)
            encoded = json.dumps(variables, separators=(",", ":")).encode()
            info = tarfile.TarInfo("hushline-single-tenant/customer.auto.tfvars.json")
            info.size, info.mode = len(encoded), 0o600
            output.addfile(info, io.BytesIO(encoded))
        version = self.tf(
            "/workspaces/" + workspace + "/configuration-versions",
            method="POST",
            payload={
                "data": {
                    "type": "configuration-versions",
                    "attributes": {"auto-queue-runs": False, "speculative": False},
                }
            },
        )["data"]
        identifier = version.get("id", "")
        if not re.fullmatch(r"cv-[A-Za-z0-9]+", identifier):
            raise ValueError("Invalid customer configuration version")
        self.transfer(version["attributes"]["upload-url"], data=archive.getvalue())
        return identifier

    def plan(self, workspace: str, configuration: str, *, phase: str) -> tuple[str, dict[str, Any]]:
        if phase not in {"create", "services", "project"}:
            raise ValueError("Unsupported exact customer plan phase")
        attrs: dict[str, Any] = {
            "message": "Guarded Single Tenant " + phase,
            "auto-apply": False,
            "is-destroy": phase != "create",
        }
        if phase == "services":
            attrs["target-addrs"] = [
                "digitalocean_app.tenant",
                "digitalocean_database_cluster.tenant",
                "digitalocean_database_firewall.tenant",
            ]
        run = self.tf(
            "/runs",
            method="POST",
            payload={
                "data": {
                    "type": "runs",
                    "attributes": attrs,
                    "relationships": {
                        "workspace": {"data": {"type": "workspaces", "id": workspace}},
                        "configuration-version": {
                            "data": {"type": "configuration-versions", "id": configuration}
                        },
                    },
                }
            },
        )["data"]
        identifier = run.get("id", "")
        if not re.fullmatch(r"run-[A-Za-z0-9]+", identifier):
            raise ValueError("Invalid saved customer run")
        data = self.wait(
            identifier, {"planned", "cost_estimated", "policy_checked", "post_plan_completed"}
        )
        if (
            data.get("relationships", {}).get("workspace", {}).get("data", {}).get("id")
            != workspace
        ):
            raise ValueError("Saved run belongs to another workspace")
        plan_id = data["relationships"]["plan"]["data"]["id"]
        if not re.fullmatch(r"plan-[A-Za-z0-9]+", plan_id):
            raise ValueError("Invalid saved customer plan")
        # The JSON API endpoint redirects to a signed Archivist URL. Resolve that
        # one redirect separately so API authentication never follows it.
        token_response = self.tf("/plans/" + plan_id)
        signed = token_response["data"]["attributes"].get("json-output-redacted")
        if signed:
            raise ValueError("A redacted plan cannot prove exact secret and credential scope")
        return identifier, self.plan_json(plan_id)

    def plan_json(self, plan_id: str) -> dict[str, Any]:
        # The authenticated transport supplies the single validated JSON-output
        # redirect as a dedicated operation, not arbitrary automatic redirects.
        response = self.tf("/plans/" + plan_id + "/json-output")
        return (
            json.loads(self.transfer(response["location"]))
            if set(response) == {"location"}
            else response
        )

    def wait(self, run: str, terminal: set[str]) -> dict[str, Any]:
        for _ in range(MAX_POLLS):
            data = self.tf("/runs/" + run)["data"]
            status = data.get("attributes", {}).get("status")
            if status in terminal and (
                terminal == {"applied"}
                or data.get("attributes", {}).get("actions", {}).get("is-confirmable") is True
            ):
                return data
            if status in {
                "errored",
                "canceled",
                "force_canceled",
                "discarded",
                "policy_soft_failed",
                "policy_override",
                "planned_and_finished",
            }:
                raise ValueError("Customer run stopped before guarded application")
            time.sleep(POLL_SECONDS)
        raise ValueError("Customer run exceeded its expected duration")

    def apply(self, run: str, workspace: str) -> None:
        data = self.tf("/runs/" + run)["data"]
        if (
            data.get("attributes", {}).get("status")
            not in {"planned", "cost_estimated", "policy_checked", "post_plan_completed"}
            or data.get("relationships", {}).get("workspace", {}).get("data", {}).get("id")
            != workspace
            or data.get("attributes", {}).get("actions", {}).get("is-confirmable") is not True
        ):
            raise ValueError("Exact saved run is not eligible for application")
        self.tf(
            "/runs/" + run + "/actions/apply",
            method="POST",
            payload={"comment": "Paid-order authority and exact resource plan verified"},
        )
        self.wait(run, {"applied"})

    def state(self, workspace: str) -> dict[str, Any]:
        version = self.tf("/workspaces/" + workspace + "/current-state-version")["data"]
        return json.loads(self.transfer(version["attributes"]["hosted-state-download-url"]))

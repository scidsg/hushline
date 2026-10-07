"""Read trusted workflow results and recover status when a callback was missed.

Artifacts are decrypted only after the immutable default-branch workflow content
and first-attempt provenance are verified. No cloud operation is retried here.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.single_tenant_live_envelope import decrypt
from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_publish import Publisher

MAX_RESPONSE_BYTES = 16777216
MAX_PAGES = 10
MAX_ENVELOPE_BYTES = 65536
ARTIFACT_VISIBILITY_SECONDS = 120


class Collector:
    def __init__(
        self, *, ledger: Ledger, publisher: Publisher, api: Callable[[str], bytes] | None = None
    ) -> None:
        self.ledger = ledger
        self.publisher = publisher
        self.api = api or self.github

    @staticmethod
    def github(path: str) -> bytes:
        if not path.startswith("repos/scidsg/hushline/") or any(
            value in path for value in ("\n", "\r", "..")
        ):
            raise ValueError("Read-only GitHub request escaped the customer repository")
        try:
            result = subprocess.run(
                [  # noqa: S603 — fixed read-only CLI and validated repository path
                    "/opt/homebrew/bin/gh",
                    "api",
                    path,
                ],
                capture_output=True,
                check=False,
                timeout=60,
            )  # — fixed authenticated CLI and validated repository path
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("Read-only workflow status is unavailable") from None
        if result.returncode or len(result.stdout) > MAX_RESPONSE_BYTES:
            raise ValueError("Read-only workflow status is unavailable")
        return result.stdout

    def document(self, path: str) -> dict[str, Any]:
        value = json.loads(self.api(path))
        if not isinstance(value, dict):
            raise ValueError("Invalid read-only workflow response")
        return value

    def blob(self, filename: str) -> str:
        return self.publisher.git(
            self.publisher.app,
            ["rev-parse", self.publisher.app_sha + ":.github/workflows/" + filename],
        ).strip()

    def release(self) -> None:
        self.environment()
        for filename in ("single_tenant_request.yml", "single_tenant_lifecycle.yml"):
            active = self.document(
                "repos/scidsg/hushline/contents/.github/workflows/" + filename + "?ref=main"
            )
            if active.get("sha") != self.blob(filename):
                raise ValueError("The reviewed automatic customer workflow is not released")
        for name, expected in (
            ("SINGLE_TENANT_SOURCE_SHA", self.publisher.app_sha),
            ("SINGLE_TENANT_INFRA_SHA", self.publisher.infra_sha),
        ):
            if (
                self.document("repos/scidsg/hushline/actions/variables/" + name).get("value")
                != expected
            ):
                raise ValueError("Automatic workflow release does not match the publisher")

    def environment(self) -> None:
        prefix = "repos/scidsg/hushline/environments/single-tenant-automation"
        environment = self.document(prefix)
        if (
            environment.get("name") != "single-tenant-automation"
            or environment.get("deployment_branch_policy")
            != {"protected_branches": False, "custom_branch_policies": True}
            or any(
                rule.get("type") in {"required_reviewers", "wait_timer", "custom"}
                for rule in environment.get("protection_rules", [])
            )
        ):
            raise ValueError("Customer automation must use its isolated review-free environment")
        branches = self.document(prefix + "/deployment-branch-policies")
        policies = branches.get("branch_policies", [])
        if (
            branches.get("total_count") != 1
            or len(policies) != 1
            or policies[0].get("name") != "main"
            or policies[0].get("type") != "branch"
        ):
            raise ValueError("Customer cloud secrets must be confined to the default branch")
        secrets = self.document(prefix + "/secrets")
        required = {
            "SINGLE_TENANT_CONFIG_READ_TOKEN",
            "SINGLE_TENANT_DO_TOKEN",
            "SINGLE_TENANT_TF_TOKEN",
            "SINGLE_TENANT_PORTAL_KEY",
            "SINGLE_TENANT_WORKFLOW_KEY",
            "SINGLE_TENANT_SMTP_JSON",
        }
        if not required.issubset({item["name"] for item in secrets.get("secrets", [])}):
            raise ValueError("Dedicated customer automation credentials are not configured")
        for name in (
            "SINGLE_TENANT_TF_ORGANIZATION",
            "SINGLE_TENANT_TF_PROJECT",
            "SINGLE_TENANT_DO_TEAM_ID",
            "SINGLE_TENANT_AUTHORITY_ORIGIN",
            "SINGLE_TENANT_CONTROL_ORIGIN",
        ):
            if not self.document("repos/scidsg/hushline/actions/variables/" + name).get("value"):
                raise ValueError("Explicit customer automation configuration is missing")

    def envelope(self, identifier: str) -> dict[str, Any]:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
            raise ValueError("Invalid workflow artifact identity")
        encoded = self.api("repos/scidsg/hushline/actions/artifacts/" + identifier + "/zip")
        try:
            with zipfile.ZipFile(io.BytesIO(encoded)) as archive:
                items = archive.infolist()
                if (
                    len(items) != 1
                    or items[0].filename != "single-tenant-result.json"
                    or items[0].file_size > MAX_ENVELOPE_BYTES
                ):
                    raise ValueError("Encrypted workflow artifact escaped its exact result file")
                value = json.loads(archive.read(items[0]))
        except (zipfile.BadZipFile, OSError, RuntimeError):
            raise ValueError("Encrypted workflow artifact could not be authenticated") from None
        if not isinstance(value, dict) or set(value) != {"ciphertext"}:
            raise ValueError("Invalid encrypted workflow artifact")
        return value["ciphertext"]

    def discover(self) -> None:
        cursor = self.ledger.collection_cursor()
        newest = cursor
        for page in range(1, MAX_PAGES + 1):
            runs = self.document(
                f"repos/scidsg/hushline/actions/workflows/single_tenant_lifecycle.yml/runs?event=workflow_run&per_page=30&page={page}"
            )["workflow_runs"]
            stop = not runs
            for run in runs:
                identifier = str(run["id"])
                self.ledger.track_run(identifier)
                newest = max(newest, int(identifier))
                if int(identifier) <= cursor:
                    stop = True
            if stop:
                self.ledger.collection_checkpoint(newest)
                return
        raise ValueError("New workflow history exceeded its reconciliation safety limit")

    def preflight_failure(self, run: dict[str, Any], keys: list[dict[str, Any]]) -> bool:
        """Report a failed trusted job that stopped before producing its artifact."""
        if run.get("conclusion") not in {"failure", "timed_out", "cancelled", "action_required"}:
            return False
        title = re.fullmatch(
            r"Single Tenant single-tenant-request/([a-f0-9]{32})/"
            r"(provision|retire)-([1-9][0-9]{0,6})",
            run.get("display_title", ""),
        )
        try:
            finished = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return False
        if not title or finished > datetime.now(UTC) - timedelta(
            seconds=ARTIFACT_VISIBILITY_SECONDS
        ):
            return False
        order, purpose, revision_text = title.groups()
        revision = int(revision_text)
        sha = self.ledger.published_request(order, purpose, revision)
        owner = next((item["owner"] for item in keys if item["order_id"] == order), None)
        if not sha or not owner:
            return False
        self.ledger.event(
            order,
            owner,
            purpose=purpose,
            revision=revision,
            public_sha=sha,
            result={
                "state": "failed",
                "failure_stage": "workflow-preflight",
                "workflow_url": "https://github.com/scidsg/hushline/actions/runs/" + str(run["id"]),
            },
        )
        return True

    def reconcile(self) -> int:
        self.discover()
        keys = self.ledger.result_keys()
        count = 0
        for run_id in self.ledger.unfinished_runs():
            run = self.document("repos/scidsg/hushline/actions/runs/" + run_id)
            if run.get("status") != "completed":
                continue
            if (
                run.get("event") != "workflow_run"
                or run.get("run_attempt") != 1
                or not re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", ""))
            ):
                self.ledger.finish_run(run_id)
                continue
            workflow = self.document(
                "repos/scidsg/hushline/contents/.github/workflows/single_tenant_lifecycle.yml?ref="
                + run["head_sha"]
            )
            if workflow.get("sha") != self.blob("single_tenant_lifecycle.yml"):
                self.ledger.finish_run(run_id)
                continue
            artifacts = self.document(
                "repos/scidsg/hushline/actions/runs/" + run_id + "/artifacts"
            )["artifacts"]
            found = False
            for artifact in artifacts:
                identifier = str(artifact["id"])
                if (
                    artifact.get("expired")
                    or artifact.get("name") != "single-tenant-result-" + run_id
                ):
                    continue
                if self.ledger.artifact_seen(identifier):
                    found = True
                    continue
                encrypted = self.envelope(identifier)
                for key in keys:
                    try:
                        body = decrypt(key["claim_private_key"], encrypted)
                    except (ValueError, KeyError):
                        continue
                    expected = {"order_id", "owner", "purpose", "revision", "public_sha", "result"}
                    if (
                        set(body) != expected
                        or body["order_id"] != key["order_id"]
                        or body["owner"] != key["owner"]
                    ):
                        raise ValueError("Encrypted result belongs to different request ownership")
                    result = decrypt(key["claim_private_key"], body["result"])
                    self.ledger.event(
                        body["order_id"],
                        body["owner"],
                        purpose=body["purpose"],
                        revision=body["revision"],
                        public_sha=body["public_sha"],
                        result=result,
                    )
                    self.ledger.artifact_record(identifier)
                    count += 1
                    found = True
                    break
                if self.ledger.artifact_seen(identifier):
                    found = True
            if found or self.preflight_failure(run, keys):
                self.ledger.finish_run(run_id)
        return count

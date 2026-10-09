"""Automated exact-order lifecycle; no retries, adoption or shared expiry exception."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.single_tenant_live_hcp import HCP
from scripts.single_tenant_live_ownership import APP_ADDRESS, Ownership, state_resources
from scripts.single_tenant_live_plan import guard_create, guard_delete


class Lifecycle:
    def __init__(  # noqa: PLR0913 — independent lifecycle trust roots and dependencies
        self,
        *,
        ownership: Ownership,
        hcp: HCP,
        authority: Callable[..., dict[str, Any]],
        branch: Callable[[str], None],
        progress: Callable[[dict[str, Any]], None],
        onion_check: Callable[[str], None],
    ) -> None:
        self.checks: dict[str, bool] = {}
        self.stage = "request"
        self.ownership = ownership
        self.hcp = hcp
        self.authority = authority
        self.branch = branch
        self.progress = progress
        self.onion_check = onion_check

    def provision(
        self, config: dict[str, Any], root: Path, variables: dict[str, Any]
    ) -> dict[str, Any]:
        order, domain = config["order_id"], config["domain"]
        self.stage = "authority"
        self.authority(config, "provision")
        self.stage = "preflight"
        self.ownership.preflight(order, domain)
        self.stage = "workspace"
        workspace = self.ownership.create_workspace(order)
        self.stage = "build"
        self.branch(order)
        self.stage = "configuration"
        version = self.hcp.configuration(workspace, root, variables)
        self.progress({"state": "provisioning"})
        self.stage = "plan"
        run, plan = self.hcp.plan(workspace, version, phase="create")
        guard_create(
            plan,
            order,
            config["payment"]["license_limit"],
            automation_token=variables["DO_TOKEN"],
            image_digest=variables["APP_IMAGE_DIGEST"],
            app_secrets={
                key: variables[key]
                for key in ("SECRET_KEY", "ENCRYPTION_KEY", "SESSION_FERNET_KEY")
            },
        )
        # Payment can change while a cloud plan is running. Recheck independently
        # immediately before applying that exact saved plan, without reviews.
        self.stage = "authority"
        self.authority(config, "provision")
        workspace_data = self.ownership.workspace(order)
        if workspace_data is None or workspace_data["id"] != workspace:
            raise ValueError("Original customer workspace changed after planning")
        self.ownership.validate_workspace(workspace_data, order)
        self.stage = "apply"
        self.hcp.apply(run, workspace)
        self.stage = "ownership"
        resources = state_resources(self.hcp.state(workspace))
        ids = self.ownership.record(order, resources)
        self.checks["infrastructure"] = True
        self.progress({"state": "provisioning", "checks": dict(self.checks)})
        self.stage = "initializer"
        app = self.ownership.do("/apps/" + ids[APP_ADDRESS])["app"]
        if app.get("active_deployment", {}).get("phase") != "ACTIVE":
            raise ValueError("Owned app initializer and service deployment have not passed")
        self.stage = "onion"
        self.onion_check(variables["ONION_HOSTNAME"])
        self.checks["configuration"] = True
        return {
            **(
                {"build_source_sha": config["build_source_sha"]}
                if "build_source_sha" in config
                else {}
            ),
            "state": "awaiting_dns",
            "ingress": app["default_ingress"].removeprefix("https://").rstrip("/"),
            "claim": variables["single_tenant_admin_claim"],
            "checks": {"infrastructure": True, "configuration": True},
        }

    def retire(
        self, config: dict[str, Any], root: Path, variables: dict[str, Any]
    ) -> dict[str, Any]:
        order = config["order_id"]
        self.stage = "authority"
        self.authority(config, "retire")
        workspace_data = self.ownership.workspace(order)
        if workspace_data is None:
            raise ValueError("The recorded customer workspace is missing")
        self.ownership.validate_workspace(workspace_data, order)
        workspace = workspace_data["id"]
        ids = self.ownership.owned(order, state_resources(self.hcp.state(workspace)))
        self.stage = "configuration"
        version = self.hcp.configuration(workspace, root, variables)
        self.progress({"state": "retiring"})
        self.stage = "service-plan"
        services_run, plan = self.hcp.plan(workspace, version, phase="services")
        guard_delete(plan, order, ids, phase="services", automation_token=variables["DO_TOKEN"])
        self.stage = "authority"
        self.authority(config, "retire")
        if self.ownership.owned(order, state_resources(self.hcp.state(workspace))) != ids:
            raise ValueError("Resource ownership changed after service planning")
        self.stage = "service-apply"
        self.hcp.apply(services_run, workspace)
        self.stage = "service-absence"
        self.ownership.verify_services_absent(order, ids)
        # A fresh plan after verified service removal refreshes project membership.
        self.stage = "project-plan"
        project_run, plan = self.hcp.plan(workspace, version, phase="project")
        guard_delete(plan, order, ids, phase="project", automation_token=variables["DO_TOKEN"])
        self.stage = "authority"
        self.authority(config, "retire")
        self.stage = "service-absence"
        self.ownership.verify_services_absent(order, ids)
        self.stage = "project-apply"
        self.hcp.apply(project_run, workspace)
        self.stage = "project-absence"
        self.ownership.verify_project_absent(order, ids)
        self.stage = "workspace-removal"
        self.ownership.remove_empty_workspace(order, self.hcp.state(workspace))
        if self.ownership.workspace(order) is not None:
            raise ValueError("The empty customer workspace is still present")
        return {"state": "retired"}

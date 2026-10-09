"""Redeploy one already-owned app from an exact signed production-release candidate."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from scripts.single_tenant_live_hcp import HCP
from scripts.single_tenant_live_image import IMAGE, image_source, release_image
from scripts.single_tenant_live_ownership import APP_ADDRESS, Ownership, state_resources
from scripts.single_tenant_live_plan import APP_REPOSITORY, identity
from scripts.single_tenant_live_release import resolve, validate_target

MAX_DEPLOYMENT_POLLS = 360
BUILD_COMPONENT_COUNT = 3
MAX_MARKER_BYTES = 4096


def sources(deployment: dict[str, Any], digest: str) -> bool:
    spec = deployment.get("spec", {})
    values = [*spec.get("services", []), *spec.get("jobs", [])]
    return (
        len(values) == BUILD_COMPONENT_COUNT
        and {value.get("name") for value in values} == {"app", "app-onion", "initialize-instance"}
        and all(
            all(
                value.get("image", {}).get(key) == expected
                for key, expected in image_source(digest).items()
            )
            and not value.get("image", {}).get("tag")
            and not any(value.get(key) for key in ("git", "github", "gitlab"))
            for value in values
        )
    )


class Upgrade:
    def __init__(  # noqa: PLR0913 — independent existing-resource and release trust roots
        self,
        *,
        ownership: Ownership,
        hcp: HCP,
        github: Callable[..., dict[str, Any]],
        authority: Callable[..., dict[str, Any]],
        authority_origin: str,
        progress: Callable[[dict[str, Any]], None],
        archive: Callable[[int], bytes] | None = None,
    ) -> None:
        self.owner, self.hcp, self.github = ownership, hcp, github
        self.authority, self.origin, self.progress = authority, authority_origin, progress
        self.archive = archive
        self.stage = "upgrade-release"

    def build(self, config: dict[str, Any]) -> None:
        target, order = config["release"], config["order_id"]
        prefix = "/repos/scidsg/hushline/"
        candidate = self.github("GET", prefix + "commits/" + target["build_sha"])
        if (
            candidate.get("sha") != target["build_sha"]
            or candidate.get("commit", {}).get("verification", {}).get("verified") is not True
            or candidate.get("committer", {}).get("login") != "hushline-dev"
            or [p.get("sha") for p in candidate.get("parents", [])] != [target["previous_sha"]]
        ):
            raise ValueError("Upgrade build is not its exact signed fast-forward candidate")
        original = self.github("GET", prefix + "commits/" + target["source_sha"])
        trees = []
        for commit in (original, candidate):
            tree = self.github(
                "GET", prefix + "git/trees/" + commit["commit"]["tree"]["sha"] + "?recursive=1"
            )
            if tree.get("truncated") is not False:
                raise ValueError("Complete release trees are required")
            entries = tree.get("tree", [])
            if len({v["path"] for v in entries}) != len(entries):
                raise ValueError("Release tree paths are ambiguous")
            trees.append({v["path"]: (v["mode"], v["type"], v["sha"]) for v in entries})
        marker = trees[1].pop(".single-tenant-release.json", None)
        if not marker or marker[:2] != ("100644", "blob") or trees[0] != trees[1]:
            raise ValueError("Customer build differs from the approved production source")
        file = self.github(
            "GET", prefix + "contents/.single-tenant-release.json?ref=" + target["build_sha"]
        )
        if (
            file.get("type") != "file"
            or file.get("size", MAX_MARKER_BYTES + 1) > MAX_MARKER_BYTES
            or file.get("encoding") != "base64"
        ):
            raise ValueError("Release marker exceeded its exact scope")
        if json.loads(base64.b64decode(file["content"], validate=False)) != {
            "order_id": order,
            "tag": target["tag"],
            "source_sha": target["source_sha"],
        }:
            raise ValueError("Release marker belongs to another tenant or version")
        path = prefix + "git/refs/heads/single-tenant/" + order
        read_path = prefix + "git/ref/heads/single-tenant/" + order
        existing = self.github("GET", read_path)
        current = existing.get("object", {}).get("sha")
        if existing.get("ref") != "refs/heads/single-tenant/" + order or current not in {
            target["previous_sha"],
            target["build_sha"],
        }:
            raise ValueError("Customer build changed outside its owned release request")
        if current != target["build_sha"]:
            # force=false preserves a competing branch update; no history is overwritten.
            self.github("PATCH", path, {"sha": target["build_sha"], "force": False})
        if self.github("GET", read_path).get("object", {}).get("sha") != target["build_sha"]:
            raise ValueError("The exact release candidate was not published")

    def run(self, config: dict[str, Any]) -> dict[str, Any]:
        order, target = config["order_id"], config["release"]
        identity(order)
        validate_target(target)
        deployed = resolve(self.origin, lambda path: self.github("GET", "/" + path))
        if (deployed.tag, deployed.source_sha) != (target["tag"], target["source_sha"]):
            raise ValueError(
                "Customer upgrades must follow the release actually deployed to production"
            )
        if self.archive is None:
            raise ValueError("Verified release image archive is required")
        digest = release_image(
            deployed.tag,
            deployed.source_sha,
            lambda path: self.github("GET", "/" + path),
            self.archive,
        )
        self.stage = "upgrade-authority"
        self.authority(config, "provision")
        workspace = self.owner.workspace(order)
        if workspace is None:
            raise ValueError("The existing customer workspace is missing")
        ids = self.owner.owned(order, state_resources(self.hcp.state(workspace["id"])))
        app_id = ids[APP_ADDRESS]
        app = self.owner.do("/apps/" + app_id)["app"]
        components = [*app["spec"].get("services", []), *app["spec"].get("jobs", [])]
        if len(components) != BUILD_COMPONENT_COUNT or {c.get("name") for c in components} != {
            "app",
            "app-onion",
            "initialize-instance",
        }:
            raise ValueError("Owned app build components have changed")
        if any(
            not (
                (
                    c.get("git", {}).get("repo_clone_url") == APP_REPOSITORY
                    and c.get("git", {}).get("branch") == "single-tenant/" + order
                    and not c.get("image")
                )
                or (
                    all(c.get("image", {}).get(k) == v for k, v in IMAGE.items())
                    and re.fullmatch(r"sha256:[a-f0-9]{64}", c.get("image", {}).get("digest", ""))
                    and not c.get("image", {}).get("tag")
                    and not any(c.get(k) for k in ("git", "github", "gitlab"))
                )
            )
            for c in components
        ):
            raise ValueError("An upgrade cannot change customer build ownership")
        pending_before = app.get("pending_deployment") or {}
        if pending_before and not sources(pending_before, digest):
            raise ValueError("Another customer deployment is still in progress")
        self.stage = "upgrade-build"
        self.build(config)
        self.stage = "upgrade-authority"
        self.authority(config, "provision")
        if self.owner.owned(order, state_resources(self.hcp.state(workspace["id"]))) != ids:
            raise ValueError("Customer resource ownership changed before deployment")
        fresh = self.owner.do("/apps/" + app_id)["app"]
        if fresh.get("spec") != app["spec"]:
            raise ValueError("Customer configuration changed before deployment")
        pending_now = fresh.get("pending_deployment") or {}
        if pending_now and not sources(pending_now, digest):
            raise ValueError("Another customer deployment is still in progress")
        app = fresh
        self.stage = "upgrade-deployment"
        active = app.get("active_deployment", {})
        pending = app.get("pending_deployment") or {}
        deployment = (
            active if active.get("phase") == "ACTIVE" and sources(active, digest) else pending
        )
        if not deployment:
            spec = deepcopy(app["spec"])
            for component in [*spec["services"], *spec["jobs"]]:
                for key in ("git", "github", "gitlab", "dockerfile_path"):
                    component.pop(key, None)
                component["image"] = image_source(digest)
            updated = self.owner.request(
                "PUT", "https://api.digitalocean.com/v2/apps/" + app_id, {"spec": spec}
            )["app"]
            if updated.get("spec") != spec:
                raise ValueError("Image update changed customer configuration")
            deployment = updated.get("pending_deployment") or updated.get("active_deployment") or {}
        identifier = deployment.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", identifier):
            raise ValueError("Invalid exact customer deployment identity")
        for _ in range(MAX_DEPLOYMENT_POLLS):
            current = self.owner.do("/apps/" + app_id + "/deployments/" + identifier)["deployment"]
            if current.get("id") != identifier:
                raise ValueError("Deployment response changed its identity")
            if current.get("phase") == "ACTIVE":
                if not sources(current, digest):
                    raise ValueError("Active deployment does not contain the exact approved build")
                return {"state": "upgraded", "deployment_id": identifier}
            if current.get("phase") in {"ERROR", "CANCELED", "SUPERSEDED"}:
                raise ValueError("Owned release deployment failed")
            self.progress({"state": "upgrading", "deployment_id": identifier})
            time.sleep(5)
        raise ValueError("Owned release deployment exceeded its duration")

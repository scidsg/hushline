"""Promote a human-published, verified release to the production Terraform workspace."""

from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import subprocess
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_IMAGE_HELPERS = runpy.run_path(str(Path(__file__).with_name("single_tenant_live_image.py")))
MAX_ARCHIVE_BYTES = int(_IMAGE_HELPERS["MAX_ARCHIVE_BYTES"])
release_image = _IMAGE_HELPERS["release_image"]

APP = "scidsg/hushline"
INFRA = "scidsg/hushline-infra"
WORKSPACE = "ws-23WhhjT9pywZsezs"
VERSION_FILE = "hushline-env/hushline.tf"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
TAG_LINE = re.compile(r'(?m)^(\s*tag\s*=\s*")v[0-9]+\.[0-9]+\.[0-9]+(")$')
DIGEST_LINE = re.compile(r'(?m)^(\s*app_image_digest\s*=\s*)(null|"sha256:[a-f0-9]{64}")$')
MAX_RESPONSE = 4 * 1024 * 1024
BUILD_ATTEMPTS = 60
SINGLE_PARENT_FIELDS = 2


@dataclass(frozen=True)
class Promotion:
    tag: str
    head: str
    digest: str
    source_sha: str


class DeploymentError(RuntimeError):
    """A release cannot safely be promoted."""


class APIError(DeploymentError):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"Release API returned HTTP {status}")


class SupersededRelease(DeploymentError):
    """A newer publication already owns production promotion."""


class UnpublishedRelease(DeploymentError):
    """The image build finished before its release was published."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class API:
    def __init__(self, origin: str, token: str) -> None:
        if not token:
            raise DeploymentError("A release automation credential is missing")
        if origin not in {"https://api.github.com", "https://app.terraform.io/api/v2"}:
            raise DeploymentError("Unexpected release API origin")
        self.origin = origin
        self.token = token

    def request(
        self, path: str, payload: dict[str, Any] | None = None, *, method: str | None = None
    ) -> dict[str, Any]:
        request = Request(  # noqa: S310 - Origins are fixed HTTPS APIs; redirects are denied.
            self.origin + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method or ("PATCH" if payload is not None else "GET"),
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/vnd.api+json",
                "Accept": "application/json",
                "User-Agent": "HushLine-release-deployment",
            },
        )
        try:
            with build_opener(NoRedirect).open(request, timeout=30) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except HTTPError as error:
            raise APIError(error.code) from None
        except URLError:
            raise DeploymentError("Release API is unavailable") from None
        if len(raw) > MAX_RESPONSE:
            raise DeploymentError("Release API response exceeded its bound")
        document = json.loads(raw) if raw else {}
        if not isinstance(document, dict):
            raise DeploymentError("Invalid release API response")
        return document

    def artifact(self, identifier: int) -> bytes:
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1:
            raise DeploymentError("Invalid release artifact identity")
        result = subprocess.run(
            [  # noqa: S603 - Fixed gh executable and validated numeric artifact identifier.
                shutil.which("gh") or "/usr/bin/gh",
                "api",
                f"repos/{APP}/actions/artifacts/{identifier}/zip",
            ],
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GH_TOKEN": self.token,
                "GH_HOST": "github.com",
                "HOME": str(Path.home()),
            },
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode or len(result.stdout) > MAX_ARCHIVE_BYTES:
            raise DeploymentError("Release image artifact is unavailable")
        return bytes(result.stdout)

    def plan_json(self, identifier: str) -> dict[str, Any]:
        if not re.fullmatch(r"plan-[A-Za-z0-9]+", identifier):
            raise DeploymentError("Invalid release plan identity")
        request = Request(  # noqa: S310 - Fixed authenticated API; no redirects with its token.
            "https://app.terraform.io/api/v2/plans/" + identifier + "/json-output",
            headers={"Authorization": "Bearer " + self.token},
        )
        try:
            with build_opener(NoRedirect).open(request, timeout=30):
                raise DeploymentError("Plan download did not return its authenticated URL")
        except HTTPError as error:
            if error.code != HTTPStatus.TEMPORARY_REDIRECT:
                raise APIError(error.code) from None
            url = error.headers.get("Location", "")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "archivist.terraform.io"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
        ):
            raise DeploymentError("Unexpected Terraform plan download origin")
        # The temporary URL authenticates itself. Never forward the Terraform bearer token.
        try:
            with build_opener(NoRedirect).open(url, timeout=30) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except URLError:
            raise DeploymentError("Production plan download is unavailable") from None
        if len(raw) > MAX_RESPONSE:
            raise DeploymentError("Production plan exceeded its bound")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise DeploymentError("Invalid production plan")
        return value


def version(tag: str) -> tuple[int, ...]:
    match = TAG.fullmatch(tag)
    if not match:
        raise DeploymentError("Only stable versioned releases can deploy")
    return tuple(int(value) for value in match.groups())


def updated_source(source: str, tag: str, digest: str | None = None) -> str:
    version(tag)
    matches = list(TAG_LINE.finditer(source))
    if len(matches) != 1:
        raise DeploymentError("Expected exactly one app image version assignment")
    source = TAG_LINE.sub(lambda match: match[1] + tag + match[2], source)
    if digest is not None:
        if (
            not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            or len(DIGEST_LINE.findall(source)) != 1
        ):
            raise DeploymentError("Production requires reviewed immutable-image support")
        source = DIGEST_LINE.sub(lambda match: match[1] + '"' + digest + '"', source)
    return source


def verify_release(github: API, tag: str) -> str:
    version(tag)
    try:
        release = github.request(f"/repos/{APP}/releases/tags/{tag}")
    except APIError as error:
        if error.status == HTTPStatus.NOT_FOUND:
            raise UnpublishedRelease("Release is not yet published") from None
        raise
    author = release.get("author", {})
    if (
        release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or author.get("type") != "User"
        or not re.fullmatch(r"[A-Za-z0-9-]+", author.get("login", ""))
    ):
        raise DeploymentError("Deployment requires a human-published stable release")
    permission = github.request(f"/repos/{APP}/collaborators/{author['login']}/permission")
    if permission.get("permission") != "admin":
        raise DeploymentError("Only an administrator can authorize a release")
    latest = github.request(f"/repos/{APP}/releases/latest")
    if latest.get("id") != release.get("id"):
        raise SupersededRelease("A newer published release supersedes this event")
    commit = github.request(f"/repos/{APP}/commits/{tag}")
    sha = commit.get("sha", "")
    if (
        not re.fullmatch(r"[a-f0-9]{40}", sha)
        or commit.get("commit", {}).get("verification", {}).get("verified") is not True
    ):
        raise DeploymentError("Release source must have a verified signature")
    comparison = github.request(f"/repos/{APP}/compare/{sha}...main")
    if comparison.get("status") not in {"ahead", "identical"}:
        raise DeploymentError("Release source is outside main history")
    return sha


def wait_for_build(github: API, tag: str, sha: str) -> None:
    for _ in range(BUILD_ATTEMPTS):
        result = github.request(
            f"/repos/{APP}/actions/workflows/build-release.yml/runs"
            f"?event=push&head_sha={sha}&per_page=100"
        )
        runs = [
            run
            for run in result.get("workflow_runs", [])
            if run.get("head_sha") == sha
            and run.get("head_branch") == tag
            and run.get("event") == "push"
            and run.get("head_repository", {}).get("full_name") == APP
        ]
        if runs:
            run = max(
                runs, key=lambda item: (item.get("run_number", 0), item.get("run_attempt", 0))
            )
            if run.get("status") == "completed":
                if run.get("conclusion") != "success":
                    raise DeploymentError("The exact release image build failed")
                return
        time.sleep(30)
    raise DeploymentError("Timed out waiting for the exact release image build")


def workspace(terraform: API) -> dict[str, Any]:
    data = terraform.request(f"/workspaces/{WORKSPACE}")["data"]
    attrs = data["attributes"]
    if (
        data["id"] != WORKSPACE
        or attrs.get("name") != "prod"
        or attrs.get("working-directory") != "hushline-env"
        or data["relationships"]["organization"]["data"]["id"] != "science-and-design"
        or attrs.get("vcs-repo", {}).get("identifier") != INFRA
    ):
        raise DeploymentError("Production workspace ownership or binding changed")
    return attrs


def git(root: Path, *args: str) -> str:
    command = [shutil.which("git") or "/usr/bin/git", "-C", str(root), *args]
    result = subprocess.run(
        command,  # noqa: S603 - Fixed Git argv; release tags are validated before use.
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise DeploymentError("Release infrastructure Git operation failed")
    return result.stdout.strip()


def prepare_branch(root: Path, tag: str, digest: str | None = None) -> None:
    """Create a signed version-only branch; never overwrite an existing branch."""
    version(tag)
    git(root, "fetch", "origin", "main")
    existing = git(root, "ls-remote", "--heads", "origin", "refs/heads/" + tag)
    if existing:
        git(root, "fetch", "origin", "refs/heads/" + tag)
        git(root, "checkout", "--detach", "FETCH_HEAD")
        head = git(root, "rev-parse", "HEAD")
        ancestry_command = [
            shutil.which("git") or "/usr/bin/git",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            head,
            "origin/main",
        ]
        reviewed = (
            subprocess.run(
                ancestry_command,  # noqa: S603
                check=False,
            ).returncode
            == 0
        )
        if not reviewed:
            parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD").split()
            if len(parents) != SINGLE_PARENT_FIELDS:
                raise DeploymentError("Existing release branch has unexpected history")
            git(root, "merge-base", "--is-ancestor", parents[1], "origin/main")
            if git(root, "diff", "--name-only", "HEAD^", "HEAD") != VERSION_FILE:
                raise DeploymentError("Existing release branch changes other infrastructure")
            previous = git(root, "show", "HEAD^:" + VERSION_FILE)
            current = git(root, "show", "HEAD:" + VERSION_FILE)
            if current != updated_source(previous, tag, digest):
                raise DeploymentError("Existing release branch is not a version-only change")
    else:
        git(root, "checkout", "-b", tag, "origin/main")
        path = root / VERSION_FILE
        original = path.read_text()
        updated = updated_source(original, tag, digest)
        if updated != original:
            path.write_text(updated)
            git(root, "add", VERSION_FILE)
            git(root, "commit", "-S", "-m", "Deploy Hush Line " + tag)
        git(root, "push", "origin", "HEAD:refs/heads/" + tag)
    current = git(root, "show", "HEAD:" + VERSION_FILE)
    if current != updated_source(current, tag, digest):
        raise DeploymentError("Release branch does not use the published image version")


def ingress(terraform: API, run: dict[str, Any]) -> dict[str, Any]:
    identifier = run["relationships"]["configuration-version"]["data"]["id"]
    if not re.fullmatch(r"cv-[A-Za-z0-9]+", identifier):
        raise DeploymentError("Invalid Terraform configuration identity")
    return terraform.request(f"/configuration-versions/{identifier}/ingress-attributes")["data"][
        "attributes"
    ]


def applied_revision(terraform: API) -> str:
    workspace_data = terraform.request(f"/workspaces/{WORKSPACE}")["data"]
    current = workspace_data["relationships"].get("current-run", {}).get("data")
    if current:
        current_id = current["id"]
        if not re.fullmatch(r"run-[A-Za-z0-9]+", current_id):
            raise DeploymentError("Invalid current production run identity")
        completed = terraform.request(f"/runs/{current_id}")["data"]
        attrs = completed["attributes"]
        if (
            attrs.get("status") == "planned_and_finished"
            and attrs.get("has-changes") is False
            and attrs.get("plan-only") is False
        ):
            # An accepted no-change infra preparation does not create a new state version.
            info = ingress(terraform, completed)
            sha = info.get("commit-sha", "")
            if info.get("identifier") != INFRA or not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise DeploymentError("Production no-change baseline source is unavailable")
            return str(sha)
    state = terraform.request(f"/workspaces/{WORKSPACE}/current-state-version")["data"]
    identifier = state["relationships"]["run"]["data"]["id"]
    if not re.fullmatch(r"run-[A-Za-z0-9]+", identifier):
        raise DeploymentError("Production applied run is unavailable")
    run = terraform.request(f"/runs/{identifier}")["data"]
    if run["attributes"]["status"] != "applied":
        raise DeploymentError("Production baseline is not an applied run")
    attrs = ingress(terraform, run)
    sha = attrs.get("commit-sha", "")
    if attrs.get("identifier") != INFRA or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise DeploymentError("Production applied source is unavailable")
    return str(sha)


def verify_production_delta(root: Path, baseline: str, tag: str, digest: str) -> None:
    """Do not smuggle pending infrastructure changes into a routine app release."""
    changed = git(root, "diff", "--name-only", baseline, "HEAD").splitlines()
    for path in changed:
        production_input = path.startswith(("hushline-env/", "modules/", "scripts/")) or path in {
            "sentinel.hcl",
            ".terraformignore",
        }
        if path.endswith(".md"):
            continue
        if not production_input or "/tests/" in path:
            continue
        if path != VERSION_FILE:
            raise DeploymentError("Pending production infrastructure must deploy separately")
        previous = git(root, "show", baseline + ":" + VERSION_FILE)
        current = git(root, "show", "HEAD:" + VERSION_FILE)
        if current != updated_source(previous, tag, digest):
            raise DeploymentError("Release includes unrelated production configuration")


def verify_plan(value: dict[str, Any], digest: str) -> None:
    changes = [
        entry
        for entry in value.get("resource_changes", [])
        if entry["change"]["actions"] != ["no-op"]
    ]
    if (
        len(changes) != 1
        or changes[0].get("address") != "module.app.digitalocean_app.app"
        or changes[0]["change"]["actions"] != ["update"]
    ):
        raise DeploymentError("Production plan changes more than the existing app image")
    change = changes[0]["change"]
    before, after = change.get("before"), change.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise DeploymentError("Production app plan is incomplete")
    before = json.loads(json.dumps(before))
    after = json.loads(json.dumps(after))
    for component in ("service", "worker", "job"):
        previous = before.get("spec", [{}])[0].get(component, [])
        proposed = after.get("spec", [{}])[0].get(component, [])
        if len(previous) != len(proposed):
            raise DeploymentError("Release changes app components")
        for old, new in zip(previous, proposed, strict=True):
            old_images, new_images = old.get("image", []), new.get("image", [])
            if len(old_images) != len(new_images):
                raise DeploymentError("Release changes image source topology")
            for old_image, new_image in zip(old_images, new_images, strict=True):
                if (
                    old_image.get("repository") == "hushline/hushline"
                    and old_image.get("registry") == "scidsg"
                    and old_image.get("registry_type") == "GHCR"
                ):
                    if new_image.get("digest") != digest or new_image.get("tag") not in {None, ""}:
                        raise DeploymentError("Production image is not the verified digest")
                    old_image["digest"] = new_image.get("digest")
                    old_image["tag"] = new_image.get("tag")
    # Only known provider-computed output fields may be unknown. Never mask spec changes.
    computed = {
        "id",
        "urn",
        "created_at",
        "updated_at",
        "live_url",
        "live_domain",
        "default_ingress",
        "active_deployment_id",
    }
    for key, flag in change.get("after_unknown", {}).items():
        if flag is True and key in computed:
            before.pop(key, None)
            after.pop(key, None)
        elif flag not in ({}, [], False):
            raise DeploymentError("Production configuration is unknown in the release plan")
    if before != after:
        raise DeploymentError("Production plan changes configuration beyond image identity")


def apply_release_run(terraform: API, github: API, promotion: Promotion) -> None:
    """Confirm only the exact VCS release run, after Terraform's policy checks."""
    tag, head, digest, source_sha = (
        promotion.tag,
        promotion.head,
        promotion.digest,
        promotion.source_sha,
    )
    for _ in range(BUILD_ATTEMPTS):
        attrs = workspace(terraform)
        if attrs["vcs-repo"]["branch"] != tag or attrs.get("auto-apply") is not False:
            raise DeploymentError("Production binding or approval controls changed")
        if verify_release(github, tag) != source_sha:
            raise DeploymentError("Published release source changed during deployment")
        data = terraform.request(f"/workspaces/{WORKSPACE}")["data"]
        current = data["relationships"]["current-run"]["data"]
        runs = []
        if current:
            identifier = current["id"]
            if not re.fullmatch(r"run-[A-Za-z0-9]+", identifier):
                raise DeploymentError("Invalid current production run identity")
            runs.append(terraform.request(f"/runs/{identifier}")["data"])
        candidates = []
        for run in runs:
            if run["attributes"].get("source") != "tfe-configuration-version":
                continue
            try:
                info = ingress(terraform, run)
            except APIError as error:
                if (
                    error.status == HTTPStatus.NOT_FOUND
                    and run["attributes"]["status"] == "fetching"
                ):
                    continue
                raise
            if (
                info.get("commit-sha") == head
                and info.get("branch") == tag
                and info.get("identifier") == INFRA
            ):
                candidates.append(run)
        if len(candidates) > 1:
            raise DeploymentError("Ambiguous release runs require operator recovery")
        if candidates:
            run = candidates[0]
            identifier = run["id"]
            if not re.fullmatch(r"run-[A-Za-z0-9]+", identifier):
                raise DeploymentError("Invalid release run identity")
            attributes = run["attributes"]
            if (
                run["relationships"]["workspace"]["data"]["id"] != WORKSPACE
                or attributes.get("is-destroy") is not False
                or attributes.get("auto-apply") is not False
                or attributes.get("plan-only") is not False
                or attributes.get("refresh-only") is not False
                or any(
                    attributes.get(key)
                    for key in ("target-addrs", "replace-addrs", "variables", "invoke-action-addrs")
                )
            ):
                raise DeploymentError("Unexpected production run operation")
            status = attributes["status"]
            if status in {"applied", "planned_and_finished"}:
                return
            if status in {
                "errored",
                "canceled",
                "force_canceled",
                "discarded",
                "policy_override",
                "policy_soft_failed",
            }:
                raise DeploymentError("Release run failed or requires policy recovery")
            if attributes.get("actions", {}).get("is-confirmable") is True:
                plan_id = run["relationships"]["plan"]["data"]["id"]
                if not re.fullmatch(r"plan-[A-Za-z0-9]+", plan_id):
                    raise DeploymentError("Invalid release plan identity")
                plan = terraform.request(f"/plans/{plan_id}")["data"]["attributes"]
                if (
                    plan.get("resource-additions") != 0
                    or plan.get("resource-destructions") != 0
                    or plan.get("resource-changes") != 1
                ):
                    raise DeploymentError("Release plan is not one in-place app update")
                verify_plan(terraform.plan_json(plan_id), digest)
                if verify_release(github, tag) != source_sha:
                    raise DeploymentError("Published release source changed before confirmation")
                final = workspace(terraform)
                if final["vcs-repo"]["branch"] != tag or final.get("auto-apply") is not False:
                    raise DeploymentError("Production changed before release confirmation")
                # The API enforces policy completion; never override policies or force a run.
                terraform.request(
                    f"/runs/{identifier}/actions/apply",
                    {"comment": "Verified human-published release " + tag},
                    method="POST",
                )
                print("Automatically confirmed verified release run " + identifier)
                return
        time.sleep(30)
    raise DeploymentError("Timed out waiting for the verified production release plan")


def deploy(github: API, terraform: API, root: Path, tag: str) -> None:
    sha = verify_release(github, tag)
    wait_for_build(github, tag, sha)
    attrs = workspace(terraform)
    current = attrs["vcs-repo"]["branch"]
    if version(tag) < version(current):
        raise DeploymentError("An older release cannot replace production")
    try:
        digest = release_image(tag, sha, lambda path: github.request("/" + path), github.artifact)
    except ValueError as error:
        raise DeploymentError(str(error)) from None
    baseline = applied_revision(terraform)
    prepare_branch(root, tag, digest)
    verify_production_delta(root, baseline, tag, digest)
    validation_command = [shutil.which("bash") or "/bin/bash", "scripts/validate.sh"]
    validation = subprocess.run(validation_command, cwd=root, check=False)  # noqa: S603
    if validation.returncode:
        raise DeploymentError("Release infrastructure validation failed")
    head = git(root, "rev-parse", "HEAD")
    if baseline == head:
        print("Production already applied " + tag)
        return
    commit = github.request(f"/repos/{INFRA}/commits/{head}")
    if commit.get("commit", {}).get("verification", {}).get("verified") is not True:
        raise DeploymentError("Infra release commit signature is not remotely verified")
    # Recheck after waiting/building to prevent stale releases from promoting.
    if verify_release(github, tag) != sha:
        raise DeploymentError("Published release source changed during preparation")
    if workspace(terraform)["vcs-repo"]["branch"] != current:
        raise DeploymentError("Production changed during release preparation")
    terraform.request(
        f"/workspaces/{WORKSPACE}",
        {
            "data": {
                "type": "workspaces",
                "id": WORKSPACE,
                "attributes": {
                    "vcs-repo": {"branch": tag},
                    "auto-apply": False,
                },
            }
        },
    )
    after = workspace(terraform)
    if after["vcs-repo"]["branch"] != tag or after["auto-apply"] is not False:
        raise DeploymentError("Production release binding was not updated")
    apply_release_run(terraform, github, Promotion(tag, head, digest, sha))


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if os.environ["GITHUB_EVENT_NAME"] == "release":
        tag = event["release"]["tag_name"]
    else:
        run = event["workflow_run"]
        if (
            run.get("conclusion") != "success"
            or run.get("event") != "push"
            or run.get("head_repository", {}).get("full_name") != APP
        ):
            return
        tag = run["head_branch"]
    try:
        deploy(
            API("https://api.github.com", os.environ["RELEASE_GITHUB_TOKEN"]),
            API("https://app.terraform.io/api/v2", os.environ["RELEASE_TF_TOKEN"]),
            Path("release-infra"),
            tag,
        )
    except SupersededRelease as error:
        print(str(error))
    except UnpublishedRelease as error:
        if os.environ["GITHUB_EVENT_NAME"] == "workflow_run":
            print("Release is not yet published; publication will trigger deployment")
            return
        raise SystemExit(str(error)) from None
    except DeploymentError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()

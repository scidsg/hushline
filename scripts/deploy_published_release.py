"""Promote a human-published, verified release to the production Terraform workspace."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

APP = "scidsg/hushline"
INFRA = "scidsg/hushline-infra"
WORKSPACE = "ws-23WhhjT9pywZsezs"
VERSION_FILE = "hushline-env/hushline.tf"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
TAG_LINE = re.compile(r'(?m)^(\s*tag\s*=\s*")v[0-9]+\.[0-9]+\.[0-9]+(")$')
MAX_RESPONSE = 4 * 1024 * 1024
BUILD_ATTEMPTS = 60
SINGLE_PARENT_FIELDS = 2


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

    def request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request = Request(  # noqa: S310 - Origins are fixed HTTPS APIs; redirects are denied.
            self.origin + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method="PATCH" if payload is not None else "GET",
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
        if len(raw) > MAX_RESPONSE:
            raise DeploymentError("Release API response exceeded its bound")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise DeploymentError("Invalid release API response")
        return document


def version(tag: str) -> tuple[int, ...]:
    match = TAG.fullmatch(tag)
    if not match:
        raise DeploymentError("Only stable versioned releases can deploy")
    return tuple(int(value) for value in match.groups())


def updated_source(source: str, tag: str) -> str:
    version(tag)
    matches = list(TAG_LINE.finditer(source))
    if len(matches) != 1:
        raise DeploymentError("Expected exactly one app image version assignment")
    return TAG_LINE.sub(lambda match: match[1] + tag + match[2], source)


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


def prepare_branch(root: Path, tag: str) -> None:
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
            if current != updated_source(previous, tag):
                raise DeploymentError("Existing release branch is not a version-only change")
    else:
        git(root, "checkout", "-b", tag, "origin/main")
        path = root / VERSION_FILE
        original = path.read_text()
        updated = updated_source(original, tag)
        if updated != original:
            path.write_text(updated)
            git(root, "add", VERSION_FILE)
            git(root, "commit", "-S", "-m", "Deploy Hush Line " + tag)
        git(root, "push", "origin", "HEAD:refs/heads/" + tag)
    current = git(root, "show", "HEAD:" + VERSION_FILE)
    if current != updated_source(current, tag):
        raise DeploymentError("Release branch does not use the published image version")


def deploy(github: API, terraform: API, root: Path, tag: str) -> None:
    sha = verify_release(github, tag)
    wait_for_build(github, tag, sha)
    attrs = workspace(terraform)
    current = attrs["vcs-repo"]["branch"]
    if version(tag) < version(current):
        raise DeploymentError("An older release cannot replace production")
    if current == tag:
        print("Production already targets " + tag)
        return
    prepare_branch(root, tag)
    validation_command = [shutil.which("bash") or "/bin/bash", "scripts/validate.sh"]
    validation = subprocess.run(validation_command, cwd=root, check=False)  # noqa: S603
    if validation.returncode:
        raise DeploymentError("Release infrastructure validation failed")
    head = git(root, "rev-parse", "HEAD")
    commit = github.request(f"/repos/{INFRA}/commits/{head}")
    if commit.get("commit", {}).get("verification", {}).get("verified") is not True:
        raise DeploymentError("Infra release commit signature is not remotely verified")
    # Recheck after waiting/building to prevent stale releases from promoting.
    verify_release(github, tag)
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
                    "auto-apply": True,
                },
            }
        },
    )
    after = workspace(terraform)
    if after["vcs-repo"]["branch"] != tag or after["auto-apply"] is not True:
        raise DeploymentError("Production release binding was not updated")
    print("Production now follows " + tag + " with automatic apply enabled")


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

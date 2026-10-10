from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import deploy_published_release as release

SHA = "a" * 40
INFRA_SHA = "b" * 40


def documents() -> dict[str, dict[str, Any]]:
    published = {
        "id": 1,
        "tag_name": "v0.7.29",
        "draft": False,
        "prerelease": False,
        "author": {"login": "maintainer", "type": "User"},
    }
    return {
        f"/repos/{release.APP}/releases/tags/v0.7.29": published,
        f"/repos/{release.APP}/releases/latest": deepcopy(published),
        f"/repos/{release.APP}/collaborators/maintainer/permission": {"permission": "admin"},
        f"/repos/{release.APP}/commits/v0.7.29": {
            "sha": SHA,
            "commit": {"verification": {"verified": True}},
        },
        f"/repos/{release.APP}/compare/{SHA}...main": {"status": "ahead"},
        f"/repos/{release.INFRA}/commits/{INFRA_SHA}": {
            "commit": {"verification": {"verified": True}},
        },
        f"/repos/{release.APP}/actions/workflows/build-release.yml/runs"
        f"?event=push&head_sha={SHA}&per_page=100": {
            "workflow_runs": [
                {
                    "head_sha": SHA,
                    "head_branch": "v0.7.29",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_repository": {"full_name": release.APP},
                }
            ]
        },
    }


class FakeAPI(release.API):
    def __init__(self, docs: dict[str, dict[str, Any]]) -> None:
        self.docs = docs
        self.writes: list[dict[str, Any]] = []

    def request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload is not None:
            self.writes.append(payload)
            attrs = self.docs[path]["data"]["attributes"]
            for key, value in payload["data"]["attributes"].items():
                if isinstance(value, dict):
                    attrs[key].update(value)
                else:
                    attrs[key] = value
        return deepcopy(self.docs[path])


def terraform_api() -> FakeAPI:
    return FakeAPI(
        {
            f"/workspaces/{release.WORKSPACE}": {
                "data": {
                    "id": release.WORKSPACE,
                    "attributes": {
                        "name": "prod",
                        "working-directory": "hushline-env",
                        "vcs-repo": {"identifier": release.INFRA, "branch": "v0.7.28"},
                        "auto-apply": False,
                    },
                    "relationships": {"organization": {"data": {"id": "science-and-design"}}},
                }
            }
        }
    )


@pytest.mark.parametrize("tag", ["v0.7.29-rc1", "../main", "v01.2.3", "main", "v1.2"])
def test_invalid_release_never_calls_provider(tag: str) -> None:
    with pytest.raises(release.DeploymentError):
        release.verify_release(FakeAPI({}), tag)


def test_version_update_preserves_all_other_configuration() -> None:
    original = 'module "app" {\n  tag = "v0.7.28"\n  include_dev_db = false\n}\n'
    assert release.updated_source(original, "v0.7.29") == original.replace("v0.7.28", "v0.7.29")


@pytest.mark.parametrize("source", ["", 'tag = "v0.7.28"\ntag = "v0.7.28"'])
def test_ambiguous_image_version_fails(source: str) -> None:
    with pytest.raises(release.DeploymentError):
        release.updated_source(source, "v0.7.29")


@pytest.mark.parametrize(("field", "value"), [("draft", True), ("prerelease", True)])
def test_unpublished_release_fails(field: str, value: bool) -> None:
    docs = documents()
    docs[f"/repos/{release.APP}/releases/tags/v0.7.29"][field] = value
    with pytest.raises(release.DeploymentError, match="human-published"):
        release.verify_release(FakeAPI(docs), "v0.7.29")


def test_bot_release_is_not_human_approval() -> None:
    docs = documents()
    docs[f"/repos/{release.APP}/releases/tags/v0.7.29"]["author"]["type"] = "Bot"
    with pytest.raises(release.DeploymentError, match="human-published"):
        release.verify_release(FakeAPI(docs), "v0.7.29")


@pytest.mark.parametrize("case", ["nonadmin", "superseded", "unsigned", "outside-main"])
def test_invalid_authorization_stops_release(case: str) -> None:
    docs = documents()
    if case == "nonadmin":
        docs[f"/repos/{release.APP}/collaborators/maintainer/permission"]["permission"] = "write"
    elif case == "superseded":
        docs[f"/repos/{release.APP}/releases/latest"]["id"] = 2
    elif case == "unsigned":
        docs[f"/repos/{release.APP}/commits/v0.7.29"]["commit"]["verification"]["verified"] = False
    else:
        docs[f"/repos/{release.APP}/compare/{SHA}...main"]["status"] = "diverged"
    with pytest.raises(release.DeploymentError):
        release.verify_release(FakeAPI(docs), "v0.7.29")


def test_failed_image_build_stops_deployment() -> None:
    docs = documents()
    build = next(value for value in docs.values() if "workflow_runs" in value)
    build["workflow_runs"][0]["conclusion"] = "failure"
    with pytest.raises(release.DeploymentError, match="build failed"):
        release.wait_for_build(FakeAPI(docs), "v0.7.29", SHA)


def test_fork_image_build_cannot_authorize_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = documents()
    build = next(value for value in docs.values() if "workflow_runs" in value)
    build["workflow_runs"][0]["head_repository"]["full_name"] = "attacker/hushline"
    monkeypatch.setattr(release.time, "sleep", lambda _: None)
    with pytest.raises(release.DeploymentError, match="Timed out"):
        release.wait_for_build(FakeAPI(docs), "v0.7.29", SHA)


@pytest.mark.parametrize(
    ("field", "value"), [("name", "staging"), ("working-directory", "hushline-other")]
)
def test_other_workspace_is_never_updated(field: str, value: str) -> None:
    tf = terraform_api()
    tf.docs[f"/workspaces/{release.WORKSPACE}"]["data"]["attributes"][field] = value
    with pytest.raises(release.DeploymentError, match="ownership"):
        release.workspace(tf)
    assert not tf.writes


def test_deploy_changes_only_production_branch_and_auto_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tf = terraform_api()
    monkeypatch.setattr(release, "prepare_branch", lambda *_: None)
    monkeypatch.setattr(release, "git", lambda *_: INFRA_SHA)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    release.deploy(FakeAPI(documents()), tf, Path("unused"), "v0.7.29")
    assert tf.writes == [
        {
            "data": {
                "type": "workspaces",
                "id": release.WORKSPACE,
                "attributes": {"vcs-repo": {"branch": "v0.7.29"}, "auto-apply": True},
            }
        }
    ]


def test_older_release_cannot_roll_back_production() -> None:
    tf = terraform_api()
    tf.docs[f"/workspaces/{release.WORKSPACE}"]["data"]["attributes"]["vcs-repo"]["branch"] = (
        "v0.7.30"
    )
    with pytest.raises(release.DeploymentError, match="older release"):
        release.deploy(FakeAPI(documents()), tf, Path("unused"), "v0.7.29")
    assert not tf.writes


def test_unsigned_infra_commit_cannot_switch_production(monkeypatch: pytest.MonkeyPatch) -> None:
    tf = terraform_api()
    docs = documents()
    docs[f"/repos/{release.INFRA}/commits/{INFRA_SHA}"]["commit"]["verification"]["verified"] = (
        False
    )
    monkeypatch.setattr(release, "prepare_branch", lambda *_: None)
    monkeypatch.setattr(release, "git", lambda *_: INFRA_SHA)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    with pytest.raises(release.DeploymentError, match="Infra release commit signature"):
        release.deploy(FakeAPI(docs), tf, Path("unused"), "v0.7.29")
    assert not tf.writes

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import deploy_published_release as release

SHA = "a" * 40
INFRA_SHA = "b" * 40
DIGEST = "sha256:" + "c" * 64


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
    monkeypatch.setattr(release, "release_image", lambda *_: DIGEST)
    monkeypatch.setattr(release, "applied_revision", lambda *_: SHA)
    monkeypatch.setattr(release, "verify_production_delta", lambda *_: None)
    applied: list[tuple[Any, ...]] = []
    monkeypatch.setattr(release, "apply_release_run", lambda *args: applied.append(args))
    monkeypatch.setattr(release, "git", lambda *_: INFRA_SHA)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    release.deploy(FakeAPI(documents()), tf, Path("unused"), "v0.7.29")
    assert tf.writes == [
        {
            "data": {
                "type": "workspaces",
                "id": release.WORKSPACE,
                "attributes": {"vcs-repo": {"branch": "v0.7.29"}, "auto-apply": False},
            }
        }
    ]
    assert len(applied) == 1
    assert applied[0][2] == release.Promotion("v0.7.29", INFRA_SHA, DIGEST, SHA)


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
    monkeypatch.setattr(release, "release_image", lambda *_: DIGEST)
    monkeypatch.setattr(release, "applied_revision", lambda *_: SHA)
    monkeypatch.setattr(release, "verify_production_delta", lambda *_: None)
    monkeypatch.setattr(release, "git", lambda *_: INFRA_SHA)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    with pytest.raises(release.DeploymentError, match="Infra release commit signature"):
        release.deploy(FakeAPI(docs), tf, Path("unused"), "v0.7.29")
    assert not tf.writes


def image_plan() -> dict[str, Any]:
    before: dict[str, Any] = {
        "spec": [
            {
                "service": [
                    {
                        "name": "app",
                        "image": [
                            {
                                "registry_type": "GHCR",
                                "registry": "scidsg",
                                "repository": "hushline/hushline",
                                "tag": "v0.7.28",
                                "digest": None,
                            }
                        ],
                        "env": [{"key": "SECRET_KEY", "value": "private-fixture"}],
                    }
                ]
            }
        ],
        "live_url": "https://example.org",
    }
    after = deepcopy(before)
    after["spec"][0]["service"][0]["image"][0].update({"tag": None, "digest": DIGEST})
    return {
        "resource_changes": [
            {
                "address": "module.app.digitalocean_app.app",
                "change": {
                    "actions": ["update"],
                    "before": before,
                    "after": after,
                    "after_unknown": {},
                },
            }
        ]
    }


def test_only_verified_image_plan_can_be_confirmed() -> None:
    release.verify_plan(image_plan(), DIGEST)


@pytest.mark.parametrize(
    "case", ["secret", "replacement", "other-resource", "wrong-digest", "new-component"]
)
def test_unrelated_or_unverified_plan_cannot_be_confirmed(case: str) -> None:
    plan = image_plan()
    entry = plan["resource_changes"][0]
    component = entry["change"]["after"]["spec"][0]["service"][0]
    if case == "secret":
        component["env"][0]["value"] = "changed-private-fixture"
    elif case == "replacement":
        entry["change"]["actions"] = ["delete", "create"]
    elif case == "other-resource":
        entry["address"] = "digitalocean_database_cluster.db"
    elif case == "wrong-digest":
        component["image"][0]["digest"] = "sha256:" + "d" * 64
    else:
        entry["change"]["after"]["spec"][0]["service"].append(deepcopy(component))
    with pytest.raises(release.DeploymentError):
        release.verify_plan(plan, DIGEST)


def test_pending_module_changes_block_app_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release, "git", lambda *_: "modules/hushline-app/app.tf")
    with pytest.raises(release.DeploymentError, match="deploy separately"):
        release.verify_production_delta(Path("unused"), SHA, "v0.7.29", DIGEST)


def test_pending_production_environment_changes_block_app_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = 'tag = "v0.7.28"\napp_image_digest = null\ninstance_count = 2'
    new = release.updated_source(old, "v0.7.29", DIGEST).replace("count = 2", "count = 3")

    def fake_git(_root: Path, *args: str) -> str:
        if args[0] == "diff":
            return release.VERSION_FILE
        return old if args[1].startswith(SHA) else new

    monkeypatch.setattr(release, "git", fake_git)
    with pytest.raises(release.DeploymentError, match="unrelated production"):
        release.verify_production_delta(Path("unused"), SHA, "v0.7.29", DIGEST)


def test_digest_update_requires_reviewed_support() -> None:
    with pytest.raises(release.DeploymentError, match="reviewed immutable"):
        release.updated_source('tag = "v0.7.28"', "v0.7.29", DIGEST)
    source = 'tag = "v0.7.28"\napp_image_digest = null'
    result = release.updated_source(source, "v0.7.29", DIGEST)
    assert DIGEST in result
    assert 'tag = "v0.7.29"' in result


class RunAPI(FakeAPI):
    def __init__(self) -> None:
        super().__init__(terraform_api().docs)
        data = self.docs[f"/workspaces/{release.WORKSPACE}"]["data"]
        data["attributes"]["vcs-repo"]["branch"] = "v0.7.29"
        data["relationships"]["current-run"] = {"data": {"id": "run-release"}}
        self.docs["/runs/run-release"] = {
            "data": {
                "id": "run-release",
                "attributes": {
                    "source": "tfe-configuration-version",
                    "status": "policy_checked",
                    "is-destroy": False,
                    "auto-apply": False,
                    "plan-only": False,
                    "refresh-only": False,
                    "actions": {"is-confirmable": True},
                },
                "relationships": {
                    "workspace": {"data": {"id": release.WORKSPACE}},
                    "configuration-version": {"data": {"id": "cv-release"}},
                    "plan": {"data": {"id": "plan-release"}},
                },
            }
        }
        self.docs["/configuration-versions/cv-release/ingress-attributes"] = {
            "data": {
                "attributes": {
                    "commit-sha": INFRA_SHA,
                    "branch": "v0.7.29",
                    "identifier": release.INFRA,
                }
            }
        }
        self.docs["/plans/plan-release"] = {
            "data": {
                "attributes": {
                    "resource-additions": 0,
                    "resource-destructions": 0,
                    "resource-changes": 1,
                }
            }
        }

    def request(
        self, path: str, payload: dict[str, Any] | None = None, *, method: str | None = None
    ) -> dict[str, Any]:
        if method == "POST":
            self.writes.append({"path": path, "payload": payload})
            return {}
        return super().request(path, payload)

    def plan_json(self, identifier: str) -> dict[str, Any]:
        assert identifier == "plan-release"
        return image_plan()


def test_only_exact_vcs_release_run_is_automatically_confirmed() -> None:
    tf = RunAPI()
    release.apply_release_run(
        tf, FakeAPI(documents()), release.Promotion("v0.7.29", INFRA_SHA, DIGEST, SHA)
    )
    assert [write["path"] for write in tf.writes] == ["/runs/run-release/actions/apply"]


@pytest.mark.parametrize(
    "case",
    [
        "api-source",
        "wrong-commit",
        "destroy",
        "policy-failed",
        "drift",
        "targeted",
        "variable-override",
    ],
)
def test_unrelated_run_or_drift_is_never_automatically_confirmed(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    tf = RunAPI()
    attrs = tf.docs["/runs/run-release"]["data"]["attributes"]
    if case == "api-source":
        attrs["source"] = "tfe-api"
    elif case == "wrong-commit":
        tf.docs["/configuration-versions/cv-release/ingress-attributes"]["data"]["attributes"][
            "commit-sha"
        ] = SHA
    elif case == "destroy":
        attrs["is-destroy"] = True
    elif case == "policy-failed":
        attrs["status"] = "policy_override"
    elif case == "drift":
        tf.docs["/plans/plan-release"]["data"]["attributes"]["resource-additions"] = 1
    elif case == "targeted":
        attrs["target-addrs"] = ["module.app"]
    else:
        attrs["variables"] = [{"key": "SECRET_KEY", "value": "override-fixture"}]
    monkeypatch.setattr(release, "BUILD_ATTEMPTS", 1)
    monkeypatch.setattr(release.time, "sleep", lambda _: None)
    with pytest.raises(release.DeploymentError):
        release.apply_release_run(
            tf, FakeAPI(documents()), release.Promotion("v0.7.29", INFRA_SHA, DIGEST, SHA)
        )
    assert not tf.writes


def test_unknown_config_cannot_be_hidden_as_a_computed_change() -> None:
    plan = image_plan()
    plan["resource_changes"][0]["change"]["after_unknown"] = {
        "spec": [{"service": [{"env": True}]}]
    }
    with pytest.raises(release.DeploymentError, match="unknown"):
        release.verify_plan(plan, DIGEST)


def test_no_change_infra_preparation_does_not_need_a_new_state_version() -> None:
    tf = RunAPI()
    attrs = tf.docs["/runs/run-release"]["data"]["attributes"]
    attrs.update({"status": "planned_and_finished", "has-changes": False})
    assert release.applied_revision(tf) == INFRA_SHA


def test_changed_release_source_stops_confirmation() -> None:
    tf = RunAPI()
    with pytest.raises(release.DeploymentError, match="source changed"):
        release.apply_release_run(
            tf, FakeAPI(documents()), release.Promotion("v0.7.29", INFRA_SHA, DIGEST, "d" * 40)
        )
    assert not tf.writes


def test_existing_release_branch_with_other_changes_cannot_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(_root: Path, *args: str) -> str:
        calls.append(args)
        if args[0] == "ls-remote":
            return INFRA_SHA + " refs/heads/v0.7.29"
        if args[0] == "rev-parse":
            return INFRA_SHA
        if args[0] == "rev-list":
            return INFRA_SHA + " " + SHA
        if args[0] == "diff":
            return "modules/hushline-app/app.tf"
        return ""

    monkeypatch.setattr(release, "git", fake_git)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=1))
    with pytest.raises(release.DeploymentError, match="other infrastructure"):
        release.prepare_branch(Path("unused"), "v0.7.29")
    assert not any(args[0] in {"push", "commit"} for args in calls)


def test_existing_reviewed_release_branch_is_reused_without_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(_root: Path, *args: str) -> str:
        calls.append(args)
        if args[0] == "ls-remote":
            return INFRA_SHA + " refs/heads/v0.7.29"
        if args[0] == "rev-parse":
            return INFRA_SHA
        if args[0] == "show":
            return 'tag = "v0.7.29"'
        return ""

    monkeypatch.setattr(release, "git", fake_git)
    monkeypatch.setattr(release.subprocess, "run", lambda *_, **__: SimpleNamespace(returncode=0))
    release.prepare_branch(Path("unused"), "v0.7.29")
    assert not any(args[0] in {"push", "commit"} for args in calls)


@pytest.mark.parametrize("event_name", ["workflow_run", "release"])
def test_build_before_publication_waits_only_for_build_event(
    monkeypatch: pytest.MonkeyPatch,
    event_name: str,
) -> None:
    event = {
        "release": {"tag_name": "v0.7.29"},
        "workflow_run": {
            "conclusion": "success",
            "event": "push",
            "head_branch": "v0.7.29",
            "head_repository": {"full_name": release.APP},
        },
    }
    monkeypatch.setenv("GITHUB_EVENT_PATH", "unused")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("RELEASE_GITHUB_TOKEN", "test")
    monkeypatch.setenv("RELEASE_TF_TOKEN", "test")
    monkeypatch.setattr(Path, "read_text", lambda *_: json.dumps(event))

    def not_published(*_: Any) -> None:
        raise release.UnpublishedRelease("Not published")

    monkeypatch.setattr(release, "deploy", not_published)
    if event_name == "release":
        with pytest.raises(SystemExit, match="Not published"):
            release.main()
    else:
        release.main()


def test_missing_workspace_is_not_mistaken_for_missing_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = {
        "workflow_run": {
            "conclusion": "success",
            "event": "push",
            "head_branch": "v0.7.29",
            "head_repository": {"full_name": release.APP},
        }
    }
    monkeypatch.setenv("GITHUB_EVENT_PATH", "unused")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_run")
    monkeypatch.setenv("RELEASE_GITHUB_TOKEN", "test")
    monkeypatch.setenv("RELEASE_TF_TOKEN", "test")
    monkeypatch.setattr(Path, "read_text", lambda *_: json.dumps(event))

    def workspace_missing(*_: Any) -> None:
        raise release.APIError(404)

    monkeypatch.setattr(release, "deploy", workspace_missing)
    with pytest.raises(SystemExit, match="HTTP 404"):
        release.main()

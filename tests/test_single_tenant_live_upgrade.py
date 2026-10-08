"""Existing app deployments preserve resource ownership, source, and runtime configuration."""

import base64
import json
from copy import deepcopy
from typing import Any, cast

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_ownership import APP_ADDRESS
from scripts.single_tenant_live_release import Release
from scripts.single_tenant_live_upgrade import Upgrade
from tests.test_single_tenant_live_ledger import ORDER

SOURCE, BUILD, PREVIOUS = "1" * 40, "2" * 40, "3" * 40
DEPLOYMENT = "12345678-1234-1234-1234-123456789012"
APP = "87654321-1234-1234-1234-123456789012"


def deployment(sha: str = BUILD) -> dict[str, Any]:
    return {
        "id": DEPLOYMENT,
        "phase": "ACTIVE",
        "services": [{"name": name, "source_commit_hash": sha} for name in ("app", "app-onion")],
        "jobs": [{"name": "initialize-instance", "source_commit_hash": sha}],
    }


@pytest.fixture()
def upgrade(mocker: MockFixture) -> tuple[Upgrade, Any, dict[str, Any], Any]:
    owner, hcp, github, authority = (mocker.Mock() for _ in range(4))
    owner.workspace.return_value = {"id": "ws-owned"}
    owner.owned.return_value = {APP_ADDRESS: APP}
    components = [
        {
            "name": name,
            "git": {
                "repo_clone_url": "https://github.com/scidsg/hushline.git",
                "branch": "single-tenant/" + ORDER,
            },
            "envs": [{"key": "ENCRYPTION_KEY", "value": "EV[existing]"}],
        }
        for name in ("app", "app-onion", "initialize-instance")
    ]
    app = {
        "spec": {"services": components[:2], "jobs": components[2:]},
        "active_deployment": deployment(PREVIOUS),
    }
    owner.do.side_effect = [{"app": app}, {"app": app}, {"deployment": deployment()}]
    owner.request.return_value = {"deployment": {"id": DEPLOYMENT}}
    target = {"tag": "v0.7.27", "source_sha": SOURCE, "build_sha": BUILD, "previous_sha": PREVIOUS}
    config = {"order_id": ORDER, "release": target}
    instance = Upgrade(
        ownership=owner,
        hcp=hcp,
        github=github,
        authority=authority,
        authority_origin="https://tips.hushline.app",
        progress=mocker.Mock(),
    )
    mocker.patch(
        "scripts.single_tenant_live_upgrade.resolve", return_value=Release("v0.7.27", SOURCE)
    )
    mocker.patch("scripts.single_tenant_live_upgrade.state_resources", return_value={})
    mocker.patch.object(instance, "build")
    return instance, owner, config, app


def test_redeploys_only_owned_app_without_changing_spec_or_secrets(
    upgrade: tuple[Upgrade, Any, dict, Any],
) -> None:
    instance, owner, config, app = upgrade
    unchanged = deepcopy(app)
    assert instance.run(config) == {"state": "upgraded", "deployment_id": DEPLOYMENT}
    assert app == unchanged
    owner.request.assert_called_once_with(
        "POST",
        "https://api.digitalocean.com/v2/apps/" + APP + "/deployments",
        {"force_build": True},
    )
    assert cast(Any, instance.authority).call_count == 2
    assert owner.owned.call_count == 2


def test_existing_exact_active_deployment_is_not_recreated(
    upgrade: tuple[Upgrade, Any, dict, Any],
) -> None:
    instance, owner, config, app = upgrade
    app["active_deployment"] = deployment()
    assert instance.run(config)["state"] == "upgraded"
    owner.request.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    [
        "ownership",
        "payment",
        "foreign_branch",
        "foreign_release",
        "other_pending",
        "wrong_build",
        "failed_deployment",
    ],
)
def test_upgrade_failure_does_not_mutate_another_resource(
    upgrade: tuple[Upgrade, Any, dict, Any], mocker: MockFixture, bad: str
) -> None:
    instance, owner, config, app = upgrade
    if bad == "ownership":
        owner.owned.side_effect = ValueError("Ownership changed")
    elif bad == "payment":
        cast(Any, instance.authority).side_effect = ValueError("Payment no longer active")
    elif bad == "foreign_branch":
        app["spec"]["services"][0]["git"]["branch"] = "main"
    elif bad == "foreign_release":
        mocker.patch(
            "scripts.single_tenant_live_upgrade.resolve", return_value=Release("v0.7.28", SOURCE)
        )
    elif bad == "other_pending":
        app["pending_deployment"] = deployment(PREVIOUS)
    elif bad == "wrong_build":
        owner.do.side_effect = [{"app": app}, {"app": app}, {"deployment": deployment(PREVIOUS)}]
    else:
        failed = deployment()
        failed["phase"] = "ERROR"
        owner.do.side_effect = [{"app": app}, {"app": app}, {"deployment": failed}]
    with pytest.raises(
        ValueError, match="Ownership|Payment|ownership|production|progress|approved|failed"
    ):
        instance.run(config)
    if bad not in {"wrong_build", "failed_deployment"}:
        owner.request.assert_not_called()


@pytest.mark.parametrize("bad", [None, "signature", "signer", "parent", "tree", "marker", "branch"])
def test_build_requires_verified_exact_source_tree_and_fast_forward(
    mocker: MockFixture, bad: str | None
) -> None:
    github = mocker.Mock()
    instance = Upgrade(
        ownership=mocker.Mock(),
        hcp=mocker.Mock(),
        github=github,
        authority=mocker.Mock(),
        authority_origin="https://tips.hushline.app",
        progress=mocker.Mock(),
    )
    config = {
        "order_id": ORDER,
        "release": {
            "tag": "v0.7.27",
            "source_sha": SOURCE,
            "build_sha": BUILD,
            "previous_sha": PREVIOUS,
        },
    }
    tree = [{"path": "hushline/version.py", "mode": "100644", "type": "blob", "sha": "4" * 40}]
    marker = {"order_id": ORDER, "tag": "v0.7.27", "source_sha": SOURCE}
    evidence: list[dict[str, Any]] = [
        {
            "sha": BUILD,
            "commit": {"verification": {"verified": True}, "tree": {"sha": "a" * 40}},
            "committer": {"login": "hushline-dev"},
            "parents": [{"sha": PREVIOUS}],
        },
        {"commit": {"tree": {"sha": "b" * 40}}},
        {"truncated": False, "tree": tree},
        {
            "truncated": False,
            "tree": tree
            + [
                {
                    "path": ".single-tenant-release.json",
                    "mode": "100644",
                    "type": "blob",
                    "sha": "5" * 40,
                }
            ],
        },
        {
            "type": "file",
            "size": 100,
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(marker).encode()).decode(),
        },
        {"ref": "refs/heads/single-tenant/" + ORDER, "object": {"sha": PREVIOUS}},
        {},
        {"object": {"sha": BUILD}},
    ]
    if bad == "signature":
        evidence[0]["commit"]["verification"]["verified"] = False
    elif bad == "signer":
        evidence[0]["committer"]["login"] = "another-user"
    elif bad == "parent":
        evidence[0]["parents"] = [{"sha": "9" * 40}]
    elif bad == "tree":
        evidence[3]["tree"] = evidence[3]["tree"] + [
            {"path": "unapproved.py", "mode": "100644", "type": "blob", "sha": "9" * 40}
        ]
    elif bad == "marker":
        marker["order_id"] = "another-order"
        evidence[4]["content"] = base64.b64encode(json.dumps(marker).encode()).decode()
    elif bad == "branch":
        evidence[5]["object"]["sha"] = "9" * 40
    github.side_effect = evidence
    if bad:
        with pytest.raises(ValueError, match="signed|source|marker|owned"):
            instance.build(config)
        assert all(call.args[0] == "GET" for call in github.call_args_list)
        return
    instance.build(config)
    assert github.call_args_list[-3].args[1] == (
        "/repos/scidsg/hushline/git/ref/heads/single-tenant/" + ORDER
    )
    assert github.call_args_list[-2].args == (
        "PATCH",
        "/repos/scidsg/hushline/git/refs/heads/single-tenant/" + ORDER,
        {"sha": BUILD, "force": False},
    )


@pytest.mark.parametrize("change", ["payment", "resources", "spec", "pending"])
def test_changes_between_branch_publication_and_deployment_stop_cloud_write(
    upgrade: tuple[Upgrade, Any, dict, Any], change: str
) -> None:
    instance, owner, config, app = upgrade
    fresh = deepcopy(app)
    if change == "payment":
        cast(Any, instance.authority).side_effect = [{}, ValueError("Payment changed")]
    elif change == "resources":
        owner.owned.side_effect = [{APP_ADDRESS: APP}, {APP_ADDRESS: DEPLOYMENT}]
    elif change == "spec":
        fresh["spec"]["services"][0]["envs"][0]["value"] = "EV[changed]"
    else:
        fresh["pending_deployment"] = deployment(PREVIOUS)
    owner.do.side_effect = [{"app": app}, {"app": fresh}]
    with pytest.raises(ValueError, match="changed|progress"):
        instance.run(config)
    owner.request.assert_not_called()


def test_exact_pending_deployment_recovers_without_another_cloud_write(
    upgrade: tuple[Upgrade, Any, dict, Any],
) -> None:
    instance, owner, config, app = upgrade
    app["pending_deployment"] = deployment()
    app["pending_deployment"]["phase"] = "BUILDING"
    assert instance.run(config)["state"] == "upgraded"
    owner.request.assert_not_called()

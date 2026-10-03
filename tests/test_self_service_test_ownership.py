"""Deployment and cleanup cannot adopt unrelated workspaces or resource IDs."""

import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import self_service_test_ownership as ownership

ORDER = "a" * 32
NAME, SOURCE = ownership.identity(ORDER)


def workspace() -> dict:
    return {
        "id": "ws-test123",
        "attributes": {
            "name": NAME,
            "source-name": SOURCE,
            "description": json.dumps({"schema": 1, "order_id": ORDER, "resources": None}),
            "working-directory": ownership.DIRECTORY,
            "execution-mode": "remote",
            "terraform-version": "1.13.5",
            "auto-apply": False,
            "auto-apply-run-trigger": False,
            "global-remote-state": False,
            "auto-destroy-activity-duration": None,
            "vcs-repo": None,
        },
        "relationships": {"project": {"data": {"id": ownership.PROJECT}}},
    }


def resources() -> dict:
    return {
        "digitalocean_project.staging": {
            "id": "project-id",
            "name": NAME,
            "description": f"Owned disposable Hush Line test {NAME}",
        },
        "digitalocean_database_cluster.db": {
            "id": "db-id",
            "name": NAME,
            "project_id": "project-id",
        },
        "digitalocean_app.staging": {
            "id": "app-id",
            "spec": [{"name": NAME}],
            "project_id": "project-id",
        },
        "digitalocean_database_firewall.staging": {
            "id": "firewall-id",
            "cluster_id": "db-id",
            "rule": [{"type": "app", "value": "app-id", "uuid": "computed-rule-id"}],
        },
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("name", "production"),
        ("source-name", "generic staging"),
        ("working-directory", "hushline-client-env"),
        ("auto-apply", True),
        ("global-remote-state", True),
        ("auto-destroy-activity-duration", "24h"),
        ("auto-destroy-at", "2026-10-04T00:00:00Z"),
        ("vcs-repo", {"identifier": "scidsg/hushline-infra"}),
    ],
)
def test_workspace_isolation_mismatch_is_rejected(key: str, value: object) -> None:
    data = workspace()
    data["attributes"][key] = value
    with pytest.raises(ValueError, match="ownership or isolation"):
        ownership.validate_workspace(data, ORDER)


def test_other_project_and_order_are_rejected() -> None:
    data = workspace()
    data["relationships"]["project"]["data"]["id"] = "production-project"
    with pytest.raises(ValueError, match="ownership|Cleanup|Resource|names"):
        ownership.validate_workspace(data, ORDER)
    with pytest.raises(ValueError, match="ownership|Cleanup|Resource|names"):
        ownership.validate_workspace(workspace(), "b" * 32)


def test_existing_workspace_is_never_mutated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ownership, "workspace", lambda order: workspace())
    api = Mock()
    monkeypatch.setattr(ownership, "tf", api)
    with pytest.raises(ValueError, match="already exists"):
        ownership.create(ORDER)
    api.assert_not_called()


def test_create_uses_no_automatic_destruction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ownership, "workspace", lambda order: None)
    api = Mock(side_effect=[{"data": workspace()}, {}])
    monkeypatch.setattr(ownership, "tf", api)
    ownership.create(ORDER)
    attrs = api.call_args_list[0].args[1]["data"]["attributes"]
    assert attrs["auto-apply"] is False
    assert "auto-destroy-activity-duration" not in attrs
    assert attrs["name"] == NAME


def test_recorded_ids_are_never_overwritten(monkeypatch: pytest.MonkeyPatch) -> None:
    data = workspace()
    data["attributes"]["description"] = json.dumps(
        {
            "schema": 1,
            "order_id": ORDER,
            "resources": ownership.validate_resources(resources(), ORDER),
        }
    )
    monkeypatch.setattr(ownership, "workspace", lambda order: data)
    api = Mock()
    monkeypatch.setattr(ownership, "tf", api)
    with pytest.raises(ValueError, match="overwrite"):
        ownership.record(ORDER)
    api.assert_not_called()


def test_cleanup_rejects_different_ids_before_cloud_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = workspace()
    ids = ownership.validate_resources(resources(), ORDER)
    data["attributes"]["description"] = json.dumps(
        {"schema": 1, "order_id": ORDER, "resources": ids}
    )
    modified = resources()
    modified["digitalocean_database_firewall.staging"]["id"] = "someone-elses-firewall"
    monkeypatch.setattr(ownership, "workspace", lambda order: data)
    monkeypatch.setattr(ownership, "read_state", lambda data: modified)
    live = Mock()
    monkeypatch.setattr(ownership, "validate_live", live)
    with pytest.raises(ValueError, match="different ownership IDs"):
        ownership.owned(ORDER)
    live.assert_not_called()


def test_partial_apply_cannot_be_cleaned_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ownership, "workspace", lambda order: workspace())
    state = Mock()
    monkeypatch.setattr(ownership, "read_state", state)
    with pytest.raises(ValueError, match="original resource ownership"):
        ownership.owned(ORDER)
    state.assert_not_called()


def test_foreign_project_resource_stops_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ownership,
        "do",
        lambda path: {
            "/projects/project-id": {"project": resources()["digitalocean_project.staging"]},
            "/apps/app-id": {"app": {"id": "app-id", "spec": {"name": NAME}}},
            "/databases/db-id": {"database": resources()["digitalocean_database_cluster.db"]},
        }[path],
    )
    monkeypatch.setattr(
        ownership,
        "inventory",
        lambda path, key: [
            {"urn": "do:app:app-id"},
            {"urn": "do:dbaas:db-id"},
            {"urn": "do:droplet:production"},
        ],
    )
    with pytest.raises(ValueError, match="different ownership"):
        ownership.validate_live(ownership.validate_resources(resources(), ORDER), ORDER)


def test_hostname_already_used_by_another_app_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ownership,
        "inventory",
        lambda path, key: (
            []
            if path != "/apps"
            else [{"spec": {"name": "other-instance", "domains": [{"name": "tips.customer.org"}]}}]
        ),
    )
    with pytest.raises(ValueError, match="existing instance"):
        ownership.preflight(ORDER, "tips.customer.org")


@pytest.mark.parametrize("alter", ["foreign-id", "update", "extra-resource"])
def test_destroy_plan_only_accepts_original_deletions(tmp_path: Path, alter: str) -> None:
    state = resources()
    ids = ownership.validate_resources(state, ORDER)
    changes = [
        {"address": address, "change": {"actions": ["delete"], "before": before}}
        for address, before in state.items()
    ]
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"resource_changes": changes}))
    ownership.guard_destroy(valid, ORDER, ids)
    changes = copy.deepcopy(changes)
    if alter == "foreign-id":
        changes[0]["change"]["before"]["id"] = "production-id"
    elif alter == "update":
        changes[0]["change"]["actions"] = ["update"]
    else:
        changes.append({"address": "digitalocean_app.production"})
    valid.write_text(json.dumps({"resource_changes": changes}))
    with pytest.raises(ValueError, match="ownership|Cleanup|Resource|names"):
        ownership.guard_destroy(valid, ORDER, ids)


def test_nonempty_workspace_is_never_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    data = workspace()
    data["attributes"]["description"] = json.dumps(
        {
            "schema": 1,
            "order_id": ORDER,
            "resources": ownership.validate_resources(resources(), ORDER),
        }
    )
    monkeypatch.setattr(ownership, "workspace", lambda order: data)
    monkeypatch.setattr(ownership, "read_state", lambda data: resources())
    api = Mock()
    monkeypatch.setattr(ownership, "tf", api)
    with pytest.raises(ValueError, match="resources are gone"):
        ownership.remove_workspace(ORDER)
    api.assert_not_called()


def test_workflow_cannot_sweep_other_instances() -> None:
    text = Path(".github/workflows/self_service_test_deploy.yml").read_text()
    assert "secrets.HUSHLINE_INFRA_STAGING_PAT" in text
    assert "secrets.HUSHLINE_INFRA_TOKEN" not in text
    assert text.count("environment: self-service-test-2447") == 1
    assert text.count("environment: ephemeral-staging") == 1
    assert "schedule:" not in text
    assert "number == 2447" in text
    assert "head.ref == 'feat/self-service-test-runner'" in text
    assert "self-service-test" in text
    assert text.count("plan_path: ${{ steps.plan.outputs.plan_path }}") == 2
    assert "terraform-destroy-workspace@" not in text
    assert "force: true" not in text
    assert "removeLabel" not in text


def test_empty_workspace_uses_server_side_safe_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    data = workspace()
    data["attributes"]["description"] = json.dumps(
        {
            "schema": 1,
            "order_id": ORDER,
            "resources": ownership.validate_resources(resources(), ORDER),
        }
    )
    monkeypatch.setattr(ownership, "workspace", lambda order: data)
    monkeypatch.setattr(ownership, "read_state", lambda data: {})
    api = Mock()
    monkeypatch.setattr(ownership, "tf", api)
    ownership.remove_workspace(ORDER)
    api.assert_called_once_with("/workspaces/ws-test123/actions/safe-delete", method="POST")


@pytest.mark.parametrize("kind", ["DEFAULT", "PRIMARY"])
def test_generated_domain_can_omit_name_but_custom_domain_cannot(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setattr(
        ownership,
        "inventory",
        lambda path, key: []
        if path != "/apps"
        else [{"spec": {"name": "other-instance", "domains": [{"type": kind}]}}],
    )
    if kind == "DEFAULT":
        ownership.preflight(ORDER, "tips.customer.org")
    else:
        with pytest.raises(ValueError, match="missing its hostname"):
            ownership.preflight(ORDER, "tips.customer.org")

"""Deployment and cleanup cannot adopt unrelated workspaces or resource IDs."""

import copy
import json
import urllib.error
from email.message import Message
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
            "spec": [{"name": ownership.app_name(ORDER)}],
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
            "/apps/app-id": {"app": {"id": "app-id", "spec": {"name": ownership.app_name(ORDER)}}},
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
            else [
                {"spec": {"name": "other-instance", "domains": [{"domain": "tips.customer.org"}]}}
            ]
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


@pytest.fixture()
def original_partial_order(monkeypatch: pytest.MonkeyPatch) -> dict:
    order = ownership.RECOVERY_ORDER
    name, source = ownership.identity(order)
    partial = {
        "digitalocean_project.staging": {
            "id": ownership.RECOVERY_IDS["digitalocean_project.staging"],
            "name": name,
            "description": f"Owned disposable Hush Line test {name}",
        },
        "digitalocean_database_cluster.db": {
            "id": ownership.RECOVERY_IDS["digitalocean_database_cluster.db"],
            "name": name,
            "project_id": ownership.RECOVERY_IDS["digitalocean_project.staging"],
        },
    }
    data = workspace()
    data["attributes"].update(
        name=name,
        **{
            "source-name": source,
            "description": json.dumps({"schema": 1, "order_id": order, "resources": None}),
        },
    )
    monkeypatch.setenv("CUSTOM_DOMAIN", "hushline.foo")
    monkeypatch.setattr(ownership, "workspace", lambda value: data)
    monkeypatch.setattr(ownership, "read_state", lambda value: partial)
    monkeypatch.setattr(
        ownership,
        "do",
        lambda path: {
            "project": partial["digitalocean_project.staging"],
            "database": partial["digitalocean_database_cluster.db"],
        },
    )
    monkeypatch.setattr(
        ownership,
        "inventory",
        lambda path, key: (
            []
            if path == "/apps"
            else [{"urn": "do:dbaas:" + ownership.RECOVERY_IDS["digitalocean_database_cluster.db"]}]
        ),
    )
    return partial


def recovery_plan(partial: dict) -> dict:
    changes = [
        {
            "address": address,
            "change": {
                "actions": ["no-op"],
                "before": copy.deepcopy(value),
                "after": copy.deepcopy(value),
            },
        }
        for address, value in partial.items()
    ]
    changes.extend(
        [
            {
                "address": "digitalocean_app.staging",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "spec": [{"name": ownership.app_name(ownership.RECOVERY_ORDER)}],
                        "project_id": ownership.RECOVERY_IDS["digitalocean_project.staging"],
                    },
                },
            },
            {
                "address": "digitalocean_database_firewall.staging",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {
                        "cluster_id": ownership.RECOVERY_IDS["digitalocean_database_cluster.db"],
                        "rule": [{"type": "app", "value": None}],
                    },
                    "after_unknown": {"rule": [{"value": True}]},
                },
            },
        ]
    )
    return {
        "resource_changes": changes,
        "prior_state": {
            "values": {
                "root_module": {
                    "resources": [
                        {"address": address, "values": value} for address, value in partial.items()
                    ]
                }
            }
        },
    }


def test_recovery_only_reads_original_owned_partial_state(original_partial_order: dict) -> None:
    assert ownership.recovery(ownership.RECOVERY_ORDER) == original_partial_order
    with pytest.raises(ValueError, match="restricted"):
        ownership.recovery(ORDER)


@pytest.mark.parametrize("alter", ["foreign-id", "foreign-name", "foreign-project", "extra-app"])
def test_recovery_rejects_foreign_or_already_created_resources(
    original_partial_order: dict, alter: str
) -> None:
    if alter == "extra-app":
        original_partial_order["digitalocean_app.staging"] = {"id": "foreign"}
    else:
        key = {"foreign-id": "id", "foreign-name": "name", "foreign-project": "project_id"}[alter]
        original_partial_order["digitalocean_database_cluster.db"][key] = "foreign"
    with pytest.raises(ValueError, match="original|ownership"):
        ownership.recovery(ownership.RECOVERY_ORDER)


def test_recovery_refuses_other_hostname(
    original_partial_order: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUSTOM_DOMAIN", "other.customer.org")
    with pytest.raises(ValueError, match="restricted"):
        ownership.recovery(ownership.RECOVERY_ORDER)


def test_recovery_refuses_foreign_project_members(
    original_partial_order: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ownership, "inventory", lambda path, key: [{"urn": "do:dbaas:foreign"}])
    with pytest.raises(ValueError, match="exclusively"):
        ownership.recovery(ownership.RECOVERY_ORDER)


def test_recovery_plan_preserves_database_and_only_creates_missing_resources(
    original_partial_order: dict, tmp_path: Path
) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(recovery_plan(original_partial_order)))
    ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.mark.parametrize(
    "alter",
    [
        "database-update",
        "database-id",
        "project-rename",
        "app-update",
        "foreign-project",
        "foreign-database",
        "foreign-app",
        "extra-resource",
        "import",
        "move",
        "module",
        "drift",
    ],
)
def test_recovery_plan_cannot_touch_existing_or_foreign_resources(
    original_partial_order: dict, tmp_path: Path, alter: str
) -> None:
    plan = recovery_plan(original_partial_order)
    project, database, app, firewall = plan["resource_changes"]
    if alter == "database-update":
        database["change"]["actions"] = ["update"]
    elif alter == "database-id":
        database["change"]["before"]["id"] = "foreign"
    elif alter == "project-rename":
        project["change"]["after"]["name"] = "foreign"
    elif alter == "app-update":
        app["change"]["actions"] = ["update"]
    elif alter == "foreign-project":
        app["change"]["after"]["project_id"] = "foreign"
    elif alter == "foreign-database":
        firewall["change"]["after"]["cluster_id"] = "foreign"
    elif alter == "foreign-app":
        firewall["change"]["after"]["rule"][0]["value"] = "foreign"
    elif alter == "extra-resource":
        plan["resource_changes"].append(copy.deepcopy(app))
    elif alter == "import":
        app["change"]["importing"] = {"id": "foreign"}
    elif alter == "move":
        app["previous_address"] = "digitalocean_app.production"
    elif alter == "module":
        app["module_address"] = "module.production"
    else:
        plan["resource_drift"] = [project]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="Recovery"):
        ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.mark.parametrize(
    "url",
    [
        "http://archivist.terraform.io/v1/object/test",
        "https://evil.example/v1/object/test",
        "https://archivist.terraform.io.evil.example/v1/object/test",
        "https://user:password@archivist.terraform.io/v1/object/test",
        "https://archivist.terraform.io:444/v1/object/test",
        "https://app.terraform.io/arbitrary/path",
    ],
)
def test_state_download_refuses_token_forwarding_to_untrusted_url(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setattr(
        ownership, "tf", lambda path: {"data": {"attributes": {"hosted-state-download-url": url}}}
    )
    request = Mock()
    monkeypatch.setattr(ownership, "request", request)
    with pytest.raises(ValueError, match="Invalid state"):
        ownership.read_state({"id": "ws-owned"})
    request.assert_not_called()


def test_signed_storage_download_does_not_forward_api_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STAGING_TF_TOKEN", "test-only-credential")
    monkeypatch.setattr(
        ownership,
        "tf",
        lambda path: {
            "data": {
                "attributes": {
                    "hosted-state-download-url": "https://archivist.terraform.io/v1/object/test",
                }
            }
        },
    )
    request = Mock(return_value={"resources": []})
    monkeypatch.setattr(ownership, "request", request)
    assert ownership.read_state({"id": "ws-owned"}) == {}
    request.assert_called_once_with("archivist.terraform.io", "/v1/object/test", None)


@pytest.mark.parametrize("prefix", ["/api", "/api/v2"])
def test_current_hcp_hosted_state_route_is_authenticated(
    monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    monkeypatch.setenv("STAGING_TF_TOKEN", "test-only-credential")
    path = prefix + "/state-versions/sv-Test123/hosted_state"
    monkeypatch.setattr(
        ownership,
        "tf",
        lambda value: {
            "data": {
                "attributes": {
                    "hosted-state-download-url": "https://app.terraform.io" + path,
                }
            }
        },
    )
    request = Mock(return_value={"resources": []})
    monkeypatch.setattr(ownership, "request", request)
    assert ownership.read_state({"id": "ws-owned"}) == {}
    request.assert_called_once_with("app.terraform.io", path, "test-only-credential")


@pytest.mark.parametrize(
    "target",
    ["https://archivist.terraform.io/v1/object/test", "https://evil.example/v1/object/test"],
)
def test_hosted_state_redirect_is_allowlisted_and_never_forwards_token(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    monkeypatch.setenv("STAGING_TF_TOKEN", "test-only-credential")
    source = "https://app.terraform.io/api/state-versions/sv-Test123/hosted_state"
    monkeypatch.setattr(
        ownership,
        "tf",
        lambda path: {"data": {"attributes": {"hosted-state-download-url": source}}},
    )
    headers = Message()
    headers["Location"] = target
    error = urllib.error.HTTPError(source, 302, "Found", headers, None)
    request = Mock(side_effect=[error, {"resources": []}])
    monkeypatch.setattr(ownership, "request", request)
    if "evil.example" in target:
        with pytest.raises(ValueError, match="approved HCP"):
            ownership.read_state({"id": "ws-owned"})
        assert request.call_count == 1
    else:
        assert ownership.read_state({"id": "ws-owned"}) == {}
        assert request.call_args_list[-1].args == (
            "archivist.terraform.io",
            "/v1/object/test",
            None,
        )


def test_failed_create_placeholder_has_no_resource_ownership() -> None:
    raw = {
        "resources": [
            {"mode": "managed", "type": "digitalocean_app", "name": "staging", "instances": []}
        ]
    }
    assert ownership.state_resources(raw) == {}
    raw["resources"].append(copy.deepcopy(raw["resources"][0]))
    with pytest.raises(ValueError, match="ambiguous"):
        ownership.state_resources(raw)


def test_empty_foreign_placeholder_is_still_rejected() -> None:
    raw = {
        "resources": [
            {"mode": "managed", "type": "digitalocean_app", "name": "production", "instances": []}
        ]
    }
    with pytest.raises(ValueError, match="outside"):
        ownership.state_resources(raw)

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
    assert text.count("environment: self-service-test-2447") == 2
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
        plan["resource_drift"] = [
            {"address": "digitalocean_database_cluster.production", "change": project["change"]}
        ]
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


def test_recovery_accepts_owned_refresh_metadata_only_with_noop_plan(
    original_partial_order: dict, tmp_path: Path
) -> None:
    plan = recovery_plan(original_partial_order)
    database = copy.deepcopy(plan["resource_changes"][1])
    database["change"]["actions"] = ["update"]
    database["change"]["after"]["computed_connection_metadata"] = "refreshed"
    plan["resource_drift"] = [database]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    ownership.guard_recovery(path, ownership.RECOVERY_ORDER)
    plan["resource_changes"][1]["change"]["actions"] = ["update"]
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="cannot modify"):
        ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.fixture()
def original_failed_app(original_partial_order: dict, monkeypatch: pytest.MonkeyPatch) -> dict:
    order = ownership.RECOVERY_ORDER
    project = ownership.RECOVERY_IDS["digitalocean_project.staging"]
    db = ownership.RECOVERY_IDS["digitalocean_database_cluster.db"]
    services = [
        {
            "name": name,
            "git": {
                "branch": f"self-service-test/{order}",
                "repo_clone_url": "https://github.com/scidsg/hushline.git",
            },
        }
        for name in ["app", "app-onion"]
    ]
    spec = {
        "name": ownership.app_name(order),
        "domain": [{"name": "hushline.foo"}],
        "service": services,
    }
    original_partial_order["digitalocean_app.staging"] = {
        "id": ownership.RECOVERY_APP,
        "project_id": project,
        "spec": [spec],
    }
    live = {
        "id": ownership.RECOVERY_APP,
        "spec": {
            "name": ownership.app_name(order),
            "domains": [{"domain": "hushline.foo"}],
            "services": services,
        },
        "active_deployment": None,
    }
    monkeypatch.setattr(
        ownership,
        "do",
        lambda path: {
            f"/projects/{project}": {
                "project": original_partial_order["digitalocean_project.staging"]
            },
            f"/databases/{db}": {
                "database": original_partial_order["digitalocean_database_cluster.db"]
            },
            f"/apps/{ownership.RECOVERY_APP}": {"app": live},
        }[path],
    )
    monkeypatch.setattr(
        ownership,
        "inventory",
        lambda path, key: [{"urn": f"do:dbaas:{db}"}, {"urn": f"do:app:{ownership.RECOVERY_APP}"}],
    )
    return original_partial_order


def failed_app_plan(resources: dict) -> dict:
    partial = {k: v for k, v in resources.items() if k in ownership.RECOVERY_IDS}
    plan = recovery_plan(partial)
    for change in plan["resource_changes"]:
        if change["address"] == "digitalocean_app.staging":
            value = resources[change["address"]]
            change["change"].update(
                actions=["update"], before=copy.deepcopy(value), after=copy.deepcopy(value)
            )
        elif change["address"] == "digitalocean_database_firewall.staging":
            change["change"]["after"]["rule"][0]["value"] = ownership.RECOVERY_APP
            change["change"]["after_unknown"] = {}
    plan["prior_state"]["values"]["root_module"]["resources"].append(
        {"address": "digitalocean_app.staging", "values": resources["digitalocean_app.staging"]}
    )
    return plan


def test_failed_app_can_be_updated_without_replacement(
    original_failed_app: dict, tmp_path: Path
) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(failed_app_plan(original_failed_app)))
    ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.mark.parametrize(
    "alter", ["replace", "foreign-id", "domain", "branch", "firewall", "database"]
)
def test_failed_app_recovery_rejects_escape(
    original_failed_app: dict, tmp_path: Path, alter: str
) -> None:
    plan = failed_app_plan(original_failed_app)
    app = next(
        x["change"] for x in plan["resource_changes"] if x["address"] == "digitalocean_app.staging"
    )
    if alter == "replace":
        app["actions"] = ["delete", "create"]
    elif alter == "foreign-id":
        app["after"]["id"] = "foreign"
    elif alter == "domain":
        app["after"]["spec"][0]["domain"] = [{"name": "other.foo"}]
    elif alter == "branch":
        app["after"]["spec"][0]["service"][0]["git"]["branch"] = "main"
    elif alter == "firewall":
        plan["resource_changes"][-1]["change"]["after"]["rule"][0]["value"] = "foreign"
    else:
        plan["resource_changes"][1]["change"]["actions"] = ["update"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="Recovery"):
        ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.mark.parametrize(
    "field", ["active_deployment", "pending_deployment", "in_progress_deployment"]
)
def test_live_app_cannot_be_recovered(
    original_failed_app: dict, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    api = ownership.do

    def live(path: str) -> dict:
        response = api(path)
        if "app" in response:
            response["app"][field] = {"phase": "DEPLOYING"}
        return response

    monkeypatch.setattr(ownership, "do", live)
    with pytest.raises(ValueError, match="never-live"):
        ownership.recovery(ownership.RECOVERY_ORDER)


@pytest.mark.parametrize("alter", [None, "workspace", "lineage", "serial", "app-id", "not-tainted"])
def test_state_repair_only_removes_original_app_taint(
    original_failed_app: dict, monkeypatch: pytest.MonkeyPatch, alter: str | None
) -> None:
    name, _ = ownership.identity(ownership.RECOVERY_ORDER)
    monkeypatch.setenv("TF_WORKSPACE", name)
    raw: dict = {
        "lineage": "original-lineage",
        "serial": 4,
        "resources": [
            {
                "mode": "managed",
                "type": address.split(".")[0],
                "name": address.split(".")[1],
                "instances": [
                    {
                        "attributes": value,
                        **({"status": "tainted"} if address == "digitalocean_app.staging" else {}),
                    }
                ],
            }
            for address, value in original_failed_app.items()
        ],
    }
    monkeypatch.setattr(ownership, "read_raw_state", lambda data: raw)
    pulled = copy.deepcopy(raw)
    shown = name
    if alter == "workspace":
        shown = "production"
    elif alter == "lineage":
        pulled["lineage"] = "foreign"
    elif alter == "serial":
        pulled["serial"] += 1
    elif alter == "app-id":
        pulled["resources"][-1]["instances"][0]["attributes"]["id"] = "foreign"
    elif alter == "not-tainted":
        raw["resources"][-1]["instances"][0].pop("status")
        pulled = copy.deepcopy(raw)
    after = copy.deepcopy(raw)
    after["serial"] += 1
    after["resources"][-1]["instances"][0].pop("status", None)
    calls = []

    def run(args: list, **kwargs: object) -> Mock:
        calls.append(args)
        if args[1:] == ["workspace", "show"]:
            output = shown
        elif args[1:] == ["state", "pull"]:
            output = json.dumps(after if len(calls) > 3 else pulled)
        else:
            output = ""
        return Mock(returncode=0, stdout=output)

    monkeypatch.setattr(ownership.subprocess, "run", run)
    if alter:
        with pytest.raises(ValueError, match="workspace|state|taint"):
            ownership.repair_failed_app_state(ownership.RECOVERY_ORDER)
        assert all("untaint" not in command for command in calls)
    else:
        ownership.repair_failed_app_state(ownership.RECOVERY_ORDER)
        assert calls[2] == ["terraform", "untaint", "-lock-timeout=30s", "digitalocean_app.staging"]


@pytest.mark.parametrize("alter", [None, "attribute", "lineage", "serial", "foreign-shell"])
def test_state_repair_verification_accepts_reordering_only(alter: str | None) -> None:
    before: dict = {
        "lineage": "original",
        "serial": 3,
        "resources": [
            {
                "mode": "managed",
                "type": "digitalocean_project",
                "name": "staging",
                "instances": [{"attributes": {"id": "original-project"}}],
            },
            {
                "mode": "managed",
                "type": "digitalocean_app",
                "name": "staging",
                "instances": [{"status": "tainted", "attributes": {"id": ownership.RECOVERY_APP}}],
            },
            {
                "mode": "managed",
                "type": "digitalocean_database_firewall",
                "name": "staging",
                "instances": [],
            },
        ],
    }
    after = copy.deepcopy(before)
    after["serial"] = 4
    after["resources"][1]["instances"][0].pop("status")
    after["resources"] = list(reversed(after["resources"][:2]))
    if alter == "attribute":
        after["resources"][0]["instances"][0]["attributes"]["id"] = "foreign"
    elif alter == "lineage":
        after["lineage"] = "foreign"
    elif alter == "serial":
        after["serial"] = 5
    elif alter == "foreign-shell":
        after["resources"].append(
            {"mode": "managed", "type": "digitalocean_droplet", "name": "foreign", "instances": []}
        )
    if alter:
        with pytest.raises(ValueError, match="State|outside"):
            ownership.verify_app_state_repair(before, after)
    else:
        ownership.verify_app_state_repair(before, after)


@pytest.mark.parametrize("alter", [None, "foreign-urn", "spec", "foreign-id"])
def test_original_app_refresh_may_only_fill_its_own_urn(
    original_failed_app: dict, tmp_path: Path, alter: str | None
) -> None:
    plan = failed_app_plan(original_failed_app)
    before = copy.deepcopy(original_failed_app["digitalocean_app.staging"])
    after = copy.deepcopy(before)
    after["urn"] = f"do:app:{ownership.RECOVERY_APP}"
    after["active_deployment_id"] = ""
    after["default_ingress"] = "https://original.ondigitalocean.app"
    after["created_at"] = "platform-assigned"
    after["updated_at"] = "platform-assigned"
    if alter == "foreign-urn":
        after["urn"] = "do:app:foreign"
    elif alter == "spec":
        after["spec"][0]["name"] = "foreign"
    elif alter == "foreign-id":
        after["id"] = "foreign"
    plan["resource_drift"] = [
        {
            "address": "digitalocean_app.staging",
            "change": {"actions": ["update"], "before": before, "after": after},
        }
    ]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    if alter:
        with pytest.raises(ValueError, match="refresh"):
            ownership.guard_recovery(path, ownership.RECOVERY_ORDER)
    else:
        ownership.guard_recovery(path, ownership.RECOVERY_ORDER)


@pytest.mark.parametrize("alter", [None, "domain", "route", "redirect", "general-env", "source"])
def test_app_refresh_allows_only_platform_defaults_and_secret_encoding(alter: str | None) -> None:
    before: dict = {
        "id": ownership.RECOVERY_APP,
        "project_id": "original",
        "spec": [
            {
                "name": "original",
                "domain": [{"name": "hushline.foo"}],
                "domains": [],
                "ingress": [],
                "service": [
                    {
                        "name": "app",
                        "git": [{"branch": "original"}],
                        "env": [
                            {"key": "SECRET_KEY", "type": "SECRET", "value": "private"},
                            {
                                "key": "PUBLIC_BASE_URL",
                                "type": "GENERAL",
                                "value": "https://hushline.foo",
                            },
                        ],
                    }
                ],
            }
        ],
    }
    after = copy.deepcopy(before)
    spec = after["spec"][0]
    spec["domains"] = ["hushline.foo"]
    spec["service"][0]["env"][0]["value"] = "encrypted-private"
    rule: dict = {
        "component": [{"name": "app", "rewrite": "", "preserve_path_prefix": True}],
        "match": [{"path": [{"prefix": "/"}], "authority": []}],
        "redirect": [],
        "cors": [],
    }
    spec["ingress"] = [{"rule": [rule], "secure_header": []}]
    if alter == "domain":
        spec["domains"] = ["other.foo"]
    elif alter == "route":
        rule["component"][0]["name"] = "other-app"
    elif alter == "redirect":
        rule["redirect"] = [{"uri": "https://other.foo"}]
    elif alter == "general-env":
        spec["service"][0]["env"][1]["value"] = "https://other.foo"
    elif alter == "source":
        spec["service"][0]["git"][0]["branch"] = "main"
    if alter in {"domain", "route", "redirect"}:
        with pytest.raises(ValueError, match="domain|routing"):
            ownership.app_refresh_equivalent(before, after)
    else:
        assert ownership.app_refresh_equivalent(before, after) is (alter is None)


@pytest.mark.parametrize("compressed", [False, True])
def test_runtime_diagnostics_keep_secrets_private(
    monkeypatch: pytest.MonkeyPatch, compressed: bool
) -> None:
    url = "https://appbuild-logs-sfo3.sfo3.digitaloceanspaces.com/owned?signature=private"
    monkeypatch.setattr(ownership, "do", lambda path: {"historic_urls": [url]})
    raw = (
        b"> Running migrations\nsqlalchemy.exc.ProgrammingError: relation does not exist\n"
        b"SECRET=never-publish-this\n"
    )
    payload = ownership.gzip.compress(raw) if compressed else raw
    response = Mock()
    response.__enter__ = Mock(return_value=Mock(read=Mock(return_value=payload)))
    response.__exit__ = Mock(return_value=None)
    opener = Mock(open=Mock(return_value=response))
    monkeypatch.setattr(ownership.urllib.request, "build_opener", lambda *args: opener)
    result = ownership.sanitized_runtime_logs(ownership.RECOVERY_APP, "owned-deployment", "app")
    assert result["available"] is True
    assert result["markers"] == ["migrations_started", "missing_table"]
    assert result["error_classes"] == ["ProgrammingError"]
    assert "never-publish-this" not in json.dumps(result)
    assert "signature" not in json.dumps(result)
    assert opener.open.call_args.args == (url,)


def test_runtime_logs_reject_foreign_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ownership, "do", lambda path: {"historic_urls": ["https://foreign.example/secret"]}
    )
    opener = Mock()
    monkeypatch.setattr(ownership.urllib.request, "build_opener", opener)
    result = ownership.sanitized_runtime_logs(ownership.RECOVERY_APP, "owned-deployment", "app")
    assert result["available"] is False
    opener.assert_not_called()

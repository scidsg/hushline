"""Generic customer ownership never adopts another instance or treats errors as absence."""

import json
import secrets
from copy import deepcopy
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_ownership import (
    APP_ADDRESS,
    DATABASE_ADDRESS,
    DIRECTORY,
    FIREWALL_ADDRESS,
    PROJECT_ADDRESS,
    PROJECT_NAME,
    SOURCE_PREFIX,
    CloudAPI,
    MissingResource,
    Ownership,
    state_resources,
    validate_state,
)
from scripts.single_tenant_live_plan import RESOURCES, identity

ORDER = "a" * 32
IDS = {
    address: "00000000-0000-0000-0000-" + str(index).zfill(12)
    for index, address in enumerate(sorted(RESOURCES), start=1)
}


def project() -> dict[str, Any]:
    return {
        "data": {
            "id": "prj-Isolated",
            "attributes": {"name": PROJECT_NAME},
            "relationships": {"organization": {"data": {"id": "isolated"}}},
        }
    }


def workspace(*, recorded: bool = False) -> dict[str, Any]:
    name, _ = identity(ORDER)
    return {
        "id": "ws-Owned",
        "attributes": {
            "name": name,
            "source-name": SOURCE_PREFIX + ORDER,
            "working-directory": DIRECTORY,
            "execution-mode": "remote",
            "terraform-version": "1.13.5",
            "auto-apply": False,
            "auto-apply-run-trigger": False,
            "global-remote-state": False,
            "queue-all-runs": False,
            "description": json.dumps(
                {"v": 1, "o": ORDER, "r": [IDS[a] for a in sorted(RESOURCES)] if recorded else None}
            ),
        },
        "relationships": {"project": {"data": {"id": "prj-Isolated"}}},
    }


def scope(request: Any) -> Ownership:
    return Ownership(organization="isolated", project_id="prj-Isolated", request=request)


def resources() -> dict[str, Any]:
    name, app_name = identity(ORDER)
    return {
        PROJECT_ADDRESS: {
            "id": IDS[PROJECT_ADDRESS],
            "name": name,
            "description": "Owned Hush Line Single Tenant " + name,
        },
        APP_ADDRESS: {
            "id": IDS[APP_ADDRESS],
            "spec": [{"name": app_name}],
            "project_id": IDS[PROJECT_ADDRESS],
        },
        DATABASE_ADDRESS: {
            "id": IDS[DATABASE_ADDRESS],
            "name": name,
            "project_id": IDS[PROJECT_ADDRESS],
        },
        FIREWALL_ADDRESS: {
            "id": IDS[FIREWALL_ADDRESS],
            "cluster_id": IDS[DATABASE_ADDRESS],
            "rule": [{"type": "app", "value": IDS[APP_ADDRESS], "uuid": "provider-computed-field"}],
        },
    }


def test_configuration_has_no_organization_or_project_fallback() -> None:
    for organization, project_id in [
        ("", "prj-Isolated"),
        ("isolated", ""),
        ("../prod", "prj-Isolated"),
    ]:
        with pytest.raises(ValueError, match="explicit isolated"):
            Ownership(organization=organization, project_id=project_id, request=Mock())


def test_creation_rejects_existing_workspace_before_any_write() -> None:
    api = Mock(side_effect=[project(), {"data": workspace()}])
    with pytest.raises(ValueError, match="cannot adopt"):
        scope(api).create_workspace(ORDER)
    assert all(call.args[0] == "GET" for call in api.call_args_list)


def test_configured_production_project_cannot_be_used_for_customer_creation() -> None:
    value = project()
    value["data"]["attributes"]["name"] = "Production"
    api = Mock(return_value=value)
    with pytest.raises(ValueError, match="not the isolated"):
        scope(api).create_workspace(ORDER)
    api.assert_called_once()
    assert api.call_args.args[0] == "GET"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("auto-apply", True),
        ("global-remote-state", True),
        ("vcs-repo", {"branch": "main"}),
        ("working-directory", "hushline-env"),
        ("auto-destroy-at", "2026-10-06T00:00:00Z"),
    ],
)
def test_workspace_must_remain_exactly_isolated(key: str, value: Any) -> None:
    data = workspace()
    data["attributes"][key] = value
    with pytest.raises(ValueError, match="ownership or isolation"):
        scope(Mock()).validate_workspace(data, ORDER)


def test_exact_state_relationships_and_provider_are_required() -> None:
    owned = resources()
    assert validate_state(owned, ORDER) == IDS
    foreign = deepcopy(owned)
    foreign[DATABASE_ADDRESS]["project_id"] = "existing-production-project"
    with pytest.raises(ValueError, match="relationships escaped"):
        validate_state(foreign, ORDER)
    state: dict[str, Any] = {
        "resources": [
            {
                "type": "digitalocean_app",
                "name": "tenant",
                "mode": "managed",
                "provider": 'provider["registry.terraform.io/digitalocean/digitalocean"]',
                "instances": [{"attributes": owned[APP_ADDRESS]}],
            }
        ]
    }
    assert state_resources(state) == {APP_ADDRESS: owned[APP_ADDRESS]}
    state["resources"][0]["instances"][0]["index_key"] = 0
    with pytest.raises(ValueError, match="ambiguous"):
        state_resources(state)


@pytest.mark.parametrize("status", [401, 302, 500])
def test_authentication_errors_redirects_and_outages_never_mean_absence(
    mocker: MockFixture, status: int
) -> None:
    session = mocker.patch("requests.Session").return_value.__enter__.return_value
    response = session.request.return_value.__enter__.return_value
    response.status_code = status
    api = CloudAPI(terraform_token=secrets.token_hex(16), digitalocean_token=secrets.token_hex(16))
    with pytest.raises(ValueError, match="ownership is unverified"):
        api.request("GET", "https://api.digitalocean.com/v2/apps/unit-only")
    assert session.trust_env is False
    assert session.request.call_args.kwargs["allow_redirects"] is False


def test_only_actual_404_proves_resource_absence(mocker: MockFixture) -> None:
    session = mocker.patch("requests.Session").return_value.__enter__.return_value
    session.request.return_value.__enter__.return_value.status_code = 404
    api = CloudAPI(terraform_token=secrets.token_hex(16), digitalocean_token=secrets.token_hex(16))
    with pytest.raises(MissingResource):
        api.request("GET", "https://api.digitalocean.com/v2/apps/unit-only")


def test_project_cannot_be_deleted_while_either_service_remains() -> None:
    api = Mock(return_value={"app": {"id": IDS[APP_ADDRESS]}})
    with pytest.raises(ValueError, match="service remains"):
        scope(api).verify_services_absent(ORDER, IDS)
    api.assert_called_once()
    assert api.call_args.args[0] == "GET"


def test_project_membership_must_be_empty_after_services_are_deleted() -> None:
    name, _ = identity(ORDER)
    api = Mock(
        side_effect=[
            MissingResource(),
            MissingResource(),
            {
                "project": {
                    "id": IDS[PROJECT_ADDRESS],
                    "name": name,
                    "description": "Owned Hush Line Single Tenant " + name,
                }
            },
            {"resources": [{"urn": "do:app:another-instance"}]},
        ]
    )
    with pytest.raises(ValueError, match="membership must be empty"):
        scope(api).verify_services_absent(ORDER, IDS)
    assert all(call.args[0] == "GET" for call in api.call_args_list)


def test_empty_owned_workspace_is_removed_only_after_three_provider_404s() -> None:
    api = Mock(
        side_effect=[
            project(),
            {"data": workspace(recorded=True)},
            MissingResource(),
            MissingResource(),
            MissingResource(),
            {},
        ]
    )
    scope(api).remove_empty_workspace(ORDER, {"resources": []})
    assert [call.args[0] for call in api.call_args_list] == [
        "GET",
        "GET",
        "GET",
        "GET",
        "GET",
        "POST",
    ]
    assert (
        api.call_args.args[1]
        == "https://app.terraform.io/api/v2/workspaces/ws-Owned/actions/safe-delete"
    )


def test_nonempty_workspace_is_never_removed() -> None:
    api = Mock(side_effect=[project(), {"data": workspace(recorded=True)}])
    owned = resources()
    state: dict[str, Any] = {
        "resources": [
            {
                "type": "digitalocean_app",
                "name": "tenant",
                "mode": "managed",
                "provider": 'provider["registry.terraform.io/digitalocean/digitalocean"]',
                "instances": [{"attributes": owned[APP_ADDRESS]}],
            }
        ]
    }
    with pytest.raises(ValueError, match="Only an empty"):
        scope(api).remove_empty_workspace(ORDER, state)
    assert all(call.args[0] == "GET" for call in api.call_args_list)


def test_ownership_record_cannot_be_overwritten_or_changed() -> None:
    api = Mock(side_effect=[project(), {"data": workspace(recorded=True)}])
    with pytest.raises(ValueError, match="cannot be overwritten"):
        scope(api).record(ORDER, resources())
    api = Mock(side_effect=[project(), {"data": workspace(recorded=True)}])
    changed = resources()
    changed[APP_ADDRESS]["id"] = "00000000-0000-0000-0000-000000009999"
    changed[FIREWALL_ADDRESS]["rule"][0]["value"] = changed[APP_ADDRESS]["id"]
    with pytest.raises(ValueError, match="original ownership record"):
        scope(api).owned(ORDER, changed)


def test_new_workspace_has_no_automatic_or_shared_execution_path() -> None:
    api = Mock(side_effect=[project(), MissingResource(), {"data": workspace()}, {}])
    assert scope(api).create_workspace(ORDER) == "ws-Owned"
    assert [call.args[0] for call in api.call_args_list] == ["GET", "GET", "POST", "POST"]
    attributes = api.call_args_list[2].args[2]["data"]["attributes"]
    assert attributes["auto-apply"] is False
    assert attributes["auto-apply-run-trigger"] is False
    assert attributes["global-remote-state"] is False
    assert attributes["queue-all-runs"] is False
    assert attributes["working-directory"] == DIRECTORY
    assert (
        api.call_args_list[2].args[1]
        == "https://app.terraform.io/api/v2/organizations/isolated/workspaces"
    )
    assert api.call_args.args[1].endswith("/workspaces/ws-Owned/relationships/tags")


@pytest.mark.parametrize(
    ("name", "identifier", "status"),
    [
        ("HushLineDev", "a" * 40, "active"),
        ("Production", "a" * 40, "active"),
        ("HushLineDev", "b" * 40, "active"),
        ("HushLineDev", "a" * 40, "locked"),
    ],
)
def test_provider_team_is_verified_before_customer_operations(
    name: str, identifier: str, status: str
) -> None:
    from scripts.single_tenant_live_ownership import verify_team

    transport = Mock(
        return_value={
            "account": {
                "status": status,
                "team": {"uuid": identifier, "name": name},
            }
        }
    )
    if name == "HushLineDev" and identifier == "a" * 40 and status == "active":
        verify_team(transport, "a" * 40)
    else:
        with pytest.raises(ValueError, match="team"):
            verify_team(transport, "a" * 40)
    transport.assert_called_once_with("GET", "https://api.digitalocean.com/v2/account", None)


@pytest.mark.parametrize("metadata", [None, {}, {"total": 0}])
def test_explicit_null_database_inventory_is_empty(metadata: Any) -> None:
    request = Mock(return_value={"databases": None, "meta": metadata})
    assert scope(request).inventory("/databases", "databases") == []
    request.assert_called_once_with(
        "GET", "https://api.digitalocean.com/v2/databases?per_page=200&page=1", None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"databases": None, "meta": {"total": 1}},
        {"databases": None, "meta": {"total": False}},
        {"databases": None, "meta": []},
        {
            "databases": None,
            "links": {"pages": {"next": "https://api.digitalocean.com/v2/databases?page=2"}},
        },
        {"databases": {}},
        {"databases": [None]},
        {"databases": "empty"},
    ],
)
def test_incomplete_or_malformed_database_inventory_cannot_authorize_creation(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="inventory"):
        scope(Mock(return_value=payload)).inventory("/databases", "databases")


@pytest.mark.parametrize(("path", "key"), [("/apps", "apps"), ("/projects", "projects")])
def test_null_inventory_is_not_a_generic_absence_fallback(path: str, key: str) -> None:
    with pytest.raises(ValueError, match="Invalid cloud resource inventory"):
        scope(Mock(return_value={key: None})).inventory(path, key)


def test_missing_database_inventory_and_api_failures_still_stop() -> None:
    with pytest.raises(KeyError):
        scope(Mock(return_value={})).inventory("/databases", "databases")
    with pytest.raises(ValueError, match="API unavailable"):
        scope(Mock(side_effect=ValueError("API unavailable"))).inventory("/databases", "databases")


def test_omitted_app_inventory_with_explicit_zero_count_is_empty() -> None:
    request = Mock(return_value={"meta": {"total": 0}})
    assert scope(request).inventory("/apps", "apps") == []
    assert request.call_args.args[0] == "GET"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"meta": {}},
        {"meta": {"total": False}},
        {"meta": {"total": 1}},
        {"meta": {"total": 0}, "links": {"pages": {"next": "next-page"}}},
        {"meta": {"total": 0}, "links": {"pages": {"next": False}}},
    ],
)
def test_omitted_app_inventory_without_proven_empty_final_page_stops(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="inventory"):
        scope(Mock(return_value=payload)).inventory("/apps", "apps")

"""Fresh authority and resource-absence gates control irreversible boundaries."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from scripts.single_tenant_live_lifecycle import Lifecycle
from scripts.single_tenant_live_ownership import RESOURCES
from tests.test_single_tenant_live_ledger import payload
from tests.test_single_tenant_live_ownership import IDS, resources
from tests.test_single_tenant_live_plan import creation, credentials


def state() -> dict[str, Any]:
    return {
        "resources": [
            {
                "type": address.split(".")[0],
                "name": "tenant",
                "mode": "managed",
                "provider": 'provider["registry.terraform.io/digitalocean/digitalocean"]',
                "instances": [{"attributes": value}],
            }
            for address, value in resources().items()
        ]
    }


def deletion(phase: str) -> dict[str, Any]:
    plan = creation()
    expected = (
        RESOURCES - {"digitalocean_project.tenant"}
        if phase == "services"
        else {"digitalocean_project.tenant"}
    )
    plan["resource_changes"] = [
        {
            "address": address,
            "change": {"actions": ["delete"], "before": {"id": IDS[address]}, "after": None},
        }
        for address in expected
    ]
    return plan


def setup() -> tuple[Lifecycle, Mock, Mock, Mock]:
    ownership, hcp, authority = Mock(), Mock(), Mock()
    ownership.create_workspace.return_value = "ws-Owned"
    ownership.workspace.return_value = {"id": "ws-Owned"}
    ownership.record.return_value = IDS
    ownership.owned.return_value = IDS
    ownership.do.return_value = {
        "app": {
            "active_deployment": {"phase": "ACTIVE"},
            "default_ingress": "hls-" + "a" * 28 + "-owned.ondigitalocean.app",
        }
    }
    hcp.configuration.return_value = "cv-Owned"
    hcp.plan.return_value = ("run-Owned", creation(2))
    hcp.state.return_value = state()
    lifecycle = Lifecycle(
        ownership=ownership,
        hcp=hcp,
        authority=authority,
        branch=Mock(),
        progress=Mock(),
        onion_check=Mock(),
    )
    return lifecycle, ownership, hcp, authority


def variables() -> dict[str, Any]:
    return {
        **credentials(),
        "APP_IMAGE_DIGEST": "sha256:" + "b" * 64,
        "ONION_HOSTNAME": "a" * 56 + ".onion",
        "single_tenant_admin_claim": "c" * 22,
    }


def test_payment_failure_precedes_any_cloud_creation() -> None:
    lifecycle, ownership, hcp, authority = setup()
    authority.side_effect = ValueError("Unpaid")
    with pytest.raises(ValueError, match="Unpaid"):
        lifecycle.provision(payload(), Path("hushline-single-tenant"), variables())
    ownership.create_workspace.assert_not_called()
    hcp.plan.assert_not_called()


def test_payment_revocation_after_plan_never_applies() -> None:
    lifecycle, _, hcp, authority = setup()
    authority.side_effect = [payload()["payment"], ValueError("Revoked")]
    with pytest.raises(ValueError, match="Revoked"):
        lifecycle.provision(payload(), Path("hushline-single-tenant"), variables())
    hcp.apply.assert_not_called()


def test_initializer_failure_preserves_created_resources_without_claim() -> None:
    lifecycle, ownership, hcp, _ = setup()
    ownership.do.return_value = {"app": {"active_deployment": {"phase": "ERROR"}}}
    with pytest.raises(ValueError, match="initializer"):
        lifecycle.provision(payload(), Path("hushline-single-tenant"), variables())
    hcp.apply.assert_called_once_with("run-Owned", "ws-Owned")
    ownership.remove_empty_workspace.assert_not_called()
    lifecycle.onion_check.assert_not_called()


def test_success_requires_owned_initializer_and_onion_check() -> None:
    lifecycle, _, _, authority = setup()
    result = lifecycle.provision(payload(), Path("hushline-single-tenant"), variables())
    assert result["state"] == "awaiting_dns"
    assert result["checks"] == {"infrastructure": True, "configuration": True}
    assert authority.call_count == 2
    lifecycle.onion_check.assert_called_once()


def test_remaining_service_prevents_project_plan_and_deletion() -> None:
    lifecycle, ownership, hcp, _ = setup()
    hcp.plan.return_value = ("run-Services", deletion("services"))
    ownership.verify_services_absent.side_effect = ValueError("Service remains")
    with pytest.raises(ValueError, match="remains"):
        lifecycle.retire(payload(), Path("hushline-single-tenant"), variables())
    assert hcp.plan.call_count == 1
    hcp.apply.assert_called_once_with("run-Services", "ws-Owned")
    ownership.remove_empty_workspace.assert_not_called()


def test_two_phase_retirement_checks_absence_and_empty_workspace() -> None:
    lifecycle, ownership, hcp, authority = setup()
    ownership.workspace.side_effect = [{"id": "ws-Owned"}, None]
    hcp.plan.side_effect = [
        ("run-Services", deletion("services")),
        ("run-Project", deletion("project")),
    ]
    result = lifecycle.retire(payload(), Path("hushline-single-tenant"), variables())
    assert result == {"state": "retired"}
    assert authority.call_count == 3
    assert hcp.apply.call_args_list[0].args == ("run-Services", "ws-Owned")
    assert hcp.apply.call_args_list[1].args == ("run-Project", "ws-Owned")
    assert ownership.verify_services_absent.call_count == 2
    ownership.verify_project_absent.assert_called_once()
    ownership.remove_empty_workspace.assert_called_once()

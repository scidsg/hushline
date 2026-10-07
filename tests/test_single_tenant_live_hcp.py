"""Check documented HCP request shapes and preserve policy and artifact boundaries."""

import io
import json
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from scripts.single_tenant_live_hcp import HCP


def run(
    *, workspace: str = "ws-Owned", confirmable: bool = True, status: str = "planned"
) -> dict[str, Any]:
    return {
        "data": {
            "id": "run-Owned",
            "attributes": {"status": status, "actions": {"is-confirmable": confirmable}},
            "relationships": {
                "workspace": {"data": {"id": workspace}},
                "plan": {"data": {"id": "plan-Owned"}},
            },
        }
    }


def test_configuration_never_uploads_adjacent_roots_or_auto_queues(tmp_path: Path) -> None:
    root = tmp_path / "hushline-single-tenant"
    root.mkdir()
    (root / "main.tf").write_text("# customer root")
    (root / ".terraform.lock.hcl").write_text("# signed lock")
    (tmp_path / "production.tf").write_text("# must never upload")
    request = Mock(
        return_value={
            "data": {
                "id": "cv-Owned",
                "attributes": {"upload-url": "https://archivist.terraform.io/owned"},
            }
        }
    )
    transfer = Mock(return_value=b"")
    adapter = HCP(request=request, transfer=transfer)
    assert adapter.configuration("ws-Owned", root, {"DO_TOKEN": "unit-only"}) == "cv-Owned"
    attrs = request.call_args.args[2]["data"]["attributes"]
    assert attrs == {"auto-queue-runs": False, "speculative": False}
    uploaded = transfer.call_args.kwargs["data"]
    with tarfile.open(fileobj=io.BytesIO(uploaded), mode="r:gz") as archive:
        assert set(archive.getnames()) == {
            "hushline-single-tenant/main.tf",
            "hushline-single-tenant/.terraform.lock.hcl",
            "hushline-single-tenant/customer.auto.tfvars.json",
        }


def test_saved_service_plan_has_only_three_exact_targets() -> None:
    calls = []

    def request(method: str, url: str, data: Any) -> dict[str, Any]:
        calls.append((method, url, data))
        if url.endswith("/json-output"):
            return {"location": "https://archivist.terraform.io/owned"}
        return run()

    adapter = HCP(
        request=request, transfer=lambda *args: json.dumps({"resource_changes": []}).encode()
    )
    identifier, plan = adapter.plan("ws-Owned", "cv-Owned", phase="services")
    assert identifier == "run-Owned"
    assert plan == {"resource_changes": []}
    attrs = calls[0][2]["data"]["attributes"]
    assert attrs["auto-apply"] is False
    assert attrs["is-destroy"] is True
    assert set(attrs["target-addrs"]) == {
        "digitalocean_app.tenant",
        "digitalocean_database_cluster.tenant",
        "digitalocean_database_firewall.tenant",
    }


@pytest.mark.parametrize(("workspace", "confirmable"), [("ws-Foreign", True), ("ws-Owned", False)])
def test_saved_run_cannot_apply_foreign_or_unconfirmed_plan(
    workspace: str, confirmable: bool
) -> None:
    request = Mock(return_value=run(workspace=workspace, confirmable=confirmable))
    adapter = HCP(request=request)
    with pytest.raises(ValueError, match="not eligible"):
        adapter.apply("run-Owned", "ws-Owned")
    assert request.call_count == 1
    assert request.call_args.args[0] == "GET"


def test_policy_failure_is_never_overridden() -> None:
    request = Mock(return_value=run(status="policy_override", confirmable=False))
    adapter = HCP(request=request)
    with pytest.raises(ValueError, match="stopped"):
        adapter.wait("run-Owned", {"planned"})
    assert request.call_count == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://archivist.terraform.io/object",
        "https://evil.foo/object",
        "https://archivist.terraform.io.evil.foo/object",
        "https://user@archivist.terraform.io/object",
    ],
)
def test_artifact_trust_roots_reject_credential_exfiltration(url: str) -> None:
    with pytest.raises(ValueError, match="escaped"):
        HCP.artifact(url)

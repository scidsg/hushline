"""Signed request validation excludes unrelated commits and fixture payments."""

from copy import deepcopy
from typing import Any

import pytest

from scripts.single_tenant_live_envelope import keys
from scripts.single_tenant_live_request import Request, commit
from tests.test_single_tenant_live_ledger import ORDER, payload


def pointer() -> dict[str, Any]:
    return {
        "order_id": ORDER,
        "purpose": "provision",
        "revision": 1,
        "config_ref": "c" * 40,
        "source_ref": "a" * 40,
        "infra_ref": "b" * 40,
    }


def request(data: dict[str, Any]) -> Request:
    return Request(
        data, branch=f"single-tenant-request/{ORDER}/provision-1", source="a" * 40, infra="b" * 40
    )


@pytest.mark.parametrize(
    ("field", "value"), [("revision", True), ("source_ref", "d" * 40), ("order_id", "e" * 32)]
)
def test_public_pointer_cannot_change_release_or_order(field: str, value: Any) -> None:
    data = pointer()
    data[field] = value
    with pytest.raises(ValueError, match="revision|reviewed release|another order"):
        request(data)


def test_fixture_payment_cannot_enter_general_live_workflow() -> None:
    data = payload()
    data.pop("state")
    data.pop("created_at")
    _, data["claim_public_key"] = keys()
    data["verification"] = "f" * 64
    assert request(pointer()).private(data) == data
    data["payment"]["payment_mode"] = "stripe_test"
    with pytest.raises(ValueError, match="live annual"):
        request(pointer()).private(data)


@pytest.mark.parametrize("change", ["unsigned", "author", "parent", "code", "modified"])
def test_signature_and_exact_single_added_file_are_required(change: str) -> None:
    data: dict[str, Any] = {
        "commit": {"verification": {"verified": True}},
        "committer": {"login": "hushline-dev"},
        "parents": [{"sha": "a" * 40}],
        "files": [{"filename": ".single-tenant-request.json", "status": "added"}],
    }
    commit(data, expected_parent="a" * 40, path=".single-tenant-request.json")
    modified = deepcopy(data)
    if change == "unsigned":
        modified["commit"]["verification"]["verified"] = False
    elif change == "author":
        modified["committer"]["login"] = "someone-else"
    elif change == "parent":
        modified["parents"][0]["sha"] = "b" * 40
    elif change == "code":
        modified["files"].append({"filename": "hushline/__init__.py", "status": "modified"})
    else:
        modified["files"][0]["status"] = "modified"
    with pytest.raises(ValueError, match="signed create-only"):
        commit(modified, expected_parent="a" * 40, path=".single-tenant-request.json")

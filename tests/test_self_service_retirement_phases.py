"""A partial destroy may finish only its recorded, genuinely empty project."""

import json
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from scripts import self_service_test_retirement as retirement
from tests.test_self_service_test_ownership import resources

ORDER = retirement.fixture.ORDER


def owned_resources() -> dict:
    data = resources()
    text = json.dumps(data).replace("a" * 32, ORDER).replace("a" * 27, ORDER[:27])
    data = json.loads(text)
    data[retirement.PROJECT_ADDRESS]["is_default"] = False
    return data


def identities() -> dict:
    return {address: value["id"] for address, value in owned_resources().items()}


def project_plan() -> dict:
    project = owned_resources()[retirement.PROJECT_ADDRESS]
    project["resources"] = []
    return {
        "resource_changes": [
            {
                "address": retirement.PROJECT_ADDRESS,
                "change": {"actions": ["delete"], "before": project},
            }
        ]
    }


def test_empty_recorded_project_can_finish_without_adopting_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = owned_resources()[retirement.PROJECT_ADDRESS]
    monkeypatch.setattr(
        retirement, "recorded", lambda order: (identities(), {retirement.PROJECT_ADDRESS: project})
    )

    def api(path: str) -> dict:
        if path.startswith("/projects/"):
            return {"project": project}
        raise urllib.error.HTTPError(path, 404, "absent", Message(), None)

    monkeypatch.setattr(retirement.ownership, "do", api)
    monkeypatch.setattr(retirement.ownership, "inventory", lambda path, key: [])
    assert retirement.remaining_project(ORDER) == identities()
    retirement.guard_project(project_plan(), ORDER, identities())


@pytest.mark.parametrize(
    "violation", ["wrong-id", "default", "members", "replace", "extra", "move"]
)
def test_project_plan_cannot_move_members_or_touch_other_projects(violation: str) -> None:
    data = project_plan()
    item = data["resource_changes"][0]
    if violation == "wrong-id":
        item["change"]["before"]["id"] = "other-project"
    elif violation == "default":
        item["change"]["before"]["is_default"] = True
    elif violation == "members":
        item["change"]["before"]["resources"] = ["do:app:already-deleted"]
    elif violation == "replace":
        item["change"]["actions"] = ["delete", "create"]
    elif violation == "move":
        item["previous_address"] = "digitalocean_project.production"
    else:
        data["resource_changes"].append({"address": "digitalocean_app.production"})
    with pytest.raises(ValueError, match="Remaining|phase|refresh"):
        retirement.guard_project(data, ORDER, identities())


def test_partial_app_or_database_is_not_silently_adopted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retirement, "recorded", lambda order: (identities(), owned_resources()))
    with pytest.raises(ValueError, match="exactly one remaining"):
        retirement.remaining_project(ORDER)


@pytest.mark.parametrize("status", [200, 403, 500])
def test_missing_resources_require_an_actual_404(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def api(path: str) -> dict:
        if status == 200:
            return {"app": {"id": "still-present"}}
        raise urllib.error.HTTPError(path, status, "not absent", Message(), None)

    monkeypatch.setattr(retirement.ownership, "do", api)
    with pytest.raises((ValueError, urllib.error.HTTPError), match="absent"):
        retirement.verify_absent("/apps/recorded-app")


def test_foreign_project_member_blocks_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    project = owned_resources()[retirement.PROJECT_ADDRESS]
    monkeypatch.setattr(
        retirement, "recorded", lambda order: (identities(), {retirement.PROJECT_ADDRESS: project})
    )
    monkeypatch.setattr(retirement, "verify_absent", lambda path: None)
    monkeypatch.setattr(retirement.ownership, "do", lambda path: {"project": project})
    monkeypatch.setattr(
        retirement.ownership, "inventory", lambda path, key: [{"urn": "do:app:other-instance"}]
    )
    with pytest.raises(ValueError, match="different ownership"):
        retirement.remaining_project(ORDER)


def service_plan() -> dict:
    return {
        "resource_changes": [
            {
                "address": address,
                "change": {
                    "actions": ["no-op"] if address == retirement.PROJECT_ADDRESS else ["delete"],
                    "before": value,
                },
            }
            for address, value in owned_resources().items()
        ]
    }


def test_service_phase_preserves_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retirement, "recorded", lambda order: (identities(), owned_resources()))
    retirement.guard_services(service_plan(), ORDER, identities())
    data = service_plan()
    project = next(
        item for item in data["resource_changes"] if item["address"] == retirement.PROJECT_ADDRESS
    )
    project["change"]["actions"] = ["delete"]
    with pytest.raises(ValueError, match="three recorded services"):
        retirement.guard_services(data, ORDER, identities())


def test_project_plan_is_fresh_and_separately_guarded() -> None:
    text = Path(".github/workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  retire:\n")[1].split("  inspect:\n")[0]
    assert "target: digitalocean_project.staging" in job
    assert "RETIREMENT_PHASE: services" in job
    assert "RETIREMENT_PHASE: project" in job
    assert "plan_services.outputs.plan_path" in job
    assert "plan_project.outputs.plan_path" in job
    assert "Confirm the recorded project is empty" in job
    assert "terraform state" not in job
    assert "assignResources" not in job

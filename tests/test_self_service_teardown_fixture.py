"""The one-time teardown test cannot adopt or overlap an existing instance."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import self_service_teardown_fixture as fixture
from scripts import self_service_test_retirement as retirement
from tests.test_self_service_test_request import isolated_plan
from tests.test_self_service_test_retirement import proof


def fixture_plan() -> dict:
    data = isolated_plan()
    data = json.loads(
        json.dumps(data).replace("a" * 32, fixture.ORDER).replace("a" * 27, fixture.ORDER[:27])
    )
    spec = data["resource_changes"][2]["change"]["after"]["spec"][0]
    spec["service"] = [
        {
            "git": [
                {
                    "branch": f"self-service-test/{fixture.ORDER}",
                    "repo_clone_url": "https://github.com/scidsg/hushline.git",
                }
            ]
        }
    ]
    return data


def test_authorized_fixture_has_no_custom_domain() -> None:
    from datetime import UTC, datetime

    data = proof()
    data.update(order_id=fixture.ORDER, custom_domain="")
    retirement.validate(data, datetime(2026, 1, 1, tzinfo=UTC))
    data["custom_domain"] = "hushline.foo"
    with pytest.raises(ValueError, match="restricted"):
        retirement.validate(data, datetime(2026, 1, 1, tzinfo=UTC))


def test_fixture_cannot_overlap_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixture.ownership, "owned", lambda order: {"app": "original-app"})
    with pytest.raises(ValueError, match="overlap"):
        fixture.isolated({"app": "original-app"})
    fixture.isolated({"app": "fresh-app"})


@pytest.mark.parametrize("violation", ["domain", "branch", "smtp", "existing-project"])
def test_fixture_plan_is_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, violation: str
) -> None:
    data = fixture_plan()
    app = data["resource_changes"][2]["change"]["after"]
    if violation == "domain":
        app["spec"][0]["domain"] = [{"name": "hushline.foo"}]
    elif violation == "branch":
        app["spec"][0]["service"][0]["git"][0]["branch"] = "main"
    elif violation == "smtp":
        app["spec"][0]["service"][0]["env"] = [{"key": "SMTP_PASSWORD"}]
    else:
        app["project_id"] = "original-project"
    monkeypatch.setenv("WORKSPACE_NAME", fixture.ownership.identity(fixture.ORDER)[0])
    check = Mock()
    monkeypatch.setattr(fixture, "check_original", check)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cannot|escaped"):
        fixture.guard_create(path)
    check.assert_not_called()


def test_original_change_blocks_fixture_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fixture, "SNAPSHOT", tmp_path / "snapshot.json")
    monkeypatch.setattr(fixture, "original_snapshot", lambda: {"state": "before"})
    fixture.preserve_original()
    monkeypatch.setattr(fixture, "original_snapshot", lambda: {"state": "after"})
    with pytest.raises(ValueError, match="original instance changed"):
        fixture.check_original()


def test_fixture_job_cannot_overwrite_or_destroy_during_creation() -> None:
    text = Path(".github/workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  fixture-create:\n")[1].split("  retire:\n")[0]
    assert "createRef" in job
    assert "updateRef" not in job
    assert "self-service-teardown-fixture" in job
    assert "guard_create" in job
    assert "destroy: true" not in job
    assert "fixture-status.json" in job

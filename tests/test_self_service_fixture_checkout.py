"""Only a paid, unexpired fresh fixture can trigger creation."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import self_service_fixture_checkout as checkout

CURRENT = datetime(2026, 10, 5, 1, tzinfo=UTC)


def payment() -> dict:
    end = CURRENT + timedelta(hours=2)
    return {
        "order_id": checkout.fixture.ORDER,
        "receipt": "b" * 32,
        "source": "fixture_checkout",
        "payment_mode": "simulated",
        "period_start": end.replace(year=end.year - 1).isoformat(),
        "period_end": end.isoformat(),
        "license_limit": 2,
    }


def test_valid_fixture_payment_has_full_annual_term() -> None:
    checkout.validate(payment(), CURRENT)


@pytest.mark.parametrize(
    "violation",
    ["old", "original", "source", "payment", "receipt", "short", "expired", "far", "bool", "extra"],
)
def test_payment_cannot_escape_test_scope(violation: str) -> None:
    data = payment()
    if violation == "old":
        data["order_id"] = checkout.fixture.RETIRED_ORDER
    elif violation == "original":
        data["order_id"] = checkout.ownership.RECOVERY_ORDER
    elif violation == "source":
        data["source"] = "simulated_checkout"
    elif violation == "payment":
        data["payment_mode"] = "paid"
    elif violation == "receipt":
        data["receipt"] = "missing"
    elif violation == "short":
        data["period_start"] = CURRENT.isoformat()
    elif violation in {"expired", "far"}:
        end = CURRENT + timedelta(hours=-1 if violation == "expired" else 30)
        data.update(
            period_start=end.replace(year=end.year - 1).isoformat(), period_end=end.isoformat()
        )
    elif violation == "bool":
        data["license_limit"] = True
    else:
        data["custom_domain"] = "hushline.foo"
    with pytest.raises(ValueError, match="Invalid|Fixture|fixture|license|Only"):
        checkout.validate(data, CURRENT)


def test_changed_payment_blocks_apply(tmp_path: Path) -> None:
    original, latest = tmp_path / "original.json", tmp_path / "latest.json"
    original.write_text(json.dumps(payment()))
    data = payment()
    data["receipt"] = "c" * 32
    latest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        checkout.unchanged(original, latest)


@pytest.mark.parametrize(
    "order", [checkout.fixture.RETIRED_ORDER, checkout.ownership.RECOVERY_ORDER]
)
def test_pointer_cannot_create_original_or_retired_fixture(tmp_path: Path, order: str) -> None:
    path = tmp_path / "pointer.json"
    path.write_text(json.dumps({"order_id": order, "config_ref": "a" * 40}))
    with pytest.raises(ValueError, match="Invalid|Fixture|fixture|license|Only"):
        checkout.pointer(path)


def test_empty_request_cannot_run_cloud_steps() -> None:
    text = Path("tests/fixtures/archived-workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  fixture-create:\n")[1].split("  retire:\n")[0]
    assert "self-service-teardown-fixture" not in job
    steps = job.split("      - name: ")[1:]
    steps = steps[
        next(
            i
            for i, step in enumerate(steps)
            if step.startswith("Check out the immutable private fixture payment")
        ) :
    ]
    assert all("if: steps.request.outputs.enabled == 'true'" in step for step in steps)
    assert "unchanged(" in job
    assert "healthy(" in job


def test_health_refuses_foreign_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "order_id": checkout.fixture.ORDER,
                "resources": {"digitalocean_app.staging": "fixture-app"},
            }
        )
    )
    monkeypatch.setattr(
        checkout.ownership, "owned", lambda order: {"digitalocean_app.staging": "fixture-app"}
    )
    monkeypatch.setattr(
        checkout.ownership, "do", lambda path: {"app": {"default_ingress": "https://hushline.foo"}}
    )
    opener = Mock()
    monkeypatch.setattr(checkout.urllib.request, "build_opener", opener)
    with pytest.raises(ValueError, match="owned provider"):
        checkout.healthy(path)
    opener.assert_not_called()


def test_retirement_cannot_shorten_the_original_fixture_checkout(tmp_path: Path) -> None:
    from scripts.self_service_test_retirement import checkout_matches

    paid = payment()
    orders = tmp_path / "lifecycle-orders"
    retirements = tmp_path / "retirements"
    orders.mkdir()
    retirements.mkdir()
    (orders / f"{checkout.fixture.ORDER}.json").write_text(json.dumps(paid))
    path = retirements / "proof.json"
    checkout_matches(path, paid)
    altered = dict(paid)
    altered["period_end"] = CURRENT.isoformat()
    with pytest.raises(ValueError, match="original checkout"):
        checkout_matches(path, altered)

"""Annual cancellation guards do not authorize early or unrelated destruction."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import self_service_test_retirement as retirement


def proof() -> dict:
    return {
        "order_id": retirement.ownership.RECOVERY_ORDER,
        "custom_domain": "hushline.foo",
        "receipt": "a" * 32,
        "payment_mode": "simulated",
        "period_start": "2024-02-29T12:00:00+00:00",
        "period_end": "2025-02-28T12:00:00+00:00",
        "cancelled_at": "2024-03-01T12:00:00+00:00",
    }


def test_annual_boundary() -> None:
    end = datetime(2025, 2, 28, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="not yet due"):
        retirement.validate(proof(), end - timedelta(seconds=1))
    retirement.validate(proof(), end)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("order_id", "b" * 32),
        ("custom_domain", "hushline.app"),
        ("receipt", "bad"),
        ("payment_mode", "paid"),
        ("period_end", "2024-03-01T12:00:00+00:00"),
        ("period_start", "2024-02-29T12:00:00"),
        ("cancelled_at", "2025-03-01T12:00:00+00:00"),
    ],
)
def test_invalid_authority(field: str, value: str) -> None:
    data = proof()
    data[field] = value
    with pytest.raises(ValueError, match="UTC|restricted|receipt|period|Cancellation"):
        retirement.validate(data, datetime(2026, 1, 1, tzinfo=UTC))


def test_changed_cancellation_blocks_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = tmp_path / "original.json"
    latest = tmp_path / "latest.json"
    original.write_text(json.dumps(proof()))
    changed = proof()
    changed["cancelled_at"] = None
    latest.write_text(json.dumps(changed))
    owned = Mock()
    monkeypatch.setattr(retirement.ownership, "owned", owned)
    with pytest.raises(ValueError, match="changed after planning"):
        retirement.guard(original, latest, tmp_path / "plan.json")
    owned.assert_not_called()


def test_absent_pointer_disables_all_cloud_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    emit = Mock()
    monkeypatch.setattr(retirement, "emit", emit)
    retirement.pointer(tmp_path / "absent")
    emit.assert_called_once_with("enabled", "false")


def test_retirement_workflow_has_independent_guards() -> None:
    text = Path("tests/fixtures/archived-workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  retire:\n")[1].split("  inspect:\n")[0]
    assert "number == 2447" in job
    assert "environment: self-service-test-2447" in job
    assert "self_service_test_retirement.py prepare" in job
    assert "self_service_test_retirement.py guard" in job
    assert "current-services-cancellation" in job
    assert "current-project-cancellation" in job
    assert "plan_path: ${{ steps.plan_services.outputs.plan_path }}" in job
    assert "plan_path: ${{ steps.plan_project.outputs.plan_path }}" in job
    assert "Confirm the recorded project is empty" in job
    assert "Verify all recorded resources are absent" in job
    assert "admin-claim" not in job
    assert "auto_approve: true" in job
    assert "self_service_test_ownership.py remove" in job


def test_explicit_sandbox_retirement_preserves_term_and_verifies_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import self_service_stripe_payment as payment
    from tests.test_self_service_stripe_payment import evidence

    data, session = evidence()
    order = payment.EXPLICIT_RETIREMENT_ORDER
    data.update(
        order_id=order,
        custom_domain="hushline.foo",
        payment_mode="stripe_test",
        receipt=data["stripe_payment"]["receipt"],
        period_start=data["stripe_payment"]["period_start"],
        period_end=data["stripe_payment"]["period_end"],
        cancelled_at=None,
        explicit_sandbox_retirement={
            "reason": "owner-authorized-permanent-sandbox-deletion",
            "authorized_at": datetime.now(UTC).isoformat(),
        },
    )
    session["metadata"]["single_tenant_order"] = order
    session["subscription"]["metadata"]["single_tenant_order"] = order
    monkeypatch.setattr(payment, "retrieve", lambda _: session)
    retirement.validate(data, datetime.now(UTC))
    session["livemode"] = True
    with pytest.raises(ValueError, match="exact owned annual payment"):
        retirement.validate(data, datetime.now(UTC))
    session["livemode"] = False
    del data["explicit_sandbox_retirement"]
    data["cancelled_at"] = datetime.now(UTC).isoformat()
    with pytest.raises(ValueError, match="not yet due"):
        retirement.validate(data, datetime.now(UTC))

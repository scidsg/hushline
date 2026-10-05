"""CI independently rejects unpaid, live, replayed and changed sandbox receipts."""

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import self_service_stripe_payment as payment


def evidence() -> tuple[dict, dict]:
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    end = start.replace(year=start.year + 1)
    metadata = {"single_tenant_receipt": "a" * 32, "single_tenant_order": "b" * 32}
    components = [128280, 48000, 17628, 17628, 17628]
    data = {
        "order_id": "b" * 32,
        "license_limit": 2,
        "stripe_payment": {
            "receipt": "a" * 32,
            "session_id": "cs_test_one",
            "subscription_id": "sub_test_one",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
        },
    }
    session = {
        "id": "cs_test_one",
        "livemode": False,
        "payment_status": "paid",
        "status": "complete",
        "mode": "subscription",
        "client_reference_id": "a" * 32,
        "metadata": metadata,
        "currency": "usd",
        "amount_total": 229164,
        "customer": "cus_test_one",
        "subscription": {
            "id": "sub_test_one",
            "livemode": False,
            "status": "active",
            "metadata": metadata,
            "customer": "cus_test_one",
            "current_period_start": int(start.timestamp()),
            "current_period_end": int(end.timestamp()),
            "items": {
                "data": [
                    {
                        "quantity": 1,
                        "price": {
                            "unit_amount": c,
                            "currency": "usd",
                            "recurring": {"interval": "year", "interval_count": 1},
                        },
                    }
                    for c in components
                ]
            },
            "latest_invoice": {
                "status": "paid",
                "livemode": False,
                "amount_paid": 229164,
                "currency": "usd",
                "subscription": "sub_test_one",
                "customer": "cus_test_one",
                "lines": {
                    "data": [
                        {
                            "proration": False,
                            "period": {
                                "start": int(start.timestamp()),
                                "end": int(end.timestamp()),
                            },
                        }
                        for _ in components
                    ]
                },
            },
        },
    }
    return data, session


def test_expected_paid_annual_checkout_is_accepted() -> None:
    data, session = evidence()
    payment.validate(data, session)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("livemode", True),
        ("payment_status", "unpaid"),
        ("amount_total", 1),
        ("currency", "eur"),
        ("id", "cs_test_other"),
        ("client_reference_id", "c" * 32),
    ],
)
def test_changed_payment_is_rejected(field: str, value: object) -> None:
    data, session = evidence()
    session[field] = value
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, session)


def test_payment_cannot_be_reused_for_a_different_order() -> None:
    data, session = evidence()
    data["order_id"] = "c" * 32
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, session)


@pytest.mark.parametrize("order", sorted(payment.PROTECTED_ORDERS))
def test_retired_order_is_rejected_before_stripe_or_cloud_access(order: str) -> None:
    data, _ = evidence()
    data["order_id"] = order
    with patch.object(payment, "retrieve") as request:
        with pytest.raises(ValueError, match="retired protected"):
            payment.verify(data)
        request.assert_not_called()


def test_proof_dates_cannot_be_changed_to_force_retirement() -> None:
    data, session = evidence()
    data["stripe_payment"]["period_end"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, session, retiring=True)


def test_subscription_must_be_cancelled_and_expired_before_retirement() -> None:
    data, session = evidence()
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, session, retiring=True)
    with patch.object(payment, "datetime") as clock:
        clock.fromtimestamp = datetime.fromtimestamp
        clock.now.return_value = datetime.fromisoformat(
            data["stripe_payment"]["period_end"]
        ) + timedelta(seconds=1)
        with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
            payment.validate(data, session, retiring=True)
        session["subscription"]["cancel_at_period_end"] = True
        payment.validate(data, session, retiring=True)


def test_live_key_is_rejected_before_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_TEST_SECRET_KEY", "sk_live_fake")
    with patch.object(payment.urllib.request, "build_opener") as request:
        with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
            payment.retrieve("cs_test_valid")
        request.assert_not_called()


def test_invoice_period_and_price_components_are_verified() -> None:
    data, session = evidence()
    bad = copy.deepcopy(session)
    bad["subscription"]["latest_invoice"]["lines"]["data"][0]["period"]["end"] -= 1
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, bad)
    bad = copy.deepcopy(session)
    bad["subscription"]["items"]["data"][0]["price"]["recurring"]["interval"] = "month"
    with pytest.raises(ValueError, match="Stripe|sandbox|annual|subscription|invoice"):
        payment.validate(data, bad)


def test_stripe_workflow_has_paid_gate_and_unchanged_order_before_apply() -> None:
    text = Path(".github/workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  stripe-deploy:\n")[1].split("  finalize:\n")[0]
    assert "number == 2447" in job
    assert "environment: self-service-test-2447" in job
    assert "diff --quiet HEAD^ HEAD -- .self-service-stripe.json" in job
    assert job.index("verify(json.loads") < job.index("Create a new order-owned workspace")
    assert job.index("unchanged(Path") < job.index("Apply isolated staging infrastructure")
    assert "plan_path: ${{ steps.plan.outputs.plan_path }}" in job
    assert "current-stripe-order" in job
    assert "Install Tor" in job

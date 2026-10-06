"""Live annual billing is independently account-bound and never replaces Super User."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from flask.ctx import AppContext
from pytest_mock import MockFixture

from hushline.model import SingleTenantOrder
from hushline.single_tenant_billing import annual_end, metadata, prices, verified_year


def evidence() -> tuple[SingleTenantOrder, dict]:
    order = SingleTenantOrder(id="a" * 32, user_id=1, owner_ref="b" * 64)
    order.license_limit = 2
    order.billing_receipt = "c" * 32
    order.stripe_session_id = "cs_live_owned"
    order.stripe_subscription_id = None
    order.stripe_customer_id = None
    order.period_start = None
    start = datetime(2026, 10, 6, tzinfo=UTC)
    end = annual_end(start)
    components = prices(2)
    session = {
        "id": order.stripe_session_id,
        "livemode": True,
        "status": "complete",
        "payment_status": "paid",
        "mode": "subscription",
        "currency": "usd",
        "amount_total": 229164,
        "client_reference_id": order.billing_receipt,
        "metadata": metadata(order),
        "customer": "cus_owned",
        "subscription": {
            "id": "sub_owned",
            "customer": "cus_owned",
            "livemode": True,
            "status": "active",
            "metadata": metadata(order),
            "current_period_start": int(start.timestamp()),
            "current_period_end": int(end.timestamp()),
            "items": {
                "data": [
                    {
                        "quantity": 1,
                        "price": {
                            "currency": "usd",
                            "unit_amount": value,
                            "recurring": {"interval": "year", "interval_count": 1},
                        },
                    }
                    for _, value in components
                ]
            },
            "latest_invoice": {
                "livemode": True,
                "status": "paid",
                "currency": "usd",
                "amount_paid": 229164,
                "customer": "cus_owned",
                "subscription": "sub_owned",
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
    return order, session


def test_owned_complete_live_annual_payment_is_accepted() -> None:
    order, session = evidence()
    now = datetime(2026, 10, 6, 1, tzinfo=UTC)
    result = verified_year(order, session, live=True, now=now)
    assert result.customer == "cus_owned"
    assert result.subscription == "sub_owned"
    assert result.end == annual_end(result.start)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("livemode", False),
        ("payment_status", "unpaid"),
        ("amount_total", 1),
        ("customer", "cus_foreign"),
        ("id", "cs_live_foreign"),
    ],
)
def test_unpaid_sandbox_and_foreign_checkout_cannot_authorize_live_resources(
    field: str, value: object
) -> None:
    order, session = evidence()
    session[field] = value
    with pytest.raises(ValueError, match="annual payment"):
        verified_year(order, session, live=True, now=datetime(2026, 10, 6, 1, tzinfo=UTC))


@pytest.mark.parametrize("target", ["metadata", "subscription"])
def test_paid_receipt_cannot_be_adopted_by_another_account(target: str) -> None:
    order, session = evidence()
    values = session["metadata"] if target == "metadata" else session["subscription"]["metadata"]
    values["single_tenant_owner"] = "d" * 64
    with pytest.raises(ValueError, match="account"):
        verified_year(order, session, live=True, now=datetime(2026, 10, 6, 1, tzinfo=UTC))


def test_every_component_must_cover_the_same_full_year() -> None:
    order, session = evidence()
    session["subscription"]["latest_invoice"]["lines"]["data"][0]["period"]["end"] -= 1
    with pytest.raises(ValueError, match="Every paid component"):
        verified_year(order, session, live=True, now=datetime(2026, 10, 6, 1, tzinfo=UTC))


def test_future_and_expired_payment_cannot_authorize_creation() -> None:
    order, session = evidence()
    for current in [datetime(2026, 10, 5, tzinfo=UTC), datetime(2027, 10, 6, tzinfo=UTC)]:
        with pytest.raises(ValueError, match="current complete"):
            verified_year(order, session, live=True, now=current)


def test_old_invoice_cannot_roll_back_the_paid_year() -> None:
    order, session = evidence()
    order.period_start = (datetime(2026, 10, 6, tzinfo=UTC) + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="older payment"):
        verified_year(order, session, live=True, now=datetime(2026, 10, 6, 1, tzinfo=UTC))


def test_unlimited_and_numbered_prices_include_all_charges() -> None:
    assert sum(v for _, v in prices(None)) == 2766764
    assert sum(v for _, v in prices(25)) == 946764
    assert annual_end(datetime(2024, 2, 29, tzinfo=UTC)) == datetime(2025, 2, 28, tzinfo=UTC)


def live_context() -> AppContext:
    from flask import Flask

    app = Flask(__name__)
    app.config.update(
        STRIPE_SECRET_KEY="sk_live_unit_test_only",  # noqa: S106 — fake key; API is mocked
        SINGLE_TENANT_TEST_MODE=False,
        SINGLE_TENANT_ACCEPT_PAYMENTS=True,
        PUBLIC_BASE_URL="https://portal.example.org",
    )
    return app.app_context()


@pytest.fixture()
def app_context() -> Generator[AppContext, None, None]:
    with live_context() as context:
        yield context


def test_live_client_reuses_existing_app_configuration_without_mutating_it(
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_billing import client

    constructor = mocker.patch("hushline.single_tenant_billing.stripe.StripeClient")
    with live_context():
        client()
    assert constructor.call_args.args == ("sk_live_unit_test_only",)
    assert constructor.call_args.kwargs == {"stripe_version": "2024-06-20"}


def test_pausing_new_sales_never_opens_live_checkout(mocker: MockFixture) -> None:
    from flask import current_app

    from hushline.single_tenant_billing import checkout
    from hushline.single_tenant_client import ServiceUnavailable

    order, _ = evidence()
    api = mocker.patch("hushline.single_tenant_billing.client")
    with live_context():
        current_app.config["SINGLE_TENANT_ACCEPT_PAYMENTS"] = False
        with pytest.raises(ServiceUnavailable, match="temporarily unavailable"):
            checkout(order)
    api.assert_not_called()


def test_checkout_reuses_the_same_reservation_and_does_not_adopt_super_user_customer(
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_billing import checkout

    order, _ = evidence()
    order.billing_receipt = None
    order.stripe_session_id = None
    order.paid = False
    api = mocker.Mock()
    reply = {
        "id": "cs_live_owned",
        "url": "https://checkout.stripe.com/c/pay/owned",
        "livemode": True,
        "status": "open",
    }
    api.checkout.sessions.create.return_value = reply
    api.checkout.sessions.retrieve.return_value = reply
    mocker.patch("hushline.single_tenant_billing.client", return_value=api)
    database = mocker.patch("hushline.single_tenant_billing.db.session")
    database.scalar.return_value = order
    with live_context():
        first = checkout(order)
        second = checkout(order)
    assert first == second
    assert api.checkout.sessions.create.call_count == 1
    request = api.checkout.sessions.create.call_args.args[0]
    assert "customer" not in request
    assert request["metadata"]["single_tenant_owner"] == order.owner_ref
    assert request["subscription_data"]["metadata"] == request["metadata"]
    assert sum(item["price_data"]["unit_amount"] for item in request["line_items"]) == 229164
    assert request["allow_promotion_codes"] is False
    assert api.checkout.sessions.create.call_args.kwargs["options"]["idempotency_key"].endswith(
        order.billing_receipt
    )


def test_foreign_subscription_cannot_be_cancelled(mocker: MockFixture) -> None:
    from hushline.single_tenant_billing import cancel
    from hushline.single_tenant_client import ServiceUnavailable

    order, session = evidence()
    order.paid = True
    order.stripe_subscription_id = "sub_owned"
    order.stripe_customer_id = "cus_owned"
    order.period_end = datetime(2027, 10, 6, tzinfo=UTC).isoformat()
    session["subscription"]["metadata"]["single_tenant_owner"] = "d" * 64
    api = mocker.Mock()
    api.subscriptions.retrieve.return_value = session["subscription"]
    mocker.patch("hushline.single_tenant_billing.client", return_value=api)
    with live_context(), pytest.raises(ServiceUnavailable, match="renewal change"):
        cancel(order, True)
    api.subscriptions.update.assert_not_called()


def test_unknown_single_tenant_event_does_not_enter_super_user_processing(
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_billing import handle_event

    mocker.patch("hushline.single_tenant_billing.db.session.get", return_value=None)
    event = {
        "livemode": True,
        "data": {
            "object": {
                "metadata": {
                    "single_tenant_kind": "paid-instance",
                    "single_tenant_order": "a" * 32,
                }
            }
        },
    }
    with live_context():
        assert handle_event(event)


@pytest.mark.parametrize(
    "capability",
    [
        {
            "payment_mode": "stripe_test",
            "namespace": "hushline-single-tenant",
            "lifecycle_protocol": 1,
            "accepts_payments": True,
        },
        {
            "payment_mode": "stripe_live",
            "namespace": "production",
            "lifecycle_protocol": 1,
            "accepts_payments": True,
        },
        {
            "payment_mode": "stripe_live",
            "namespace": "hushline-single-tenant",
            "lifecycle_protocol": 1,
            "accepts_payments": False,
        },
        {},
    ],
)
def test_unready_lifecycle_service_cannot_charge_customer(
    app_context: AppContext, mocker: MockFixture, capability: dict
) -> None:
    from flask import current_app

    from hushline.single_tenant_client import ServiceUnavailable, call

    order, _ = evidence()
    current_app.config["SINGLE_TENANT_TEST_MODE"] = False
    mocker.patch("hushline.single_tenant_client._remote_call", return_value=capability)
    charge = mocker.patch("hushline.single_tenant_billing.checkout")
    with pytest.raises(ServiceUnavailable):
        call(order, "checkout")
    charge.assert_not_called()


def test_delayed_broker_cannot_erase_verified_annual_payment(
    app_context: AppContext, mocker: MockFixture
) -> None:
    from flask import current_app

    from hushline.single_tenant_client import call

    order, _ = evidence()
    order.paid = True
    order.period_end = "2027-10-06T00:00:00+00:00"
    order.cancelled_at = "2026-10-06T01:00:00+00:00"
    current_app.config["SINGLE_TENANT_TEST_MODE"] = False
    mocker.patch(
        "hushline.single_tenant_client._remote_call",
        return_value={
            "order_id": order.id,
            "owner": order.owner_ref,
            "paid": False,
            "term": {"period_end": "2026-10-06T00:00:00+00:00", "cancelled_at": None},
        },
    )
    result = call(order, "status")
    assert result["paid"] is True
    assert result["term"]["period_end"] == order.period_end
    assert result["term"]["cancelled_at"] == order.cancelled_at


def test_payment_racing_account_deletion_keeps_cancellation_lock(mocker: MockFixture) -> None:
    from hushline.single_tenant_billing import cancel

    order, session = evidence()
    order.paid = False
    order.cancellation_pending = True
    order.cancelled = True
    api = mocker.Mock()
    api.checkout.sessions.retrieve.return_value = session
    api.subscriptions.retrieve.return_value = session["subscription"]
    updated = dict(session["subscription"], cancel_at_period_end=True)
    api.subscriptions.update.return_value = updated
    mocker.patch("hushline.single_tenant_billing.client", return_value=api)
    database = mocker.patch("hushline.single_tenant_billing.db.session")
    with live_context():
        result = cancel(order, True)
    assert result["cancelled"] is True
    assert order.paid
    assert order.cancellation_pending
    assert order.cancelled
    database.commit.assert_not_called()
    api.subscriptions.update.assert_called_once_with("sub_owned", {"cancel_at_period_end": True})


def test_account_deletion_between_reservation_and_checkout_prevents_charge(
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_billing import checkout
    from hushline.single_tenant_client import ServiceUnavailable

    order, _ = evidence()
    order.billing_receipt = None
    order.stripe_session_id = None
    order.paid = False
    deleted, _ = evidence()
    deleted.user_id = None
    deleted.cancellation_pending = True
    api = mocker.patch("hushline.single_tenant_billing.client")
    database = mocker.patch("hushline.single_tenant_billing.db.session")
    database.scalar.side_effect = [order, deleted]
    with live_context(), pytest.raises(ServiceUnavailable, match="no longer available"):
        checkout(order)
    api.return_value.checkout.sessions.create.assert_not_called()


def test_missed_checkout_return_recovers_same_payment_without_provisioning(
    app_context: AppContext,
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_client import call

    order, _ = evidence()
    order.stage = "payment"
    order.paid = False
    remote = mocker.patch("hushline.single_tenant_client._remote_call")

    def paid(*args: object) -> dict:
        order.paid = True
        return {"paid": True}

    confirmation = mocker.patch("hushline.single_tenant_billing.confirm", side_effect=paid)
    result = call(order, "status")
    assert result["paid"] is True
    confirmation.assert_called_once_with(order, "cs_live_owned")
    remote.assert_not_called()


def test_unprovisioned_paid_order_can_cancel_without_a_broker_instance(
    app_context: AppContext,
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_client import call

    order, _ = evidence()
    order.stage = "domain"
    order.paid = True
    remote = mocker.patch("hushline.single_tenant_client._remote_call")
    cancellation = mocker.patch(
        "hushline.single_tenant_billing.cancel", return_value={"cancelled": True}
    )
    assert call(order, "cancel", cancelled=True)["cancelled"] is True
    cancellation.assert_called_once_with(order, True)
    remote.assert_not_called()


def test_invoice_without_checkout_metadata_is_routed_by_owned_subscription(
    app_context: AppContext,
    mocker: MockFixture,
) -> None:
    from hushline.single_tenant_billing import handle_event

    order, _ = evidence()
    database = mocker.patch("hushline.single_tenant_billing.db.session")
    database.scalar.return_value = order
    confirmation = mocker.patch("hushline.single_tenant_billing.confirm")
    assert handle_event(
        {
            "livemode": True,
            "type": "invoice.paid",
            "data": {"object": {"subscription": "sub_owned", "metadata": {}}},
        }
    )
    confirmation.assert_called_once_with(order, "cs_live_owned")


def test_paid_renewal_extends_by_one_calendar_year_without_recreating_order() -> None:
    order, session = evidence()
    start = datetime(2027, 10, 6, tzinfo=UTC)
    end = annual_end(start)
    order.period_start = datetime(2026, 10, 6, tzinfo=UTC).isoformat()
    subscription = session["subscription"]
    subscription["current_period_start"] = int(start.timestamp())
    subscription["current_period_end"] = int(end.timestamp())
    for line in subscription["latest_invoice"]["lines"]["data"]:
        line["period"] = {"start": int(start.timestamp()), "end": int(end.timestamp())}
    result = verified_year(order, session, live=True, now=start + timedelta(seconds=1))
    assert result.start == start
    assert result.end == end
    assert result.subscription == "sub_owned"
    assert order.id == "a" * 32


def test_failed_renewal_does_not_authorize_an_unpaid_year() -> None:
    order, session = evidence()
    session["subscription"]["latest_invoice"]["status"] = "open"
    session["subscription"]["latest_invoice"]["amount_paid"] = 0
    with pytest.raises(ValueError, match="annual payment"):
        verified_year(order, session, live=True, now=datetime(2026, 10, 6, 1, tzinfo=UTC))

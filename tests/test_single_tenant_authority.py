"""Paid workflow authority is fresh, replay-protected and confined to its owner."""

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import SingleTenantOrder, User
from hushline.single_tenant_authority import PATH, authenticate, authorize, consume_nonce
from hushline.single_tenant_billing import verified_year
from tests.test_single_tenant_billing import evidence, live_context

KEY = bytes.fromhex("a" * 64)
EPOCH = 1791280800


def headers(body: bytes, *, timestamp: int = EPOCH, nonce: str = "d" * 32) -> dict[str, str]:
    digest = hashlib.sha256(body).hexdigest()
    signed = f"POST\n{PATH}\n{timestamp}\n{nonce}\n{digest}".encode()
    return {
        "X-Hushline-Timestamp": str(timestamp),
        "X-Hushline-Nonce": nonce,
        "X-Hushline-Signature": hmac.new(KEY, signed, hashlib.sha256).hexdigest(),
    }


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def configure(mocker: MockFixture) -> None:
        mocker.patch.dict(
            os.environ,
            {
                "SINGLE_TENANT_ENABLED": "true",
                "SINGLE_TENANT_TEST_MODE": "false",
                "SINGLE_TENANT_SERVICE_URL": "https://broker.example.org",
                "SINGLE_TENANT_SERVICE_KEY": "a" * 64,
            },
        )

    return configure


def test_signature_is_bound_to_exact_body_and_time() -> None:
    body = b'{"purpose":"provision"}'
    assert authenticate(body, headers(body), KEY, EPOCH) == "d" * 32
    with pytest.raises(ValueError, match="authentication failed"):
        authenticate(body + b" ", headers(body), KEY, EPOCH)
    with pytest.raises(ValueError, match="authentication failed"):
        authenticate(body, headers(body), KEY, EPOCH + 301)
    with pytest.raises(ValueError, match="authentication failed"):
        authenticate(body, headers(body), b"x" * 32, EPOCH)


def test_replay_is_rejected_after_transaction_commit(app: Flask) -> None:
    with app.app_context():
        consume_nonce("d" * 32, EPOCH)
        with pytest.raises(ValueError, match="already consumed"):
            consume_nonce("d" * 32, EPOCH)


def test_unsigned_request_never_queries_stripe(client: FlaskClient, mocker: MockFixture) -> None:
    api = mocker.patch("hushline.single_tenant_billing.client")
    response = client.post(
        PATH, json={"order_id": "a" * 32, "owner": "b" * 64, "purpose": "retire"}
    )
    assert response.status_code == 409
    assert response.headers["Cache-Control"] == "no-store"
    api.assert_not_called()


def test_wrong_owner_cannot_obtain_payment_evidence(
    client: FlaskClient,
    user: User,
    mocker: MockFixture,
) -> None:
    import time

    order = SingleTenantOrder(id="a" * 32, user_id=user.id, owner_ref="b" * 64)
    db.session.add(order)
    db.session.commit()
    body = json.dumps({"order_id": order.id, "owner": "c" * 64, "purpose": "provision"}).encode()
    api = mocker.patch("hushline.single_tenant_billing.client")
    response = client.post(PATH, data=body, headers=headers(body, timestamp=int(time.time())))
    assert response.status_code == 409
    api.assert_not_called()
    assert "receipt" not in response.get_data(as_text=True)


def paid_order() -> tuple[SingleTenantOrder, dict]:
    order, session = evidence()
    order.paid = True
    order.stripe_subscription_id = "sub_owned"
    order.stripe_customer_id = "cus_owned"
    order.stripe_invoice_id = "in_owned"
    order.period_start = datetime(2026, 10, 6, tzinfo=UTC).isoformat()
    order.period_end = datetime(2027, 10, 6, tzinfo=UTC).isoformat()
    order.stage = "ready"
    order.service_state = "ready"
    order.cancellation_pending = False
    order.cancelled = True
    order.cancelled_at = datetime(2026, 10, 6, 1, tzinfo=UTC).isoformat()
    return order, session


def test_fresh_provision_authority_preserves_order_and_license_allowance(
    mocker: MockFixture,
) -> None:
    order, session = paid_order()
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    with live_context():
        result = authorize(order, "provision", datetime(2026, 10, 6, 2, tzinfo=UTC))
    assert result["authorized"] == "provision"
    assert result["payment"]["license_limit"] == 2
    assert result["order_id"] == order.id


@pytest.mark.parametrize("hours_before", [1, 24, 8760])
def test_retirement_cannot_run_before_the_unmodified_paid_deadline(
    mocker: MockFixture,
    hours_before: int,
) -> None:
    order, session = paid_order()
    session["subscription"]["status"] = "canceled"
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    assert order.period_end is not None
    end = datetime.fromisoformat(order.period_end)
    with live_context(), pytest.raises(ValueError, match="unchanged expired"):
        authorize(order, "retire", end - timedelta(hours=hours_before))


def test_retirement_requires_terminal_owned_subscription_at_actual_expiry(
    mocker: MockFixture,
) -> None:
    order, session = paid_order()
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    assert order.period_end is not None
    end = datetime.fromisoformat(order.period_end)
    with live_context(), pytest.raises(ValueError, match="terminal cancellation"):
        authorize(order, "retire", end)
    session["subscription"]["status"] = "canceled"
    with live_context():
        result = authorize(order, "retire", end)
    assert result["authorized"] == "retire"
    assert result["payment"]["period_end"] == end.isoformat()
    with pytest.raises(ValueError, match="annual payment"):
        verified_year(order, session, live=True, now=end - timedelta(seconds=1))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", None),
        ("service_state", "retired"),
        ("paid", False),
    ],
)
def test_deleted_account_and_retired_order_cannot_authorize_provisioning(
    mocker: MockFixture,
    field: str,
    value: object,
) -> None:
    order, session = paid_order()
    setattr(order, field, value)
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    with live_context(), pytest.raises(ValueError, match="required"):
        authorize(order, "provision", datetime(2026, 10, 6, 2, tzinfo=UTC))


def test_pending_withdrawal_prevents_retirement(mocker: MockFixture) -> None:
    order, session = paid_order()
    order.cancellation_pending = True
    session["subscription"]["status"] = "canceled"
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    with live_context(), pytest.raises(ValueError, match="terminal cancellation"):
        authorize(order, "retire", datetime(2027, 10, 6, tzinfo=UTC))


def test_authority_is_explicit_private_json_never_html(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    import time

    order = SingleTenantOrder(id="a" * 32, user_id=user.id, owner_ref="b" * 64)
    db.session.add(order)
    db.session.commit()
    body = json.dumps(
        {"order_id": order.id, "owner": order.owner_ref, "purpose": "provision"}
    ).encode()
    payload = {"order_id": order.id, "owner": order.owner_ref, "value": "<script>alert(1)</script>"}
    mocker.patch("hushline.single_tenant_authority.authorize", return_value=payload)
    response = client.post(PATH, data=body, headers=headers(body, timestamp=int(time.time())))
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json() == payload


def test_failed_later_renewal_does_not_hide_the_owned_paid_invoice(mocker: MockFixture) -> None:
    order, session = paid_order()
    invoice = deepcopy(session["subscription"]["latest_invoice"])
    subscription = session["subscription"]
    subscription["status"] = "canceled"
    subscription["current_period_start"] = int(datetime(2027, 10, 6, tzinfo=UTC).timestamp())
    subscription["current_period_end"] = int(datetime(2028, 10, 6, tzinfo=UTC).timestamp())
    subscription["latest_invoice"] = {"id": "in_unpaid", "status": "open", "amount_paid": 0}
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = invoice
    with live_context():
        result = authorize(order, "retire", datetime(2027, 10, 7, tzinfo=UTC))
    api.invoices.retrieve.assert_called_once_with("in_owned", {"expand": ["discounts"]})
    assert result["payment"]["invoice_id"] == "in_owned"
    assert result["payment"]["period_end"] == order.period_end
    assert result["payment"]["period_end"] == "2027-10-06T00:00:00+00:00"


def test_retirement_rejects_a_different_historical_invoice(mocker: MockFixture) -> None:
    order, session = paid_order()
    session["subscription"]["status"] = "canceled"
    invoice = deepcopy(session["subscription"]["latest_invoice"])
    invoice["id"] = "in_another"
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = invoice
    with live_context(), pytest.raises(ValueError, match="annual payment"):
        authorize(order, "retire", datetime(2027, 10, 7, tzinfo=UTC))


def test_historical_paid_invoice_cannot_authorize_an_unpaid_current_year(
    mocker: MockFixture,
) -> None:
    order, session = paid_order()
    session["subscription"]["status"] = "active"
    session["subscription"]["latest_invoice"]["status"] = "open"
    session["subscription"]["latest_invoice"]["amount_paid"] = 0
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    with live_context(), pytest.raises(ValueError, match="annual payment"):
        authorize(order, "provision", datetime(2027, 10, 7, tzinfo=UTC))
    api.invoices.retrieve.assert_not_called()


def test_explicit_early_destruction_requires_confirmed_terminal_stripe_state(
    mocker: MockFixture,
) -> None:
    order, session = paid_order()
    now = datetime(2026, 10, 6, 2, tzinfo=UTC)
    order.destroy_requested_at = now.isoformat()
    api = mocker.patch("hushline.single_tenant_billing.client").return_value
    api.checkout.sessions.retrieve.return_value = session
    api.invoices.retrieve.return_value = session["subscription"]["latest_invoice"]
    with live_context(), pytest.raises(ValueError, match="terminal cancellation"):
        authorize(order, "retire", now)
    session["subscription"]["status"] = "canceled"
    with live_context():
        result = authorize(order, "retire", now)
    assert result["destroy_requested_at"] == now.isoformat()
    assert result["payment"]["period_end"] == order.period_end

"""Independently verify a sandbox annual payment before any test infrastructure write."""

from __future__ import annotations

import calendar
import json
import os
import re
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

API_VERSION = "2024-06-20"
EXPLICIT_RETIREMENT_LICENSES = 2
EXPLICIT_RETIREMENT_ORDER = "d9096a7ac4a4a90198550588df08fdcd"


def explicit_retirement(data: dict) -> bool:
    """One owner-authorized sandbox deletion; never an annual expiry override."""
    authorization = data.get("explicit_sandbox_retirement")
    if authorization is None:
        return False
    if (
        data.get("order_id") != EXPLICIT_RETIREMENT_ORDER
        or data.get("custom_domain") != "hushline.foo"
        or data.get("payment_mode") != "stripe_test"
        or data.get("license_limit") != EXPLICIT_RETIREMENT_LICENSES
        or not isinstance(authorization, dict)
        or set(authorization) != {"reason", "authorized_at"}
        or authorization.get("reason") != "owner-authorized-permanent-sandbox-deletion"
    ):
        raise ValueError("Explicit sandbox retirement escaped its exact authorized order")
    authorized = datetime.fromisoformat(authorization["authorized_at"])
    if authorized.tzinfo is None or authorized.utcoffset() != UTC.utcoffset(authorized):
        raise ValueError("Explicit sandbox retirement authorization must be UTC")
    if not datetime(2026, 10, 5, tzinfo=UTC) <= authorized <= datetime.now(UTC):
        raise ValueError("Invalid explicit sandbox retirement authorization time")
    return True


PROTECTED_ORDERS = {
    "de44b913bbc22b3ac75d8e5b114bdc45",
    "d9a565c4b17aca835b1f23a0b69b482b",
    "1c08c360da985ca24e9e246371ffc97f",
}


CLOCK_FIXTURE_ORDER = "6368ab5a5987358f9a9083f8ec2707b7"


def stripe_get(path: str) -> dict:
    key = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
    if not key.startswith(("sk_test_", "rk_test_")):
        raise ValueError("A dedicated Stripe test verification key is required")
    request = urllib.request.Request(  # noqa: S310 — fixed Stripe HTTPS endpoint
        "https://api.stripe.com/v1/" + path,
        headers={"Authorization": f"Bearer {key}", "Stripe-Version": API_VERSION},
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: object, **kwargs: object) -> None:
            return None

    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        return json.load(response)


def retrieve(session_id: str) -> dict:
    if not re.fullmatch(r"cs_test_[A-Za-z0-9]+", session_id):
        raise ValueError("Only a sandbox Checkout Session can authorize test resources")
    return stripe_get(f"checkout/sessions/{session_id}?expand[]=subscription.latest_invoice")


def is_clock_order(data: dict) -> bool:
    clock_id = (data.get("stripe_payment") or {}).get("test_clock_id")
    if clock_id is None:
        return False
    if (
        data.get("order_id") != CLOCK_FIXTURE_ORDER
        or data.get("custom_domain") != ""
        or not isinstance(clock_id, str)
        or not re.fullmatch(r"clock_[A-Za-z0-9]+", clock_id)
    ):
        raise ValueError("Stripe clock cannot alter another order or hostname")
    return True


def clock_current(data: dict, session: dict) -> datetime | None:
    if not is_clock_order(data):
        return None
    customer_id = session.get("customer")
    if not isinstance(customer_id, str) or not re.fullmatch(r"cus_[A-Za-z0-9]+", customer_id):
        raise ValueError("Invalid clock-owned sandbox customer")
    customer = stripe_get("customers/" + customer_id)
    clock_id = data["stripe_payment"]["test_clock_id"]
    clock = stripe_get("test_helpers/test_clocks/" + clock_id)
    if (
        customer.get("id") != customer_id
        or customer.get("livemode") is not False
        or customer.get("test_clock") != clock_id
        or customer.get("metadata") != {"single_tenant_clock_order": CLOCK_FIXTURE_ORDER}
        or clock.get("id") != clock_id
        or clock.get("livemode") is not False
        or clock.get("status") != "ready"
    ):
        raise ValueError("Stripe has not confirmed the exact fixture clock ownership")
    return datetime.fromtimestamp(clock["frozen_time"], UTC)


def validate(data: dict, session: dict, retiring: bool = False) -> None:
    if data.get("order_id") in PROTECTED_ORDERS:
        raise ValueError("Stripe cannot reuse a retired protected test order")
    proof = data.get("stripe_payment")
    expected = {
        "receipt",
        "session_id",
        "subscription_id",
        "period_start",
        "period_end",
    }
    if is_clock_order(data):
        expected.add("test_clock_id")
    if not isinstance(proof, dict) or set(proof) != expected:
        raise ValueError("A complete Stripe payment proof is required")
    if not re.fullmatch(r"[a-f0-9]{32}", proof["receipt"]):
        raise ValueError("Invalid sandbox payment receipt")
    sub = session.get("subscription") or {}
    invoice = sub.get("latest_invoice") or {}
    quantity = data.get("license_limit")
    if quantity is not None and (
        not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1
    ):
        raise ValueError("Invalid paid license limit")
    license_cost = Decimal("20000") if quantity is None else Decimal(quantity) * 240
    subtotal = Decimal("1282.80") + license_cost
    components = [128280, int(license_cost * 100)] + [int(subtotal * 10)] * 3
    amount = sum(components)
    metadata = {"single_tenant_receipt": proof["receipt"], "single_tenant_order": data["order_id"]}
    if (
        session.get("id") != proof["session_id"]
        or session.get("livemode") is not False
        or session.get("payment_status") != "paid"
        or session.get("status") != "complete"
        or session.get("mode") != "subscription"
        or session.get("client_reference_id") != proof["receipt"]
        or session.get("metadata") != metadata
        or session.get("currency") != "usd"
        or session.get("amount_total") != amount
        or sub.get("id") != proof["subscription_id"]
        or sub.get("livemode") is not False
        or sub.get("status") not in ({"active", "canceled"} if retiring else {"active"})
        or sub.get("metadata") != metadata
        or sub.get("customer") != session.get("customer")
        or invoice.get("status") != "paid"
        or invoice.get("livemode") is not False
        or invoice.get("amount_paid") != amount
        or invoice.get("currency") != "usd"
        or invoice.get("subscription") != sub.get("id")
        or invoice.get("customer") != sub.get("customer")
    ):
        raise ValueError("Stripe has not confirmed the exact owned annual payment")
    start = datetime.fromtimestamp(sub["current_period_start"], UTC)
    end = datetime.fromtimestamp(sub["current_period_end"], UTC)
    day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
    if end != start.replace(year=start.year + 1, day=day):
        raise ValueError("Stripe must confirm a complete calendar-year term")
    if start.isoformat() != proof["period_start"] or end.isoformat() != proof["period_end"]:
        raise ValueError("Stripe billing period differs from the immutable order proof")
    items = sub.get("items", {}).get("data", [])
    if len(items) != len(components) or sorted(
        item["price"]["unit_amount"] for item in items
    ) != sorted(components):
        raise ValueError("Stripe annual price components differ from the paid license selection")
    if any(
        item.get("quantity") != 1
        or item["price"].get("currency") != "usd"
        or item["price"].get("recurring", {}).get("interval") != "year"
        or item["price"].get("recurring", {}).get("interval_count") != 1
        for item in items
    ):
        raise ValueError("All payment components must be billed annually")
    lines = invoice.get("lines", {}).get("data", [])
    if len(lines) != len(components) or any(
        line.get("proration") is not False
        or line.get("period", {}).get("start") != sub["current_period_start"]
        or line.get("period", {}).get("end") != sub["current_period_end"]
        for line in lines
    ):
        raise ValueError("Paid invoice must cover the exact annual subscription period")
    current = clock_current(data, session) or datetime.now(UTC)
    if not retiring and not start <= current < end:
        raise ValueError("Stripe payment is not currently valid")
    if (
        retiring
        and not explicit_retirement(data)
        and (
            current < end
            or not (sub.get("cancel_at_period_end") or sub.get("status") == "canceled")
        )
    ):
        raise ValueError("Stripe subscription is not cancelled and due for retirement")


def verify(data: dict, retiring: bool = False) -> None:
    if data.get("order_id") in PROTECTED_ORDERS:
        raise ValueError("Stripe cannot reuse a retired protected test order")
    validate(data, retrieve(data["stripe_payment"]["session_id"]), retiring)


def unchanged(path: Path, latest: Path) -> None:
    data = json.loads(path.read_text())
    if data != json.loads(latest.read_text()):
        raise ValueError("Stripe order changed after planning")
    verify(data)

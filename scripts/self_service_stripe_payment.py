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


def retrieve(session_id: str) -> dict:
    key = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
    if not key.startswith(("sk_test_", "rk_test_")):
        raise ValueError("A dedicated Stripe test verification key is required")
    if not re.fullmatch(r"cs_test_[A-Za-z0-9]+", session_id):
        raise ValueError("Only a sandbox Checkout Session can authorize test resources")
    request = urllib.request.Request(  # noqa: S310 — fixed Stripe HTTPS endpoint
        f"https://api.stripe.com/v1/checkout/sessions/{session_id}?expand[]=subscription.latest_invoice",
        headers={"Authorization": f"Bearer {key}", "Stripe-Version": API_VERSION},
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: object, **kwargs: object) -> None:
            return None

    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        return json.load(response)


def validate(data: dict, session: dict, retiring: bool = False) -> None:
    proof = data.get("stripe_payment")
    if not isinstance(proof, dict) or set(proof) != {
        "receipt",
        "session_id",
        "subscription_id",
        "period_start",
        "period_end",
    }:
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
    if not retiring and not start <= datetime.now(UTC) < end:
        raise ValueError("Stripe payment is not currently valid")
    if retiring and (
        datetime.now(UTC) < end
        or not (sub.get("cancel_at_period_end") or sub.get("status") == "canceled")
    ):
        raise ValueError("Stripe subscription is not cancelled and due for retirement")


def verify(data: dict, retiring: bool = False) -> None:
    validate(data, retrieve(data["stripe_payment"]["session_id"]), retiring)


def unchanged(path: Path, latest: Path) -> None:
    data = json.loads(path.read_text())
    if data != json.loads(latest.read_text()):
        raise ValueError("Stripe order changed after planning")
    verify(data)

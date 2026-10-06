"""Annual Single Tenant billing using the app's existing Stripe configuration.

No live request runs unless the new-sales feature is explicitly enabled. Billing
identities are independent of Super User subscriptions; no premium user billing
fields are changed, and only metadata-bound Single Tenant objects are accepted.
"""

import calendar
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import stripe
from flask import current_app

from hushline.db import db
from hushline.model import SingleTenantOrder
from hushline.single_tenant_client import ServiceUnavailable

COMPONENT_COUNT = 5
MAX_TOTAL_CENTS = 99999999
API_VERSION = "2024-06-20"


class SubscriptionExpired(ServiceUnavailable):
    """The owned Stripe subscription ended before a withdrawal could complete."""


@dataclass(frozen=True)
class PaidYear:
    customer: str
    subscription: str
    start: datetime
    end: datetime
    invoice: str


def prices(quantity: int | None) -> list[tuple[str, int]]:
    if quantity is not None and (
        isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1
    ):
        raise ValueError("A positive license count or Unlimited is required")
    licenses = Decimal(20000) if quantity is None else Decimal(quantity) * 240
    subtotal = Decimal("1282.80") + licenses
    fee = int(subtotal * 10)
    result = [
        ("Infrastructure", 128280),
        (
            "Unlimited licenses" if quantity is None else f"Licenses ({quantity})",
            int(licenses * 100),
        ),
        ("Donation", fee),
        ("Administration", fee),
        ("Support", fee),
    ]
    if sum(value for _, value in result) > MAX_TOTAL_CENTS:
        raise ValueError("The annual total exceeds Stripe's checkout limit")
    return result


def metadata(order: SingleTenantOrder) -> dict[str, str]:
    return {
        "single_tenant_kind": "paid-instance",
        "single_tenant_order": order.id,
        "single_tenant_owner": order.owner_ref,
        "single_tenant_receipt": order.billing_receipt or "",
    }


def annual_end(start: datetime) -> datetime:
    day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
    return start.replace(year=start.year + 1, day=day)


def verified_invoice(
    order: SingleTenantOrder, session: Any, *, live: bool, historical: bool = False
) -> PaidYear:
    expected = metadata(order)
    subscription = session.get("subscription") or {}
    invoice = subscription.get("latest_invoice") if hasattr(subscription, "get") else None
    invoice = invoice or {}
    if (
        not order.billing_receipt
        or session.get("id") != order.stripe_session_id
        or session.get("livemode") is not live
        or session.get("status") != "complete"
        or session.get("payment_status") != "paid"
        or session.get("mode") != "subscription"
        or session.get("client_reference_id") != order.billing_receipt
        or any(session.get("metadata", {}).get(k) != v for k, v in expected.items())
        or not hasattr(subscription, "get")
        or subscription.get("livemode") is not live
        or any(subscription.get("metadata", {}).get(k) != v for k, v in expected.items())
        or session.get("currency") != "usd"
        or session.get("amount_total") != sum(value for _, value in prices(order.license_limit))
        or not isinstance(invoice.get("id"), str)
        or not invoice["id"].startswith("in_")
        or (historical and invoice["id"] != order.stripe_invoice_id)
        or invoice.get("livemode") is not live
        or invoice.get("status") != "paid"
        or invoice.get("currency") != "usd"
        or invoice.get("amount_paid") != session.get("amount_total")
        or invoice.get("customer") != session.get("customer")
        or subscription.get("customer") != session.get("customer")
        or invoice.get("subscription") != subscription.get("id")
        or not isinstance(session.get("customer"), str)
        or not isinstance(subscription.get("id"), str)
        or (order.stripe_customer_id and session.get("customer") != order.stripe_customer_id)
        or (order.stripe_subscription_id and subscription.get("id") != order.stripe_subscription_id)
    ):
        raise ValueError("Stripe has not confirmed this account's complete annual payment")
    if historical:
        lines = invoice.get("lines", {}).get("data", [])
        if len(lines) != COMPONENT_COUNT or any(
            not isinstance(line.get("period", {}).get(field), int)
            for line in lines
            for field in ("start", "end")
        ):
            raise ValueError("Every paid component must cover the same complete annual term")
        period = lines[0]["period"]
        start = datetime.fromtimestamp(period["start"], UTC)
        end = datetime.fromtimestamp(period["end"], UTC)
    else:
        start = datetime.fromtimestamp(subscription["current_period_start"], UTC)
        end = datetime.fromtimestamp(subscription["current_period_end"], UTC)
    if annual_end(start) != end:
        raise ValueError("A complete calendar-year payment is required")
    items = subscription.get("items", {}).get("data", [])
    lines = invoice.get("lines", {}).get("data", [])
    if (
        len(items) != COMPONENT_COUNT
        or len(lines) != COMPONENT_COUNT
        or any(
            item.get("quantity") != 1
            or item.get("price", {}).get("currency") != "usd"
            or item.get("price", {}).get("recurring", {}).get("interval") != "year"
            or item.get("price", {}).get("recurring", {}).get("interval_count") != 1
            for item in items
        )
        or any(
            line.get("proration") is not False
            or line.get("period", {}).get("start") != int(start.timestamp())
            or line.get("period", {}).get("end") != int(end.timestamp())
            for line in lines
        )
    ):
        raise ValueError("Every paid component must cover the same complete annual term")
    if sorted(item["price"]["unit_amount"] for item in items) != sorted(
        value for _, value in prices(order.license_limit)
    ):
        raise ValueError("The annual price components changed")
    if order.period_start and start < datetime.fromisoformat(order.period_start):
        raise ValueError("An older payment cannot replace the verified paid year")
    return PaidYear(session["customer"], subscription["id"], start, end, invoice["id"])


def verified_year(order: SingleTenantOrder, session: Any, *, live: bool, now: datetime) -> PaidYear:
    paid = verified_invoice(order, session, live=live)
    if session["subscription"].get("status") != "active":
        raise ValueError("Stripe has not confirmed this account's complete annual payment")
    if not paid.start <= now < paid.end:
        raise ValueError("A current complete calendar-year payment is required")
    return paid


def client() -> Any:
    key = current_app.config.get("STRIPE_SECRET_KEY", "")
    if current_app.config.get("SINGLE_TENANT_TEST_MODE") or not key.startswith(
        ("sk_live_", "rk_live_")
    ):
        raise ServiceUnavailable(
            "Live checkout requires the app's existing live Stripe configuration"
        )
    return stripe.StripeClient(key, stripe_version=API_VERSION)


def checkout(order: SingleTenantOrder) -> dict[str, Any]:
    if not current_app.config.get("SINGLE_TENANT_ACCEPT_PAYMENTS"):
        raise ServiceUnavailable("New Single Tenant subscriptions are temporarily unavailable")
    origin = current_app.config.get("PUBLIC_BASE_URL", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
    ):
        raise ServiceUnavailable("Live checkout requires the app's configured HTTPS origin")
    api = client()
    locked = db.session.scalar(
        db.select(SingleTenantOrder).where(SingleTenantOrder.id == order.id).with_for_update()
    )
    if locked is None or locked.owner_ref != order.owner_ref or locked.user_id is None:
        raise ServiceUnavailable("This checkout no longer belongs to an active account")
    order = locked
    if order.paid or order.cancellation_pending:
        raise ServiceUnavailable("This annual checkout is no longer available")
    if not order.billing_receipt:
        order.billing_receipt = secrets.token_hex(16)
        # Persist the idempotency reservation before contacting Stripe, then
        # reacquire the lock: deletion or another checkout may have committed.
        db.session.commit()
        reserved = db.session.scalar(
            db.select(SingleTenantOrder)
            .where(SingleTenantOrder.id == locked.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            reserved is None
            or reserved.owner_ref != locked.owner_ref
            or reserved.user_id is None
            or reserved.paid
            or reserved.cancellation_pending
        ):
            raise ServiceUnavailable("This annual checkout is no longer available")
        order = reserved
    if not order.billing_receipt:
        raise ServiceUnavailable("The annual checkout reservation is unavailable")
    try:
        if order.stripe_session_id:
            session = api.checkout.sessions.retrieve(order.stripe_session_id)
        else:
            session = api.checkout.sessions.create(
                {
                    "mode": "subscription",
                    "payment_method_types": ["card"],
                    "client_reference_id": order.billing_receipt,
                    "metadata": metadata(order),
                    "subscription_data": {"metadata": metadata(order)},
                    "line_items": [
                        {
                            "quantity": 1,
                            "price_data": {
                                "currency": "usd",
                                "unit_amount": amount,
                                "recurring": {"interval": "year"},
                                "product_data": {"name": name},
                            },
                        }
                        for name, amount in prices(order.license_limit)
                    ],
                    "success_url": origin.rstrip("/")
                    + "/single-tenant/payment-return?session_id={CHECKOUT_SESSION_ID}",
                    "cancel_url": origin.rstrip("/") + "/single-tenant",
                    "allow_promotion_codes": False,
                },
                options={"idempotency_key": "hushline-single-tenant-" + order.billing_receipt},
            )
            order.stripe_session_id = session["id"]
            db.session.commit()
    except stripe.StripeError:
        raise ServiceUnavailable("Stripe Checkout is temporarily unavailable") from None
    if session.get("livemode") is not True or session.get("status") != "open":
        raise ServiceUnavailable("This checkout is not available for a new payment")
    return {"order_id": order.id, "owner": order.owner_ref, "checkout_url": session.get("url")}


def confirm(order: SingleTenantOrder, session_id: str, *, commit: bool = True) -> dict[str, Any]:
    if commit:
        # Refresh under lock so a completed account-deletion/cancellation intent
        # cannot be overwritten by an older in-memory webhook or return request.
        refreshed = db.session.scalar(
            db.select(SingleTenantOrder)
            .where(SingleTenantOrder.id == order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if refreshed is None or refreshed.owner_ref != order.owner_ref:
            raise ServiceUnavailable("The account does not own this checkout")
        order = refreshed
    if not session_id or session_id != order.stripe_session_id:
        raise ServiceUnavailable("The account does not own this checkout")
    try:
        session = client().checkout.sessions.retrieve(
            session_id, {"expand": ["subscription.latest_invoice"]}
        )
        paid = verified_year(order, session, live=True, now=datetime.now(UTC))
    except (stripe.StripeError, ValueError, KeyError, TypeError):
        raise ServiceUnavailable(
            "Verification of the account's annual payment is pending"
        ) from None
    previous = (order.period_end, order.stripe_invoice_id, order.cancelled_at)
    order.stripe_customer_id = paid.customer
    order.stripe_subscription_id = paid.subscription
    order.stripe_invoice_id = paid.invoice
    order.period_start = paid.start.isoformat()
    order.period_end = paid.end.isoformat()
    order.paid = True
    if not order.cancellation_pending:
        order.cancelled = session["subscription"].get("cancel_at_period_end") is True
        cancelled = session["subscription"].get("canceled_at")
        order.cancelled_at = (
            datetime.fromtimestamp(cancelled, UTC).isoformat()
            if order.cancelled and cancelled
            else (order.cancelled_at or datetime.now(UTC).isoformat())
            if order.cancelled
            else None
        )
    if previous != (
        order.period_end,
        order.stripe_invoice_id,
        order.cancelled_at,
    ) and order.stage in {"dns", "provision", "ready"}:
        order.billing_sync_pending = True
    # The cancellation worker owns a row lock until both Stripe and the broker
    # acknowledge its intent. Payment confirmation must not release that lock.
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return {"order_id": order.id, "owner": order.owner_ref, "paid": True}


def cancel(order: SingleTenantOrder, desired: bool) -> dict[str, Any]:
    """Change only this order's renewal; account deletion does not erase its term."""
    api = client()
    try:
        if not order.paid:
            if not order.stripe_session_id:
                return {"order_id": order.id, "owner": order.owner_ref, "cancelled": desired}
            session = api.checkout.sessions.retrieve(order.stripe_session_id)
            if session.get("livemode") is not True or any(
                session.get("metadata", {}).get(k) != v for k, v in metadata(order).items()
            ):
                raise ValueError("The checkout does not belong to this account")
            if desired and session.get("status") == "open":
                api.checkout.sessions.expire(order.stripe_session_id)
                return {"order_id": order.id, "owner": order.owner_ref, "cancelled": True}
            if desired and session.get("status") == "expired":
                return {"order_id": order.id, "owner": order.owner_ref, "cancelled": True}
            confirm(order, order.stripe_session_id, commit=False)
        subscription = api.subscriptions.retrieve(order.stripe_subscription_id)
        if (
            subscription.get("livemode") is not True
            or subscription.get("customer") != order.stripe_customer_id
            or any(subscription.get("metadata", {}).get(k) != v for k, v in metadata(order).items())
        ):
            raise ValueError("The subscription does not belong to this account")
        if subscription.get("status") == "canceled":
            if not desired:
                order.cancelled_at = datetime.fromtimestamp(
                    subscription.get("canceled_at") or int(datetime.now(UTC).timestamp()), UTC
                ).isoformat()
                raise SubscriptionExpired("The owned subscription cannot be resumed")
        else:
            if not order.period_end or datetime.fromisoformat(order.period_end) <= datetime.now(
                UTC
            ):
                raise ValueError("The paid-through state must be reconciled before renewal changes")
            subscription = api.subscriptions.update(
                order.stripe_subscription_id,
                {"cancel_at_period_end": desired},
            )
            if (
                subscription.get("livemode") is not True
                or subscription.get("cancel_at_period_end") is not desired
            ):
                raise ValueError("Stripe did not confirm this order's renewal intent")
        order.cancelled_at = (
            datetime.fromtimestamp(
                subscription.get("canceled_at") or int(datetime.now(UTC).timestamp()), UTC
            ).isoformat()
            if desired
            else None
        )
        db.session.flush()
    except (stripe.StripeError, ValueError, KeyError, TypeError):
        raise ServiceUnavailable(
            "Confirmation of this account's renewal change is pending"
        ) from None
    return {"order_id": order.id, "owner": order.owner_ref, "cancelled": desired}


def proof(order: SingleTenantOrder) -> dict[str, Any]:
    if not order.paid or not all(
        [
            order.billing_receipt,
            order.stripe_session_id,
            order.stripe_subscription_id,
            order.stripe_customer_id,
            order.stripe_invoice_id,
            order.period_start,
            order.period_end,
        ]
    ):
        raise ServiceUnavailable("An independently verified annual payment is required")
    return {
        "payment_mode": "stripe_live",
        "license_limit": order.license_limit,
        "receipt": order.billing_receipt,
        "session_id": order.stripe_session_id,
        "subscription_id": order.stripe_subscription_id,
        "customer_id": order.stripe_customer_id,
        "invoice_id": order.stripe_invoice_id,
        "period_start": order.period_start,
        "period_end": order.period_end,
        "cancelled_at": order.cancelled_at,
    }


def handle_event(event: Any) -> bool:
    """Consume only owned Single Tenant events before the Super User event queue."""
    obj = event.get("data", {}).get("object", {})
    values = obj.get("metadata", {})
    identifier = (
        values.get("single_tenant_order")
        if values.get("single_tenant_kind") == "paid-instance"
        else None
    )
    subscription = obj.get("subscription")
    order = db.session.get(SingleTenantOrder, identifier) if identifier else None
    if order is None and isinstance(subscription, str):
        order = db.session.scalar(
            db.select(SingleTenantOrder).where(
                SingleTenantOrder.stripe_subscription_id == subscription
            )
        )
    if order is None:
        return identifier is not None
    if current_app.config.get("SINGLE_TENANT_TEST_MODE") or event.get("livemode") is not True:
        raise ServiceUnavailable("The Single Tenant billing event has the wrong payment mode")
    event_type = event.get("type", "")
    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "invoice.paid",
        "invoice.payment_succeeded",
    }:
        if order.stripe_session_id:
            confirm(order, order.stripe_session_id)
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        try:
            actual = client().subscriptions.retrieve(order.stripe_subscription_id or obj.get("id"))
        except stripe.StripeError:
            raise ServiceUnavailable(
                "The owned subscription state is temporarily unavailable"
            ) from None
        if (
            actual.get("livemode") is not True
            or any(actual.get("metadata", {}).get(k) != v for k, v in metadata(order).items())
            or (order.stripe_customer_id and actual.get("customer") != order.stripe_customer_id)
        ):
            raise ServiceUnavailable("The subscription event failed account ownership verification")
        cancelled = actual.get("cancel_at_period_end") is True or actual.get("status") == "canceled"
        if not order.cancellation_pending:
            order.cancelled = cancelled
            order.cancelled_at = (
                datetime.fromtimestamp(
                    actual.get("canceled_at") or int(datetime.now(UTC).timestamp()), UTC
                ).isoformat()
                if cancelled
                else None
            )
            order.billing_sync_pending = order.stage in {"dns", "provision", "ready"}
        db.session.commit()
    return True


def refresh_expired_terms() -> int:
    """Recover missed owned renewal/cancellation events without trusting callbacks."""
    if current_app.config.get("SINGLE_TENANT_TEST_MODE"):
        return 0
    count = 0
    attempted: set[str] = set()
    while True:
        order = db.session.scalar(
            db.select(SingleTenantOrder)
            .where(
                SingleTenantOrder.paid.is_(True),
                SingleTenantOrder.period_end <= datetime.now(UTC).isoformat(),
                SingleTenantOrder.service_state != "retired",
                SingleTenantOrder.id.not_in(attempted),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if order is None:
            db.session.rollback()
            return count
        attempted.add(order.id)
        try:
            actual = client().subscriptions.retrieve(order.stripe_subscription_id)
            if (
                actual.get("id") != order.stripe_subscription_id
                or actual.get("customer") != order.stripe_customer_id
                or actual.get("livemode") is not True
                or any(
                    actual.get("metadata", {}).get(key) != value
                    for key, value in metadata(order).items()
                )
            ):
                raise ValueError("Expired subscription failed exact ownership verification")
            if actual.get("status") == "canceled":
                if not order.cancellation_pending:
                    order.cancelled = True
                    order.cancelled_at = datetime.fromtimestamp(
                        actual.get("canceled_at") or int(datetime.now(UTC).timestamp()), UTC
                    ).isoformat()
                    order.billing_sync_pending = order.stage in {"dns", "provision", "ready"}
            else:
                confirm(order, order.stripe_session_id or "", commit=False)
            db.session.commit()
            count += 1
        except (stripe.StripeError, ServiceUnavailable, ValueError, KeyError, TypeError):
            db.session.rollback()

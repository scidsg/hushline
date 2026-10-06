"""Fresh payment authority for isolated workflows; Stripe keys stay in the portal.

This endpoint is absent in sandbox mode and when Single Tenant is disabled.
Requests are signed, replay-protected and exactly order/owner bound. Historical
invoice evidence alone never authorizes provisioning or early retirement.
"""

import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime
from typing import Any

import stripe
from flask import Blueprint, Flask, Response, jsonify, request
from sqlalchemy.exc import IntegrityError

from hushline import single_tenant_billing as billing
from hushline.db import db
from hushline.model import SingleTenantOrder
from hushline.model.single_tenant_nonce import SingleTenantNonce
from hushline.single_tenant_client import ServiceUnavailable, validate_settings

PATH = "/internal/single-tenant/billing-authority"
MAX_BODY = 16384
MAX_SKEW = 300


def authenticate(body: bytes, headers: Any, key: bytes, now: int) -> str:
    timestamp = headers.get("X-Hushline-Timestamp", "")
    nonce = headers.get("X-Hushline-Nonce", "")
    signature = headers.get("X-Hushline-Signature", "")
    if (
        not re.fullmatch(r"[0-9]{10}", timestamp)
        or abs(int(timestamp) - now) > MAX_SKEW
        or not re.fullmatch(r"[a-f0-9]{32}", nonce)
        or not re.fullmatch(r"[a-f0-9]{64}", signature)
        or len(body) > MAX_BODY
    ):
        raise ValueError("Billing request authentication failed")
    digest = hashlib.sha256(body).hexdigest()
    signed = f"POST\n{PATH}\n{timestamp}\n{nonce}\n{digest}".encode()
    expected = hmac.new(key, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Billing request authentication failed")
    return nonce


def consume_nonce(nonce: str, now: int) -> None:
    db.session.execute(db.delete(SingleTenantNonce).where(SingleTenantNonce.seen < now - 600))
    db.session.add(SingleTenantNonce(nonce=nonce, seen=now))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ValueError("Billing request already consumed") from None


def authorize(order: SingleTenantOrder, purpose: str, now: datetime) -> dict[str, Any]:
    if (
        not order.paid
        or not order.stripe_session_id
        or not order.stripe_subscription_id
        or not order.stripe_customer_id
        or order.service_state == "retired"
    ):
        raise ValueError("A verified owned payment is required")
    session = billing.client().checkout.sessions.retrieve(
        order.stripe_session_id, {"expand": ["subscription.latest_invoice"]}
    )
    paid = billing.verified_invoice(order, session, live=True)
    if purpose == "provision":
        if order.user_id is None or session["subscription"].get("status") != "active":
            raise ValueError("An active owning account and subscription are required")
        if not paid.start <= now < paid.end:
            raise ValueError("The paid year is not currently active")
        # Save a newly paid renewal before producing fresh immutable evidence.
        changed = order.period_end != paid.end.isoformat()
        order.period_start = paid.start.isoformat()
        order.period_end = paid.end.isoformat()
        if changed and order.stage in {"dns", "provision", "ready"}:
            order.billing_sync_pending = True
    elif purpose == "retire":
        if (
            order.cancellation_pending
            or not order.cancelled
            or not order.cancelled_at
            or session["subscription"].get("status") != "canceled"
            or order.period_start != paid.start.isoformat()
            or order.period_end != paid.end.isoformat()
            or now < paid.end
        ):
            raise ValueError(
                "Retirement requires the unchanged expired year and terminal cancellation"
            )
    else:
        raise ValueError("Unsupported billing authority purpose")
    return {
        "order_id": order.id,
        "owner": order.owner_ref,
        "authorized": purpose,
        "checked_at": now.isoformat(),
        "payment": billing.proof(order),
    }


def init_app(app: Flask) -> None:
    if not app.config.get("SINGLE_TENANT_ENABLED") or app.config.get("SINGLE_TENANT_TEST_MODE"):
        return
    _, key = validate_settings(app.config)
    bp = Blueprint("single_tenant_authority", __name__)

    @bp.route(PATH, methods=["POST"])
    def fresh_billing_authority() -> tuple[Response, int] | Response:
        if request.content_length is None or request.content_length > MAX_BODY:
            return jsonify(error="Invalid billing request"), 413
        body = request.get_data()
        try:
            epoch = int(time.time())
            nonce = authenticate(body, request.headers, key, epoch)
            consume_nonce(nonce, epoch)
            data = json.loads(body)
            if (
                not isinstance(data, dict)
                or set(data) != {"order_id", "owner", "purpose"}
                or not isinstance(data["order_id"], str)
                or not re.fullmatch(r"[a-f0-9]{32}", data["order_id"])
                or not isinstance(data["owner"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", data["owner"])
                or data["purpose"] not in {"provision", "retire"}
            ):
                raise ValueError("Invalid billing request")
            order = db.session.scalar(
                db.select(SingleTenantOrder)
                .where(SingleTenantOrder.id == data["order_id"])
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if order is None or not hmac.compare_digest(order.owner_ref, data["owner"]):
                raise ValueError("The account does not own this order")
            result = authorize(order, data["purpose"], datetime.now(UTC))
            db.session.commit()
            return jsonify(result)
        except (ValueError, KeyError, TypeError):
            db.session.rollback()
            return jsonify(error="Billing ownership or eligibility verification failed"), 409
        except (stripe.StripeError, ServiceUnavailable):
            db.session.rollback()
            return jsonify(error="Fresh payment verification is temporarily unavailable"), 503

    @bp.after_request
    def private(response: Any) -> Any:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.register_blueprint(bp)

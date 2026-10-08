"""Authenticated server-to-server single tenant requests with fixed trust roots."""

import contextlib
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from flask import current_app

from hushline.model.single_tenant_order import SingleTenantOrder

MAX_RESPONSE_BYTES = 65536
HTTP_OK = 200
CLOCK_SERVICE_PORT = 8776


class ServiceUnavailable(Exception):
    """A sanitized error; remote response bodies are never exposed."""


def validate_settings(config: Any) -> tuple[str, bytes]:
    origin = config.get("SINGLE_TENANT_SERVICE_URL", "")
    key = config.get("SINGLE_TENANT_SERVICE_KEY", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme == "http"
            and not (
                config.get("SINGLE_TENANT_TEST_MODE") is True
                and parsed.hostname == "127.0.0.1"
                and parsed.port == CLOCK_SERVICE_PORT
            )
        )
        or not isinstance(key, str)
        or not re.fullmatch(r"[a-f0-9]{64}", key)
    ):
        raise ValueError("Single Tenant requires an explicit service origin and dedicated key")
    fixture = config.get("SINGLE_TENANT_TEST_ORDER")
    if fixture and (
        config.get("SINGLE_TENANT_TEST_MODE") is not True
        or fixture != "6368ab5a5987358f9a9083f8ec2707b7"
        or origin.rstrip("/") != "http://127.0.0.1:8776"
    ):
        raise ValueError("The test order is confined to the isolated clock service")
    return origin.rstrip("/"), bytes.fromhex(key)


def _remote_call(order: SingleTenantOrder, action: str, **fields: Any) -> dict[str, Any]:
    origin, key = validate_settings(current_app.config)
    if action not in {
        "checkout",
        "confirm",
        "provision",
        "status",
        "dns",
        "cancel",
        "claim",
        "capabilities",
        "billing-sync",
        "destroy",
    }:
        raise ValueError("Unsupported service operation")
    path = "/internal/single-tenant/" + action
    body = json.dumps(
        {"order_id": order.id, "owner": order.owner_ref, **fields},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(
        key, f"POST\n{path}\n{timestamp}\n{nonce}\n{digest}".encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Hushline-Timestamp": timestamp,
        "X-Hushline-Nonce": nonce,
        "X-Hushline-Signature": signature,
    }
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.post(
                origin + path,
                data=body,
                headers=headers,
                timeout=(5, 30),
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code != HTTP_OK:
                    raise ServiceUnavailable("The instance service is temporarily unavailable")
                payload = bytearray()
                for chunk in response.iter_content(8192):
                    payload.extend(chunk)
                    if len(payload) > MAX_RESPONSE_BYTES:
                        raise ServiceUnavailable("The instance service response was invalid")
        result = json.loads(payload)
    except (requests.RequestException, ValueError):
        raise ServiceUnavailable("The instance service is temporarily unavailable") from None
    if (
        not isinstance(result, dict)
        or result.get("order_id") != order.id
        or result.get("owner") != order.owner_ref
    ):
        raise ServiceUnavailable("The instance service response failed ownership verification")
    return result


def call(order: SingleTenantOrder, action: str, **fields: Any) -> dict[str, Any]:
    if current_app.config.get("SINGLE_TENANT_TEST_MODE"):
        return _remote_call(order, action, **fields)
    from hushline import single_tenant_billing as billing

    if action == "checkout":
        capability = _remote_call(order, "capabilities")
        if (
            capability.get("payment_mode") != "stripe_live"
            or capability.get("namespace") != "hushline-single-tenant"
            or capability.get("lifecycle_protocol") != 1
            or capability.get("accepts_payments") is not True
        ):
            raise ServiceUnavailable("Live Single Tenant provisioning is not ready for purchases")
        return billing.checkout(order)
    if action == "confirm":
        return billing.confirm(order, fields.get("session_id", ""))
    if action == "cancel":
        desired = fields.get("cancelled")
        if not isinstance(desired, bool):
            raise ValueError("A renewal intent is required")
        result = billing.cancel(order, desired)
        if order.paid and order.stage in {"dns", "provision", "ready"}:
            _remote_call(order, "billing-sync", payment=billing.proof(order))
        return result
    if action == "status" and order.stage in {"licenses", "payment", "domain"}:
        # Before provisioning the broker has no instance to inspect. A missed
        # Checkout return is recovered by independently reading the same session.
        if not order.paid and order.stripe_session_id:
            with contextlib.suppress(ServiceUnavailable):
                billing.confirm(order, order.stripe_session_id)
        return {
            "order_id": order.id,
            "owner": order.owner_ref,
            "paid": order.paid,
            "status": {"state": "paid" if order.paid else "unpaid", "ready": False},
            "term": {
                "state": "active" if order.paid else "unpaid",
                "period_end": order.period_end,
                "cancelled_at": order.cancelled_at,
            },
        }
    if action in {"provision", "billing-sync"}:
        fields = {**fields, "payment": billing.proof(order)}
    result = _remote_call(order, action, **fields)
    if action == "status":
        # The app verifies Stripe. A delayed broker status cannot shorten or erase
        # the annual term, receipt or durable local cancellation intent.
        result["paid"] = order.paid
        result["term"] = {
            "state": (result.get("term") or {}).get("state", "active"),
            "period_end": order.period_end,
            "cancelled_at": order.cancelled_at,
        }
    return result

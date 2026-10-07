"""Signed private API for the general paid Single Tenant controller.

This factory never starts a listener or enables sales implicitly. Installation
must provide the customer-only ledger and healthy reviewed workflow publisher.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, abort, request
from werkzeug.wrappers.response import Response

from hushline.single_tenant import valid_customer_domain
from scripts.single_tenant_live_envelope import decrypt, keys
from scripts.single_tenant_live_health import dns
from scripts.single_tenant_live_health import healthy as https_healthy
from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_payment import verify

MAX_REQUEST_BYTES = 16384
MAX_CLOCK_SKEW = 300


def create_service(  # noqa: PLR0913 — explicit independent trust roots and readiness
    *,
    ledger: Ledger,
    portal_key: str,
    workflow_key: str,
    authority_origin: str,
    accepts_payments: bool,
    healthy: Callable[[], bool],
    billing_verify: Callable[..., dict[str, Any]] = verify,
) -> Flask:
    if (
        any(not re.fullmatch(r"[a-f0-9]{64}", key) for key in (portal_key, workflow_key))
        or portal_key == workflow_key
    ):
        raise ValueError("Distinct portal and workflow signing keys are required")
    parsed = urlsplit(authority_origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (parsed.hostname == "hushline.app" or parsed.hostname.endswith(".hushline.app"))
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Live billing authority requires an approved HTTPS origin")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

    @app.after_request
    def private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    def authenticated(key: str) -> dict[str, Any]:
        raw = request.get_data()
        timestamp = request.headers.get("X-Hushline-Timestamp", "")
        nonce = request.headers.get("X-Hushline-Nonce", "")
        signature = request.headers.get("X-Hushline-Signature", "")
        if (
            not re.fullmatch(r"[0-9]{1,12}", timestamp)
            or abs(int(time.time()) - int(timestamp)) > MAX_CLOCK_SKEW
            or not re.fullmatch(r"[a-f0-9]{32}", nonce)
            or not re.fullmatch(r"[a-f0-9]{64}", signature)
        ):
            abort(401)
        digest = hashlib.sha256(raw).hexdigest()
        signed = f"POST\n{request.path}\n{timestamp}\n{nonce}\n{digest}".encode()
        expected = hmac.new(bytes.fromhex(key), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature) or not ledger.nonce(
            nonce, now=int(time.time())
        ):
            abort(401)
        try:
            data = json.loads(raw)
            Ledger.owner(data["order_id"], data["owner"])
        except (ValueError, KeyError, TypeError):
            abort(400)
        return data

    def status(payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state", "queued")
        now = datetime.now(UTC)
        elapsed = max(0, int((now - datetime.fromisoformat(payload["created_at"])).total_seconds()))
        return {
            "order_id": payload["order_id"],
            "owner": payload["owner"],
            "paid": True,
            "verification": payload["verification"],
            "term": {
                "state": state if state in {"retiring", "retired"} else "active",
                "period_end": payload["payment"]["period_end"],
                "cancelled_at": payload["payment"]["cancelled_at"],
            },
            "status": {
                "state": state,
                "ready": state == "ready",
                "dns_verified": payload.get("dns_verified", False),
                "ingress": payload.get("ingress", ""),
                "checks": payload.get("checks", {}),
                "https_ok": payload.get("checks", {}).get("health") is True
                and payload.get("checks", {}).get("tls") is True,
                "workflow_url": payload.get("workflow_url", ""),
                "elapsed_seconds": elapsed,
                "message": "Deployment failed. Your order is saved; no replacement was requested."
                if state == "failed"
                else (
                    "Request publication interrupted. Recovering the same saved request."
                    if payload.get("publication_error")
                    else f"Deployment: {state.replace('_', ' ')} · {elapsed // 60} minutes elapsed."
                ),
            },
        }

    @app.post("/internal/single-tenant/<action>")
    def portal(action: str) -> dict[str, Any]:
        data = authenticated(portal_key)
        order, owner = data["order_id"], data["owner"]
        if action == "capabilities":
            if set(data) != {"order_id", "owner"}:
                abort(400)
            return {
                "order_id": order,
                "owner": owner,
                "payment_mode": "stripe_live",
                "namespace": "hushline-single-tenant",
                "lifecycle_protocol": 1,
                "accepts_payments": accepts_payments and healthy(),
            }
        try:
            if action == "provision":
                if set(data) != {
                    "order_id",
                    "owner",
                    "domain",
                    "payment",
                } or not valid_customer_domain(data["domain"]):
                    abort(400)
                # Verify before committing the private request. The workflow will
                # independently repeat verification immediately before apply.
                payment = billing_verify(
                    authority_origin, portal_key, order, owner, "provision", data["payment"]
                )
                try:
                    existing = ledger.get(order, owner)
                except ValueError:
                    existing = None
                if existing:
                    if existing["domain"] != data["domain"] or any(
                        existing["payment"][field] != payment[field]
                        for field in ("receipt", "subscription_id", "session_id")
                    ):
                        abort(409)
                    return status(existing)
                claim_private, claim_public = keys()
                ledger.reserve(
                    order,
                    owner,
                    {
                        "order_id": order,
                        "owner": owner,
                        "domain": data["domain"],
                        "payment": payment,
                        "state": "queued",
                        "created_at": datetime.now(UTC).isoformat(),
                        "verification": secrets.token_hex(32),
                        "claim_private_key": claim_private,
                        "claim_public_key": claim_public,
                    },
                )
            elif action == "billing-sync":
                if set(data) != {"order_id", "owner", "payment"}:
                    abort(400)
                # The portal holds its row lock through this acknowledgement.
                # Do not call it back synchronously; fresh authority is required
                # later, asynchronously, before every infrastructure operation.
                ledger.billing(order, owner, data["payment"])
            elif action in {"status", "dns", "claim"}:
                if set(data) != {"order_id", "owner"}:
                    abort(400)
            else:
                abort(404)
            payload = ledger.get(order, owner)
            if action == "dns" or (action == "status" and payload.get("dns_verified")):
                verified_dns = dns(
                    payload["domain"], payload.get("ingress", ""), payload["verification"]
                )
                ledger.observation(
                    order,
                    owner,
                    dns=verified_dns,
                    https_ok=verified_dns and https_healthy(payload["domain"]),
                )
                payload = ledger.get(order, owner)
            if action == "claim":
                if payload.get("state") != "ready" or not payload.get("claim"):
                    abort(409)
                return {
                    "order_id": order,
                    "owner": owner,
                    "domain": payload["domain"],
                    "invitation": payload["claim"],
                }
            return status(payload)
        except ValueError:
            abort(409)

    @app.post("/internal/single-tenant/workflow-result")
    def workflow() -> dict[str, Any]:
        data = authenticated(workflow_key)
        if set(data) != {"order_id", "owner", "purpose", "revision", "public_sha", "result"}:
            abort(400)
        try:
            ledger.event(
                data["order_id"],
                data["owner"],
                purpose=data["purpose"],
                revision=data["revision"],
                public_sha=data["public_sha"],
                result=decrypt(
                    ledger.get(data["order_id"], data["owner"])["claim_private_key"], data["result"]
                ),
            )
        except (ValueError, TypeError, KeyError):
            abort(409)
        return {"order_id": data["order_id"], "owner": data["owner"], "accepted": True}

    return app

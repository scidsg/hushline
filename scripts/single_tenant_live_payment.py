"""Read fresh portal payment authority without distributing live Stripe keys.

Only a trusted configured Hush Line HTTPS origin is accepted. The request and
response are private; callers must not print them or retain them in public job
artifacts. A proof is evidence, not permission to bypass resource ownership or
saved-plan guards.
"""

from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

PATH = "/internal/single-tenant/billing-authority"
MAX_BYTES = 65536
FRESH_SECONDS = 60
PAYMENT_FIELDS = {
    "payment_mode",
    "license_limit",
    "receipt",
    "session_id",
    "subscription_id",
    "customer_id",
    "invoice_id",
    "period_start",
    "period_end",
    "cancelled_at",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def validate_response(  # noqa: PLR0913 — explicit expected identity, purpose, proof and UTC clock
    data: Any,
    order: str,
    owner: str,
    purpose: str,
    expected: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if (
        not isinstance(data, dict)
        or set(data) != {"order_id", "owner", "authorized", "checked_at", "payment"}
        or data.get("order_id") != order
        or data.get("owner") != owner
        or data.get("authorized") != purpose
        or not isinstance(data.get("payment"), dict)
        or set(data["payment"]) != PAYMENT_FIELDS
        or data["payment"] != expected
        or expected.get("payment_mode") != "stripe_live"
    ):
        raise ValueError("Fresh billing authority failed exact-order verification")
    checked = datetime.fromisoformat(data["checked_at"])
    start = datetime.fromisoformat(expected["period_start"])
    end = datetime.fromisoformat(expected["period_end"])
    if any(value.tzinfo != UTC for value in (now, checked, start, end)):
        raise ValueError("Billing authority must use UTC")
    day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
    if end != start.replace(year=start.year + 1, day=day) or not (
        0 <= (now - checked).total_seconds() <= FRESH_SECONDS
    ):
        raise ValueError("Billing authority is stale or not a complete annual term")
    if purpose == "provision":
        if not start <= now < end:
            raise ValueError("Provisioning requires a currently paid year")
    elif purpose == "retire":
        if not expected.get("cancelled_at") or now < end:
            raise ValueError("Retirement requires confirmed cancellation after paid-year expiry")
    else:
        raise ValueError("Unsupported live billing operation")
    return data["payment"]


def verify(  # noqa: PLR0913 — trust roots are separate from the exact owned request
    origin: str,
    key_hex: str,
    order: str,
    owner: str,
    purpose: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (parsed.hostname == "hushline.app" or parsed.hostname.endswith(".hushline.app"))
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-f0-9]{64}", key_hex)
        or not re.fullmatch(r"[a-f0-9]{32}", order)
        or not re.fullmatch(r"[a-f0-9]{64}", owner)
        or purpose not in {"provision", "retire"}
    ):
        raise ValueError("Invalid live billing trust root or order")
    body = json.dumps(
        {"order_id": order, "owner": owner, "purpose": purpose},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(body).hexdigest()
    signed = f"POST\n{PATH}\n{timestamp}\n{nonce}\n{digest}".encode()
    signature = hmac.new(bytes.fromhex(key_hex), signed, hashlib.sha256).hexdigest()
    request = urllib.request.Request(  # noqa: S310 — configured HTTPS Hush Line origin validated above
        origin.rstrip("/") + PATH,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hushline-Timestamp": timestamp,
            "X-Hushline-Nonce": nonce,
            "X-Hushline-Signature": signature,
        },
        method="POST",
    )
    try:
        # Do not send the signing credential to a redirect or environment proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=30) as response:
            payload = response.read(MAX_BYTES + 1)
            if response.status != HTTPStatus.OK or len(payload) > MAX_BYTES:
                raise ValueError("Invalid billing authority response")
        return validate_response(
            json.loads(payload), order, owner, purpose, expected, datetime.now(UTC)
        )
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        raise ValueError(
            "Fresh live payment verification failed; no resource changes permitted"
        ) from None

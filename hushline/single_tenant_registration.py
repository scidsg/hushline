"""Explicit, replay-safe first-year gift setup in the existing live Stripe account."""

import hashlib
import re
import time
from typing import Any

import stripe
from flask import current_app

from hushline.single_tenant_billing import FREE_PERCENT, client, free_coupon
from hushline.single_tenant_client import ServiceUnavailable

CODE_LIFETIME_SECONDS = 7 * 24 * 60 * 60


def prepare_registration_code() -> None:
    coupon_id = current_app.config.get("SINGLE_TENANT_FREE_COUPON_ID", "")
    code = current_app.config.get("SINGLE_TENANT_FREE_REGISTRATION_CODE", "")
    if not code:
        return
    if (
        not current_app.config.get("SINGLE_TENANT_ENABLED")
        or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", coupon_id)
        or not re.fullmatch(r"[A-Z0-9-]{16,64}", code)
    ):
        raise ServiceUnavailable("The explicit registration code configuration is invalid")
    api = client()
    try:
        try:
            coupon = api.coupons.retrieve(coupon_id)
        except stripe.InvalidRequestError as exc:
            if exc.code != "resource_missing":
                raise
            coupon = api.coupons.create(
                {
                    "id": coupon_id,
                    "name": "Single Tenant first-year registration",
                    "percent_off": FREE_PERCENT,
                    "duration": "once",
                    "max_redemptions": 1,
                    "metadata": {"single_tenant_kind": "registration-gift"},
                },
                options={"idempotency_key": "hushline-single-tenant-gift-" + coupon_id},
            )
        if not free_coupon(coupon, coupon_id):
            raise ValueError("The existing gift definition does not match")
        existing = api.promotion_codes.list({"code": code, "limit": 100})
        matches = existing.get("data", [])
        if matches:
            if len(matches) != 1 or not owned_promotion(matches[0], coupon_id, code):
                raise ValueError("The existing code does not match")
            return  # Used or expired codes are never replaced or reactivated.
        promotion = api.promotion_codes.create(
            {
                "coupon": coupon_id,
                "code": code,
                "max_redemptions": 1,
                "expires_at": int(time.time()) + CODE_LIFETIME_SECONDS,
                "metadata": {"single_tenant_kind": "registration-gift"},
            },
            options={
                "idempotency_key": "hushline-single-tenant-code-"
                + hashlib.sha256((coupon_id + code).encode()).hexdigest()
            },
        )
        if not owned_promotion(promotion, coupon_id, code):
            raise ValueError("Stripe did not confirm the owned registration code")
    except (stripe.StripeError, ValueError, KeyError, TypeError):
        raise ServiceUnavailable("The approved registration code could not be verified") from None


def owned_promotion(promotion: Any, coupon_id: str, code: str) -> bool:
    coupon = promotion.get("coupon", {})
    return bool(
        promotion.get("livemode") is True
        and promotion.get("code", "").upper() == code
        and promotion.get("max_redemptions") == 1
        and hasattr(coupon, "get")
        and coupon.get("id") == coupon_id
    )

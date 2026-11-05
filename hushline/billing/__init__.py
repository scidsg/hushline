"""Provider-independent subscription billing."""

from flask import Flask, current_app

from hushline.billing.provider import BillingProvider


def init_app(app: Flask) -> None:
    name = app.config.get("BILLING_PROVIDER") or (
        "stripe" if app.config.get("STRIPE_SECRET_KEY") else "none"
    )
    provider: BillingProvider
    if name == "stripe":
        if not app.config.get("STRIPE_SECRET_KEY"):
            raise ValueError("Stripe billing requires STRIPE_SECRET_KEY")
        from hushline.billing.stripe import StripeBillingProvider

        provider = StripeBillingProvider(
            app.config["STRIPE_SECRET_KEY"], app.config.get("STRIPE_WEBHOOK_SECRET")
        )
    elif name in {"manual", "none"}:
        if app.config.get("STRIPE_SECRET_KEY"):
            raise ValueError("Remove STRIPE_SECRET_KEY before disabling automated billing")
        if app.config.get("SINGLE_TENANT_ENABLED"):
            raise ValueError("The managed Single Tenant service requires Stripe billing")
        from hushline.billing.manual import DisabledBillingProvider, ManualBillingProvider

        provider = ManualBillingProvider() if name == "manual" else DisabledBillingProvider()
    else:
        raise ValueError(f"Unknown billing provider: {name!r}")
    app.extensions["billing_provider"] = provider


def get_provider() -> BillingProvider:
    return current_app.extensions["billing_provider"]


def automated_billing_enabled() -> bool:
    return get_provider().automated

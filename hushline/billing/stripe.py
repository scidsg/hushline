"""Stripe SDK boundary. Preserve the existing API operations and parameters."""

import json
from contextlib import contextmanager
from typing import Any, Iterator

import stripe

from hushline.billing.domain import (
    BillingError,
    BillingEvent,
    BillingNotFound,
    BillingUnavailable,
    Customer,
    InvalidWebhook,
    InvoiceEvent,
    InvoiceLine,
    InvoiceLines,
    InvoicePlan,
    Price,
    Product,
    SubscriptionEvent,
)
from hushline.billing.provider import BillingProvider


@contextmanager
def translate_errors() -> Iterator[None]:
    try:
        yield
    except stripe.SignatureVerificationError:
        raise InvalidWebhook("Invalid webhook signature") from None
    except stripe.InvalidRequestError:
        raise BillingNotFound("Invalid payment resource") from None
    except stripe.StripeError:
        raise BillingError("Payment provider request failed") from None


def subscription_value(value: Any) -> SubscriptionEvent:
    return SubscriptionEvent(
        value.id,
        value.customer,
        value.status,
        value.cancel_at_period_end,
        value.current_period_start,
        value.current_period_end,
    )


def invoice_value(value: Any) -> InvoiceEvent:
    return InvoiceEvent(
        value.id,
        value.customer,
        value.total,
        value.status,
        value.created,
        getattr(value, "hosted_invoice_url", None),
        getattr(value, "invoice_pdf", None),
        InvoiceLines(
            tuple(
                InvoiceLine(InvoicePlan(line.plan.product) if line.plan else None)
                for line in value.lines.data
            )
        ),
    )


def product_value(value: Any) -> Product:
    return Product(value.id, value.name, value.default_price)


class StripeBillingProvider(BillingProvider):
    name = "stripe"
    automated = True
    form_action_origins = ("https://checkout.stripe.com", "https://billing.stripe.com")
    webhook_signature_header = "Stripe-Signature"

    def __init__(self, secret_key: str, webhook_secret: str | None) -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        # Retain the existing SDK configuration for the separate Single Tenant integration.
        stripe.api_key = secret_key

    def customer(self, customer_id: str | None, email: str) -> Customer:
        with translate_errors():
            if customer_id:
                try:
                    return Customer(stripe.Customer.modify(customer_id, email=email).id)
                except stripe.InvalidRequestError:
                    pass
            return Customer(stripe.Customer.create(email=email).id)

    def subscription(self, subscription_id: str) -> SubscriptionEvent:
        with translate_errors():
            return subscription_value(stripe.Subscription.retrieve(subscription_id))

    def invoice(self, invoice_id: str) -> InvoiceEvent:
        with translate_errors():
            return invoice_value(stripe.Invoice.retrieve(invoice_id))

    def checkout(
        self, user_id: str, customer_id: str, price_id: str, success_url: str
    ) -> str | None:
        with translate_errors():
            return stripe.checkout.Session.create(
                client_reference_id=user_id,
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                automatic_tax={"enabled": True},
                customer_update={"address": "auto"},
            ).url

    def portal(self, customer_id: str, return_url: str) -> str | None:
        with translate_errors():
            return stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
                flow_data={
                    "type": "payment_method_update",
                    "after_completion": {
                        "type": "redirect",
                        "redirect": {"return_url": return_url},
                    },
                },
            ).url

    def set_autorenew(self, subscription_id: str, enabled: bool) -> None:
        with translate_errors():
            stripe.Subscription.modify(subscription_id, cancel_at_period_end=not enabled)

    def cancel(self, subscription_id: str) -> None:
        with translate_errors():
            # Stripe 10 supports class-level deletion, but types it as an instance method.
            stripe.Subscription.delete(subscription_id)  # type: ignore[arg-type]

    def _event(self, event: Any) -> BillingEvent:
        # Preserve the JSON representation previously stored by StripeEvent.
        payload = json.loads(str(event))
        return BillingEvent(event.id, event.type, event.created, payload)

    def handle_service_event(self, event: BillingEvent) -> bool:
        from hushline import single_tenant_billing
        from hushline.single_tenant_client import ServiceUnavailable

        try:
            return single_tenant_billing.handle_event(event.payload)
        except ServiceUnavailable:
            raise BillingUnavailable("Managed-service payment reconciliation is pending") from None

    def validate_webhook(self, payload: bytes, signature: str) -> BillingEvent:
        with translate_errors():
            return self._event(
                stripe.Webhook.construct_event(
                    payload,
                    signature,
                    self.webhook_secret,
                )
            )

    def decode_event(self, payload: str) -> BillingEvent:
        with translate_errors():
            event = stripe.Event.construct_from(json.loads(payload), self.secret_key)
            subscription = None
            invoice = None
            if event.type.startswith("customer.subscription."):
                subscription = subscription_value(
                    stripe.Subscription.construct_from(
                        event.data.object,
                        self.secret_key,
                    )
                )
            elif event.type.startswith("invoice."):
                invoice = invoice_value(
                    stripe.Invoice.construct_from(
                        event.data.object,
                        self.secret_key,
                    )
                )
            return BillingEvent(
                event.id, event.type, event.created, json.loads(payload), subscription, invoice
            )

    def product(self, product_id: str) -> Product:
        with translate_errors():
            return product_value(stripe.Product.retrieve(product_id))

    def products(self) -> list[Product]:
        with translate_errors():
            return [product_value(value) for value in stripe.Product.list(limit=100)]

    def create_product(self, name: str) -> Product:
        with translate_errors():
            return product_value(
                stripe.Product.create(
                    name=name,
                    type="service",
                    tax_code="txcd_10103001",
                )
            )

    def price(self, price_id: str) -> Price:
        with translate_errors():
            value = stripe.Price.retrieve(price_id)
            return Price(value.id, value.unit_amount)

    def prices(self, product_id: str) -> list[Price]:
        with translate_errors():
            return [
                Price(value.id, value.unit_amount)
                for value in stripe.Price.search(query=f'product:"{product_id}"')
            ]

    def create_price(self, product_id: str, amount: int) -> Price:
        with translate_errors():
            value = stripe.Price.create(
                product=product_id,
                unit_amount=amount,
                currency="usd",
                recurring={"interval": "month"},
            )
            return Price(value.id, value.unit_amount)

    def set_default_price(self, product_id: str, price_id: str) -> None:
        with translate_errors():
            stripe.Product.modify(product_id, default_price=price_id)

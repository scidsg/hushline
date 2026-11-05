"""Application-owned values crossing the payment-provider boundary."""

import json
from dataclasses import dataclass
from typing import Any


class BillingError(Exception):
    """A payment provider could not complete an operation."""


class BillingNotFound(BillingError):
    """A referenced payment resource is invalid or no longer exists."""


class InvalidWebhook(BillingError):
    """A webhook could not be authenticated."""


class BillingUnavailable(BillingError):
    """Event reconciliation is temporarily unavailable; delivery should be retried."""


@dataclass(frozen=True)
class Customer:
    id: str


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    default_price: str | None


@dataclass(frozen=True)
class Price:
    id: str
    unit_amount: int | None


@dataclass(frozen=True)
class SubscriptionEvent:
    id: str
    customer: str
    status: str
    cancel_at_period_end: bool
    current_period_start: int
    current_period_end: int


@dataclass(frozen=True)
class InvoicePlan:
    product: str


@dataclass(frozen=True)
class InvoiceLine:
    plan: InvoicePlan | None


@dataclass(frozen=True)
class InvoiceLines:
    data: tuple[InvoiceLine, ...]


@dataclass(frozen=True)
class InvoiceEvent:
    id: str
    customer: str
    total: int
    status: str
    created: int
    hosted_invoice_url: str | None
    invoice_pdf: str | None
    lines: InvoiceLines


@dataclass(frozen=True)
class BillingEvent:
    id: str
    type: str
    created: int
    payload: dict[str, Any]
    subscription: SubscriptionEvent | None = None
    invoice: InvoiceEvent | None = None

    def __str__(self) -> str:
        return json.dumps(self.payload)

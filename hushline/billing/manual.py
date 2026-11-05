"""Self-hosted entitlements, administered locally without a payment service."""

from typing import NoReturn

from hushline.billing.domain import BillingError
from hushline.billing.provider import BillingProvider


def unavailable() -> NoReturn:
    raise BillingError("Automated payments are unavailable with this billing provider")


class ManualBillingProvider(BillingProvider):
    name = "manual"

    def customer(self, customer_id: str | None, email: str) -> NoReturn:
        unavailable()

    def subscription(self, subscription_id: str) -> NoReturn:
        unavailable()

    def invoice(self, invoice_id: str) -> NoReturn:
        unavailable()

    def checkout(self, user_id: str, customer_id: str, price_id: str, success_url: str) -> NoReturn:
        unavailable()

    def portal(self, customer_id: str, return_url: str) -> NoReturn:
        unavailable()

    def set_autorenew(self, subscription_id: str, enabled: bool) -> NoReturn:
        unavailable()

    def cancel(self, subscription_id: str) -> NoReturn:
        unavailable()

    def validate_webhook(self, payload: bytes, signature: str) -> NoReturn:
        unavailable()

    def decode_event(self, payload: str) -> NoReturn:
        unavailable()

    def product(self, product_id: str) -> NoReturn:
        unavailable()

    def products(self) -> NoReturn:
        unavailable()

    def create_product(self, name: str) -> NoReturn:
        unavailable()

    def price(self, price_id: str) -> NoReturn:
        unavailable()

    def prices(self, product_id: str) -> NoReturn:
        unavailable()

    def create_price(self, product_id: str, amount: int) -> NoReturn:
        unavailable()

    def set_default_price(self, product_id: str, price_id: str) -> NoReturn:
        unavailable()


class DisabledBillingProvider(ManualBillingProvider):
    name = "none"

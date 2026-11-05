from abc import ABC, abstractmethod

from hushline.billing.domain import (
    BillingEvent,
    Customer,
    InvoiceEvent,
    Price,
    Product,
    SubscriptionEvent,
)


class BillingProvider(ABC):
    """Billing operations used by the application; no vendor objects may escape."""

    name: str
    automated: bool = False
    form_action_origins: tuple[str, ...] = ()
    webhook_signature_header: str = ""

    def handle_service_event(self, event: BillingEvent) -> bool:
        """Optionally reconcile a provider's managed-service event outside the premium queue."""
        return False

    @abstractmethod
    def customer(self, customer_id: str | None, email: str) -> Customer:
        raise NotImplementedError

    @abstractmethod
    def subscription(self, subscription_id: str) -> SubscriptionEvent:
        raise NotImplementedError

    @abstractmethod
    def invoice(self, invoice_id: str) -> InvoiceEvent:
        raise NotImplementedError

    @abstractmethod
    def checkout(
        self, user_id: str, customer_id: str, price_id: str, success_url: str
    ) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def portal(self, customer_id: str, return_url: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set_autorenew(self, subscription_id: str, enabled: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, subscription_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def validate_webhook(self, payload: bytes, signature: str) -> BillingEvent:
        raise NotImplementedError

    @abstractmethod
    def decode_event(self, payload: str) -> BillingEvent:
        """Decode a previously authenticated event from the durable queue."""
        raise NotImplementedError

    @abstractmethod
    def product(self, product_id: str) -> Product:
        raise NotImplementedError

    @abstractmethod
    def products(self) -> list[Product]:
        raise NotImplementedError

    @abstractmethod
    def create_product(self, name: str) -> Product:
        raise NotImplementedError

    @abstractmethod
    def price(self, price_id: str) -> Price:
        raise NotImplementedError

    @abstractmethod
    def prices(self, product_id: str) -> list[Price]:
        raise NotImplementedError

    @abstractmethod
    def create_price(self, product_id: str, amount: int) -> Price:
        raise NotImplementedError

    @abstractmethod
    def set_default_price(self, product_id: str, price_id: str) -> None:
        raise NotImplementedError

import hashlib
import hmac
import json
import time

import pytest
import stripe
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.billing import get_provider, init_app
from hushline.billing.domain import BillingError, Customer, InvalidWebhook, SubscriptionEvent
from hushline.billing.provider import BillingProvider
from hushline.billing.stripe import StripeBillingProvider
from hushline.model import User


@pytest.mark.parametrize(
    ("config", "name"),
    [
        ({}, "none"),
        ({"STRIPE_SECRET_KEY": "sk_test_123"}, "stripe"),
        ({"BILLING_PROVIDER": "manual"}, "manual"),
    ],
)
def test_provider_selection(config: dict[str, str], name: str) -> None:
    app = Flask(__name__)
    app.config.update(config)
    init_app(app)
    assert app.extensions["billing_provider"].name == name


@pytest.mark.parametrize(
    "config",
    [
        {"BILLING_PROVIDER": "unknown"},
        {"BILLING_PROVIDER": "stripe"},
        {"BILLING_PROVIDER": "manual", "STRIPE_SECRET_KEY": "sk_test_123"},
        {"BILLING_PROVIDER": "none", "STRIPE_SECRET_KEY": "sk_test_123"},
        {"BILLING_PROVIDER": "manual", "SINGLE_TENANT_ENABLED": True},
    ],
)
def test_invalid_provider_config_fails_closed(config: dict[str, object]) -> None:
    app = Flask(__name__)
    app.config.update(config)
    with pytest.raises(ValueError, match="billing|billing provider"):
        init_app(app)


def test_stripe_manual_entitlement_command_is_unavailable(app: Flask, user: User) -> None:
    result = app.test_cli_runner().invoke(args=["billing", "set-tier", str(user.id), "business"])
    assert result.exit_code != 0
    assert "requires BILLING_PROVIDER=manual" in result.output


def test_signed_webhook_and_domain_normalization() -> None:
    provider = StripeBillingProvider("sk_test_local", "whsec_local")
    payload = json.dumps(
        {
            "id": "evt_local",
            "type": "customer.subscription.updated",
            "created": 123,
            "data": {
                "object": {
                    "id": "sub_local",
                    "customer": "cus_local",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 100,
                    "current_period_end": 200,
                }
            },
        }
    ).encode()
    timestamp = int(time.time())
    digest = hmac.new(b"whsec_local", str(timestamp).encode() + b"." + payload, hashlib.sha256)
    signature = f"t={timestamp},v1={digest.hexdigest()}"
    event = provider.validate_webhook(payload, signature)
    decoded = provider.decode_event(str(event))
    assert decoded.subscription == SubscriptionEvent(
        "sub_local", "cus_local", "active", False, 100, 200
    )
    assert decoded.payload == json.loads(payload)
    with pytest.raises(InvalidWebhook):
        provider.validate_webhook(payload + b" ", signature)
    with pytest.raises(InvalidWebhook):
        provider.validate_webhook(payload, "")
    expired = timestamp - 600
    old_digest = hmac.new(b"whsec_local", str(expired).encode() + b"." + payload, hashlib.sha256)
    with pytest.raises(InvalidWebhook):
        provider.validate_webhook(payload, f"t={expired},v1={old_digest.hexdigest()}")


def test_adapter_preserves_checkout_parameters(app: Flask, mocker: MockFixture) -> None:
    checkout = mocker.patch("stripe.checkout.Session.create")
    checkout.return_value.url = "https://checkout.stripe.com/test"
    assert (
        get_provider().checkout("42", "cus_42", "price_42", "https://example.org/return")
        == checkout.return_value.url
    )
    checkout.assert_called_once_with(
        client_reference_id="42",
        customer="cus_42",
        line_items=[{"price": "price_42", "quantity": 1}],
        mode="subscription",
        success_url="https://example.org/return",
        automatic_tax={"enabled": True},
        customer_update={"address": "auto"},
    )


def test_provider_errors_do_not_leak_vendor_exceptions(app: Flask, mocker: MockFixture) -> None:
    mocker.patch("stripe.Subscription.delete", side_effect=stripe.StripeError("private detail"))
    with pytest.raises(BillingError, match="Payment provider request failed"):
        get_provider().cancel("sub_42")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_uses_injected_provider_without_stripe(
    app: Flask, client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    provider = mocker.Mock(spec=BillingProvider)
    provider.automated = True
    provider.form_action_origins = ()
    provider.customer.return_value = Customer("local-customer")
    provider.checkout.return_value = "/local-checkout"
    app.extensions["billing_provider"] = provider
    stripe_create = mocker.patch("stripe.Customer.create", side_effect=AssertionError("SDK used"))
    response = client.post("/premium/upgrade")
    assert response.status_code == 302
    assert response.location == "/local-checkout"
    provider.checkout.assert_called_once_with(
        str(user.id), "local-customer", "price_123", "http://localhost:8080/premium/waiting"
    )
    stripe_create.assert_not_called()
    assert "stripe.com" not in response.headers["Content-Security-Policy"]


@pytest.mark.usefixtures("_authenticated_user")
def test_waiting_page_uses_only_local_status_polling(client: FlaskClient) -> None:
    response = client.get("/premium/waiting")
    assert response.status_code == 200
    assert "js/premium-waiting.js" in response.text
    assert "js.stripe.com" not in response.text
    policy = response.headers["Content-Security-Policy"]
    assert "script-src 'self';" in policy
    assert "frame-src 'none'" in policy
    assert "https://js.stripe.com" not in policy
    assert "https://api.stripe.com" not in policy
    assert "https://checkout.stripe.com" in policy

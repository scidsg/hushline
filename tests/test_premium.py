from unittest.mock import MagicMock

import pytest
import stripe
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import StripeInvoice, StripeInvoiceStatusEnum, Tier, User
from hushline.premium import (
    BUSINESS_TIER,
    FREE_TIER,
    create_customer,
    create_products_and_prices,
    create_subscription,
    get_latest_invoice_payment_intent_client_secret,
    get_subscription,
    handle_invoice_created,
    handle_invoice_payment_succeeded,
    handle_subscription_created,
    handle_subscription_deleted,
    handle_subscription_updated,
    update_price,
)


@pytest.fixture()
def mock_stripe(mocker: MockFixture) -> MagicMock:
    return mocker.patch("hushline.premium.stripe")


@pytest.fixture()
def business_tier() -> Tier:
    tier = db.session.query(Tier).filter_by(name="Business").first()
    if not tier:
        raise ValueError("Business tier not found")

    return tier


def test_create_products_and_prices(app: Flask, mock_stripe: MagicMock) -> None:
    with app.app_context():
        # Remove the stripe_product_id and stripe_price_id from the Business tier
        tier = Tier.query.filter_by(name="Business").first()
        assert tier is not None
        if not tier:
            return

        tier.stripe_product_id = None
        tier.stripe_price_id = None
        db.session.add(tier)
        db.session.commit()

        mock_stripe.Product.create.return_value = MagicMock(id="prod_123")
        mock_stripe.Price.create.return_value = MagicMock(id="price_123")

        create_products_and_prices()

        assert mock_stripe.Product.create.called
        assert mock_stripe.Price.create.called

        # Check that stripe_product_id and stripe_price_id were set
        tier = Tier.query.filter_by(name="Business").first()
        assert tier is not None
        if not tier:
            return

        assert tier.stripe_product_id is not None
        assert tier.stripe_price_id is not None


def test_update_price_existing(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = [MagicMock(id="price_123", unit_amount=2000)]

    with app.app_context():
        tier = Tier.query.filter_by(name="Business").first()
        assert tier is not None
        if not tier:
            return

        update_price(tier)

        assert not mock_stripe.Price.create.called
        assert mock_stripe.Product.modify.called


def test_update_price_new(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = []
    mock_stripe.Price.create.return_value = MagicMock(id="price_123")

    with app.app_context():
        tier = Tier.query.filter_by(name="Business").first()
        assert tier is not None
        if not tier:
            return

        update_price(tier)

        assert mock_stripe.Price.create.called
        assert mock_stripe.Product.modify.called


def test_create_customer(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Customer.create.return_value = MagicMock(id="cus_123")

    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        db.session.add(user)
        db.session.commit()

        create_customer(user)

        assert mock_stripe.Customer.create.called
        assert user.stripe_customer_id is not None

        # Check that the customer ID was saved to the database
        db.session.refresh(user)
        assert user.stripe_customer_id is not None


def test_create_subscription(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Customer.create.return_value = MagicMock(id="cus_123")
    mock_stripe.Subscription.create.return_value = MagicMock(id="sub_123")

    with app.app_context():
        tier = Tier.query.filter_by(name="Business").first()
        assert tier is not None

        user = User(email="test@example.com", password="password")  # noqa: S106
        db.session.add(user)
        db.session.commit()

        create_subscription(user, tier)

        assert mock_stripe.Subscription.create.called
        assert user.stripe_subscription_id is not None

        # Check that the subscription ID was saved to the database
        db.session.refresh(user)
        assert user.stripe_subscription_id is not None


def test_get_latest_invoice_payment_intent_client_secret(mock_stripe: MagicMock) -> None:
    mock_stripe.Invoice.retrieve.return_value = MagicMock(payment_intent="pi_123")
    mock_stripe.PaymentIntent.retrieve.return_value = MagicMock(client_secret="secret_123")  # noqa: S106

    secret = get_latest_invoice_payment_intent_client_secret(MagicMock(latest_invoice="inv_123"))

    assert secret == "secret_123"


def test_get_subscription(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Subscription.retrieve.return_value = MagicMock(id="sub_123")

    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_subscription_id = "sub_123"
        db.session.add(user)
        db.session.commit()

        subscription = get_subscription(user)

        assert subscription is not None
        assert mock_stripe.Subscription.retrieve.called


def test_handle_subscription_created(app: Flask) -> None:
    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_customer_id = "cus_123"
        db.session.add(user)
        db.session.commit()

        subscription = MagicMock()
        subscription.customer = "cus_123"
        subscription.id = "sub_123"

        handle_subscription_created(subscription)

        assert user.stripe_subscription_id == "sub_123"


def test_handle_subscription_updated(app: Flask) -> None:
    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_subscription_id = "sub_123"
        db.session.add(user)
        db.session.commit()

        subscription = MagicMock()
        subscription.id = "sub_123"
        subscription.status = "canceled"

        handle_subscription_updated(subscription)

        assert user.tier_id == FREE_TIER


def test_handle_subscription_deleted(app: Flask) -> None:
    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_subscription_id = "sub_123"
        db.session.add(user)
        db.session.commit()

        subscription = MagicMock()
        subscription.id = "sub_123"

        handle_subscription_deleted(subscription)

        assert user.tier_id == FREE_TIER
        assert user.stripe_subscription_id is None


def test_handle_invoice_created(app: Flask) -> None:
    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_customer_id = "cus_123"
        db.session.add(user)
        db.session.commit()

        handle_invoice_created(
            MagicMock(
                id="inv_123",
                customer="cus_123",
                hosted_invoice_url="https://example.com",
                total=2000,
                status=StripeInvoiceStatusEnum.OPEN,
                lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
            )
        )

        stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").first()
        assert stripe_invoice is not None


def test_handle_invoice_payment_succeeded(app: Flask) -> None:
    with app.app_context():
        user = User(email="test@example.com", password="password")  # noqa: S106
        user.stripe_customer_id = "cus_123"
        user.stripe_subscription_id = "sub_123"
        db.session.add(user)
        db.session.commit()

        invoice = MagicMock(
            id="inv_123",
            customer="cus_123",
            hosted_invoice_url="https://example.com",
            total=2000,
            status=StripeInvoiceStatusEnum.OPEN,
            lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
            subscription="sub_123",
        )
        handle_invoice_created(invoice)

        stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").first()
        assert stripe_invoice is not None

        invoice.status = StripeInvoiceStatusEnum.PAID
        handle_invoice_payment_succeeded(invoice)

        stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").first()
        assert stripe_invoice is not None
        assert stripe_invoice.total == 2000
        assert stripe_invoice.status == StripeInvoiceStatusEnum.PAID
        assert user.tier_id == BUSINESS_TIER


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_get_redirects_to_index(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_post_user_already_on_business_tier(
    client: FlaskClient, user: User, business_tier: Tier
) -> None:
    user.tier_id = BUSINESS_TIER
    db.session.commit()

    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_process(
    client: FlaskClient, user: User, business_tier: Tier, mocker: MockFixture
) -> None:
    user.stripe_customer_id = "cus_123"
    db.session.commit()

    mocker.patch("hushline.premium.create_subscription", return_value=MagicMock(id="sub_123"))
    mocker.patch(
        "hushline.premium.get_latest_invoice_payment_intent_client_secret",
        return_value="secret_123",
    )

    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 200

    # Check that the user has a stripe_subscription_id
    db.session.refresh(user)
    assert user.stripe_subscription_id is not None
    assert user.tier_id is None

    # Send the webhook event
    invoice = MagicMock(
        id="inv_123",
        customer="cus_123",
        hosted_invoice_url="https://example.com",
        total=2000,
        status=StripeInvoiceStatusEnum.OPEN,
        lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
        subscription="sub_123",
    )
    handle_invoice_created(invoice)
    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").first()
    assert stripe_invoice is not None

    invoice.status = StripeInvoiceStatusEnum.PAID
    handle_invoice_payment_succeeded(invoice)

    # Check that the user is now on the business tier
    db.session.refresh(user)
    assert user.tier_id == BUSINESS_TIER

    # And an invoice was created
    stripe_invoice = db.session.query(StripeInvoice).filter_by(user_id=user.id).first()
    assert stripe_invoice is not None


def test_downgrade_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.downgrade"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_downgrade_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.downgrade"))
    assert response.status_code == 400
    assert response.json == {"success": False}


@pytest.mark.usefixtures("_authenticated_user")
def test_downgrade_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.tier_id = BUSINESS_TIER
    db.session.commit()

    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", return_value=MagicMock()
    )

    response = client.post(url_for("premium.downgrade"))
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert mock_stripe_delete.called

    # Send the webhook event
    handle_subscription_deleted(MagicMock(id="sub_123"))

    db.session.refresh(user)
    assert user.tier_id == FREE_TIER
    assert user.stripe_subscription_id is None


@pytest.mark.usefixtures("_authenticated_user")
def test_downgrade_stripe_error(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.tier_id = BUSINESS_TIER
    db.session.commit()

    # Create an instance of the StripeError exception
    stripe_error_instance = MagicMock()
    stripe_error_instance.side_effect = stripe._error.StripeError("An error occurred")

    # Mock the stripe.Subscription.delete method to raise the StripeError exception
    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.downgrade"))
    assert response.status_code == 400
    assert response.json == {"success": False}
    assert mock_stripe_delete.called

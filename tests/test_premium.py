from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import stripe
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import (
    StripeInvoice,
    StripeInvoiceStatusEnum,
    StripeSubscriptionStatusEnum,
    Tier,
    User,
)
from hushline.premium import (
    create_customer,
    create_products_and_prices,
    get_subscription,
    handle_invoice_created,
    handle_invoice_updated,
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
    tier = db.session.query(Tier).filter_by(name="Business").one()
    if not tier:
        raise ValueError("Business tier not found")

    return tier


def test_create_products_and_prices(app: Flask, mocker: MagicMock) -> None:
    # Make sure we have a business tier
    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None
    if not tier:
        return

    # Make sure it has no Stripe IDs to start
    tier.stripe_product_id = None
    tier.stripe_price_id = None
    db.session.add(tier)
    db.session.commit()

    stripe_error_instance = MagicMock()
    stripe_error_instance.side_effect = stripe._error.InvalidRequestError("", param={})

    # Mock the Stripe API calls
    mock_stripe_product_create = mocker.patch(
        "hushline.premium.stripe.Product.create", return_value=MagicMock(id="prod_123")
    )
    mock_stripe_price_create = mocker.patch(
        "hushline.premium.stripe.Price.create", return_value=MagicMock(id="price_123")
    )
    mock_stripe_product_retrieve = mocker.patch(
        "hushline.premium.stripe.Product.retrieve",
        side_effect=stripe_error_instance,
    )
    mocker.patch(
        "hushline.premium.stripe.Product.list",
        return_value=[MagicMock(id="prod_123", name="Business")],
    )
    mock_stripe_price_retrieve = mocker.patch(
        "hushline.premium.stripe.Price.retrieve",
        side_effect=stripe_error_instance,
    )

    create_products_and_prices()

    # Check that the product creation was called
    assert mock_stripe_product_create.called
    assert mock_stripe_price_create.called

    # Check that stripe_product_id and stripe_price_id were set
    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None
    if not tier:
        return

    assert tier.stripe_product_id == "prod_123"
    assert tier.stripe_price_id == "price_123"

    # Test the case where the product already exists in Stripe

    tier.stripe_product_id = "prod_123"
    tier.stripe_price_id = None
    db.session.add(tier)
    db.session.commit()

    mock_stripe_product_retrieve.side_effect = None
    mock_stripe_product_retrieve.return_value = MagicMock(id="prod_123")
    mock_stripe_price_retrieve.side_effect = stripe_error_instance

    create_products_and_prices()

    # Check that the product creation was not called again
    assert mock_stripe_product_create.call_count == 1
    assert mock_stripe_price_create.call_count == 2

    # Check that stripe_product_id and stripe_price_id were set
    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None
    if not tier:
        return

    assert tier.stripe_product_id == "prod_123"
    assert tier.stripe_price_id == "price_123"


def test_update_price_existing(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = [MagicMock(id="price_123", unit_amount=2000)]

    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None
    if not tier:
        return

    update_price(tier)

    assert not mock_stripe.Price.create.called
    assert mock_stripe.Product.modify.called

    assert tier.stripe_price_id == "price_123"


def test_update_price_new(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = []
    mock_stripe.Price.create.return_value = MagicMock(id="price_123")

    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None
    if not tier:
        return

    update_price(tier)

    assert mock_stripe.Price.create.called
    assert mock_stripe.Product.modify.called

    assert tier.stripe_price_id == "price_123"


def test_create_customer(app: Flask, mock_stripe: MagicMock, user: User) -> None:
    mock_stripe.Customer.create.return_value = MagicMock(id="cus_123")

    create_customer(user)

    assert mock_stripe.Customer.create.called
    assert user.stripe_customer_id is not None

    # Check that the customer ID was saved to the database
    db.session.refresh(user)
    assert user.stripe_customer_id is not None


def test_get_subscription(app: Flask, mock_stripe: MagicMock, user: User) -> None:
    mock_stripe.Subscription.retrieve.return_value = MagicMock(id="sub_123")

    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = get_subscription(user)

    assert subscription is not None
    assert mock_stripe.Subscription.retrieve.called


# Webhook handler for customer.subscription.created
def test_handle_subscription_created(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.customer = "cus_123"
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.INCOMPLETE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = (datetime.now() + timedelta(days=30)).timestamp()
    subscription.current_period_start = datetime.now().timestamp()

    handle_subscription_created(subscription)

    assert user.stripe_subscription_id == "sub_123"
    assert not user.is_business_tier


# Webhook handler for customer.subscription.updated, when the status changes to active
def test_handle_subscription_updated_upgrade(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.ACTIVE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = (datetime.now() + timedelta(days=30)).timestamp()
    subscription.current_period_start = datetime.now().timestamp()

    handle_subscription_updated(subscription)

    assert user.is_business_tier


# Webhook handler for customer.subscription.updated, when the status changes to canceled
def test_handle_subscription_updated_downgrade(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.CANCELED.value
    subscription.cancel_at_period_end = True
    subscription.current_period_end = (datetime.now() + timedelta(days=30)).timestamp()
    subscription.current_period_start = datetime.now().timestamp()

    handle_subscription_updated(subscription)

    assert user.is_free_tier


# Webhook handler for customer.subscription.deleted
def test_handle_subscription_deleted(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"

    handle_subscription_deleted(subscription)

    assert user.is_free_tier
    assert user.stripe_subscription_id is None


# Webhook handler for invoice.created
def test_handle_invoice_created(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
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

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice is not None
    assert stripe_invoice.user_id == user.id
    assert stripe_invoice.total == 2000
    assert stripe_invoice.status == StripeInvoiceStatusEnum.OPEN
    assert stripe_invoice.hosted_invoice_url == "https://example.com"


# Webhook handler for invoice.updated
def test_handle_invoice_updated(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
    user.stripe_subscription_id = "sub_123"
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

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice is not None

    invoice.status = StripeInvoiceStatusEnum.PAID
    handle_invoice_updated(invoice)

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice is not None
    assert stripe_invoice.status == StripeInvoiceStatusEnum.PAID


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_post_user_already_on_business_tier(
    client: FlaskClient, user: User, business_tier: Tier
) -> None:
    user.set_business_tier()
    db.session.commit()

    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_process(
    client: FlaskClient, user: User, business_tier: Tier, mocker: MockFixture
) -> None:
    mocker.patch(
        "stripe.checkout.Session.create",
        return_value=MagicMock(url="https://checkout.stripe.com/session_123"),
    )
    mocker.patch(
        "stripe.Customer.create",
        return_value=MagicMock(id="cus_123"),
    )

    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == "https://checkout.stripe.com/session_123"

    # Send the webhook events
    subscription = MagicMock(
        id="sub_123",
        customer="cus_123",
        status=StripeSubscriptionStatusEnum.INCOMPLETE.value,
        cancel_at_period_end=False,
        current_period_end=(datetime.now() + timedelta(days=30)).timestamp(),
        current_period_start=datetime.now().timestamp(),
    )
    invoice = MagicMock(
        id="inv_123",
        customer="cus_123",
        hosted_invoice_url="https://stripe.com/invoice/inv_123",
        total=2000,
        status=StripeInvoiceStatusEnum.OPEN.value,
        lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
        subscription="sub_123",
    )

    handle_subscription_created(subscription)
    handle_invoice_created(invoice)
    invoice.status = StripeInvoiceStatusEnum.PAID.value
    handle_invoice_updated(invoice)
    subscription.status = StripeSubscriptionStatusEnum.ACTIVE.value
    handle_subscription_updated(subscription)

    # Check that the user is now on the business tier
    db.session.refresh(user)
    assert user.is_business_tier

    # And an invoice was created
    stripe_invoice = db.session.query(StripeInvoice).filter_by(user_id=user.id).one()
    assert stripe_invoice is not None


def test_disable_autorenew_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_autorenew_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 400
    assert response.json == {"success": False}


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_autorenew_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    assert user.stripe_subscription_cancel_at_period_end is False

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", return_value=MagicMock()
    )

    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert mock_stripe_modify.called

    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is True


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_autorenew_stripe_error(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    stripe_error_instance = MagicMock()
    stripe_error_instance.side_effect = stripe._error.StripeError("An error occurred")

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 400
    assert response.json == {"success": False}
    assert mock_stripe_modify.called


def test_enable_autorenew_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_autorenew_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 400
    assert response.json == {"success": False}


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_autorenew_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.stripe_subscription_cancel_at_period_end = True
    db.session.commit()

    assert user.stripe_subscription_cancel_at_period_end is True

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", return_value=MagicMock()
    )

    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert mock_stripe_modify.called

    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is False


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_autorenew_stripe_error(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    stripe_error_instance = MagicMock()
    stripe_error_instance.side_effect = stripe._error.StripeError("An error occurred")

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 400
    assert response.json == {"success": False}
    assert mock_stripe_modify.called


def test_cancel_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 400
    assert response.json == {"success": False}


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.set_business_tier()
    db.session.commit()

    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", return_value=MagicMock()
    )

    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert mock_stripe_delete.called

    # Send the webhook event
    handle_subscription_deleted(MagicMock(id="sub_123"))

    db.session.refresh(user)
    assert user.is_free_tier
    assert user.stripe_subscription_id is None


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_stripe_error(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.set_business_tier()
    db.session.commit()

    stripe_error_instance = MagicMock()
    stripe_error_instance.side_effect = stripe._error.StripeError("An error occurred")

    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 400
    assert response.json == {"success": False}
    assert mock_stripe_delete.called

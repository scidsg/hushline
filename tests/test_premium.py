import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from flask import Flask, get_flashed_messages, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture
from stripe import InvalidRequestError, SignatureVerificationError, StripeError

from hushline.db import db
from hushline.model import (
    StripeEvent,
    StripeEventStatusEnum,
    StripeInvoice,
    StripeInvoiceStatusEnum,
    StripeSubscriptionStatusEnum,
    Tier,
    User,
)
from hushline.premium import (
    create_customer,
    create_products_and_prices,
    get_business_price_string,
    get_subscription,
    handle_invoice_created,
    handle_invoice_updated,
    handle_subscription_created,
    handle_subscription_deleted,
    handle_subscription_updated,
    update_price,
    worker,
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


def test_create_products_and_prices(app: Flask, mocker: MockFixture) -> None:
    # Make sure we have a business tier
    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None

    # Make sure it has no Stripe IDs to start
    tier.stripe_product_id = None
    tier.stripe_price_id = None
    db.session.add(tier)
    db.session.commit()

    stripe_error_instance = InvalidRequestError("Invalid request", param="")

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
    assert tier.stripe_product_id == "prod_123"
    assert tier.stripe_price_id == "price_123"


def test_update_price_existing(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = [MagicMock(id="price_123", unit_amount=2000)]

    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None

    update_price(tier)

    assert not mock_stripe.Price.create.called
    assert mock_stripe.Product.modify.called

    assert tier.stripe_price_id == "price_123"


def test_update_price_new(app: Flask, mock_stripe: MagicMock) -> None:
    mock_stripe.Price.search.return_value = []
    mock_stripe.Price.create.return_value = MagicMock(id="price_123")

    tier = Tier.query.filter_by(name="Business").one()
    assert tier is not None

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
    assert user.stripe_customer_id == "cus_123"


def test_create_customer_updates_existing_customer(
    app: Flask, mock_stripe: MagicMock, user: User
) -> None:
    user.email = "user@example.com"
    user.stripe_customer_id = "cus_existing"
    db.session.commit()
    existing_customer = MagicMock(id="cus_existing")
    mock_stripe.Customer.modify.return_value = existing_customer

    returned_customer = create_customer(user)

    assert returned_customer is existing_customer
    mock_stripe.Customer.modify.assert_called_once_with("cus_existing", email="user@example.com")
    mock_stripe.Customer.create.assert_not_called()


def test_create_customer_recreates_when_modify_fails(
    app: Flask, mocker: MockFixture, user: User
) -> None:
    user.stripe_customer_id = "cus_stale"
    db.session.commit()
    modify_mock = mocker.patch(
        "hushline.premium.stripe.Customer.modify",
        side_effect=InvalidRequestError("invalid", param=""),
    )
    create_mock = mocker.patch(
        "hushline.premium.stripe.Customer.create",
        return_value=MagicMock(id="cus_new"),
    )

    returned_customer = create_customer(user)

    assert returned_customer.id == "cus_new"
    modify_mock.assert_called_once()
    create_mock.assert_called_once()
    db.session.refresh(user)
    assert user.stripe_customer_id == "cus_new"


def test_get_subscription(app: Flask, mock_stripe: MagicMock, user: User) -> None:
    mock_stripe.Subscription.retrieve.return_value = MagicMock(id="sub_123")

    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = get_subscription(user)

    assert subscription is not None
    assert mock_stripe.Subscription.retrieve.called


def test_get_business_price_string_formats(app: Flask, business_tier: Tier) -> None:
    business_tier.monthly_amount = 2000
    db.session.commit()
    assert get_business_price_string() == "20"

    business_tier.monthly_amount = 2050
    db.session.commit()
    assert get_business_price_string() == "20.5"


def test_get_business_price_string_missing_tier(app: Flask, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.Tier.business_tier", return_value=None)
    assert get_business_price_string() == "NA"


def test_create_products_and_prices_missing_business_tier(app: Flask, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.Tier.business_tier", return_value=None)
    create_products_and_prices()


def test_update_price_without_product_id_logs_and_returns(
    app: Flask, business_tier: Tier, mocker: MockFixture
) -> None:
    business_tier.stripe_product_id = None
    db.session.commit()
    logger = mocker.patch.object(app.logger, "error")

    update_price(business_tier)
    logger.assert_called_once()


def test_get_subscription_none_when_missing_subscription_id(app: Flask, user: User) -> None:
    user.stripe_subscription_id = None
    db.session.commit()
    assert get_subscription(user) is None


def test_handle_subscription_created(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.customer = "cus_123"
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.INCOMPLETE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = int((datetime.now() + timedelta(days=30)).timestamp())
    subscription.current_period_start = int(datetime.now().timestamp())

    handle_subscription_created(subscription)

    assert user.stripe_subscription_id == "sub_123"
    assert not user.is_business_tier


def test_handle_subscription_created_raises_for_missing_user(app: Flask) -> None:
    subscription = MagicMock()
    subscription.customer = "missing"
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.ACTIVE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = int((datetime.now() + timedelta(days=30)).timestamp())
    subscription.current_period_start = int(datetime.now().timestamp())

    with pytest.raises(ValueError, match="Could not find user with customer ID"):
        handle_subscription_created(subscription)


def test_handle_subscription_updated_upgrade(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.ACTIVE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = int((datetime.now() + timedelta(days=30)).timestamp())
    subscription.current_period_start = int(datetime.now().timestamp())

    handle_subscription_updated(subscription)

    assert user.is_business_tier


def test_handle_subscription_updated_downgrade(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"
    subscription.status = StripeSubscriptionStatusEnum.CANCELED.value
    subscription.cancel_at_period_end = True
    subscription.current_period_end = int((datetime.now() + timedelta(days=30)).timestamp())
    subscription.current_period_start = int(datetime.now().timestamp())

    handle_subscription_updated(subscription)

    assert user.is_free_tier


def test_handle_subscription_updated_raises_for_missing_subscription(app: Flask) -> None:
    subscription = MagicMock()
    subscription.id = "sub_missing"
    subscription.status = StripeSubscriptionStatusEnum.ACTIVE.value
    subscription.cancel_at_period_end = False
    subscription.current_period_end = int((datetime.now() + timedelta(days=30)).timestamp())
    subscription.current_period_start = int(datetime.now().timestamp())

    with pytest.raises(ValueError, match="Could not find user with subscription ID"):
        handle_subscription_updated(subscription)


def test_handle_subscription_deleted(app: Flask, user: User) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    subscription = MagicMock()
    subscription.id = "sub_123"

    handle_subscription_deleted(subscription)

    assert user.is_free_tier
    assert user.stripe_subscription_id is None


def test_handle_subscription_deleted_raises_for_missing_subscription(app: Flask) -> None:
    with pytest.raises(ValueError, match="Could not find user with subscription ID"):
        handle_subscription_deleted(MagicMock(id="sub_missing"))


def test_handle_invoice_created(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
    db.session.commit()

    handle_invoice_created(
        MagicMock(
            id="inv_123",
            customer="cus_123",
            hosted_invoice_url="https://example.com",
            total=2000,
            status=StripeInvoiceStatusEnum.OPEN.value,
            lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
            subscription="sub_123",
        )
    )

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice is not None
    assert stripe_invoice.user_id == user.id
    assert stripe_invoice.total == 2000
    assert stripe_invoice.status == StripeInvoiceStatusEnum.OPEN
    assert stripe_invoice.hosted_invoice_url == "https://example.com"


def test_handle_invoice_created_value_error_is_handled(app: Flask, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.StripeInvoice", side_effect=ValueError("bad invoice"))
    handle_invoice_created(MagicMock())


def test_handle_invoice_updated(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_123"
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    invoice = MagicMock(
        id="inv_123",
        customer="cus_123",
        hosted_invoice_url="https://example.com",
        total=2000,
        status=StripeInvoiceStatusEnum.OPEN.value,
        lines=MagicMock(data=[MagicMock(plan=MagicMock(product="prod_123"))]),
        subscription="sub_123",
    )
    handle_invoice_created(invoice)

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice is not None

    invoice.status = StripeInvoiceStatusEnum.PAID.value
    handle_invoice_updated(invoice)

    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id="inv_123").one()
    assert stripe_invoice.status == StripeInvoiceStatusEnum.PAID


def test_handle_invoice_updated_raises_for_missing_invoice(app: Flask) -> None:
    with pytest.raises(ValueError, match="Could not find invoice with ID"):
        handle_invoice_updated(
            MagicMock(id="inv_missing", status=StripeInvoiceStatusEnum.PAID.value, total=1)
        )


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
        current_period_end=int((datetime.now() + timedelta(days=30)).timestamp()),
        current_period_start=int(datetime.now().timestamp()),
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
    assert response.status_code == 302
    assert response.location == url_for("premium.index")

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ No active subscription found." in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_autorenew_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    assert user.stripe_subscription_cancel_at_period_end is False

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", return_value=MagicMock()
    )

    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_modify.called

    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is True

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "Autorenew has been disabled." in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_autorenew_stripe_error(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    stripe_error_instance = StripeError("An error occurred")

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.disable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_modify.called

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ Something went wrong while disabling autorenew." in flashed_messages


def test_enable_autorenew_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_autorenew_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ No active subscription found." in flashed_messages


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
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_modify.called

    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is False

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "Autorenew has been enabled." in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_autorenew_stripe_error(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()

    stripe_error_instance = StripeError("An error occurred")

    mock_stripe_modify = mocker.patch(
        "hushline.premium.stripe.Subscription.modify", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.enable_autorenew"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_modify.called

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ Something went wrong while enabling autorenew." in flashed_messages


def test_cancel_no_user_in_session(client: FlaskClient) -> None:
    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_no_subscription(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ No active subscription found." in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_success(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.set_business_tier()
    db.session.commit()

    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", return_value=MagicMock()
    )

    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_delete.called

    # Send the webhook event
    handle_subscription_deleted(MagicMock(id="sub_123"))

    db.session.refresh(user)
    assert user.is_free_tier
    assert user.stripe_subscription_id is None

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "💔 Sorry to see you go!" in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_cancel_stripe_error(client: FlaskClient, user: User, mocker: MockFixture) -> None:
    user.stripe_subscription_id = "sub_123"
    user.set_business_tier()
    db.session.commit()

    stripe_error_instance = StripeError("An error occurred")

    mock_stripe_delete = mocker.patch(
        "hushline.premium.stripe.Subscription.delete", side_effect=stripe_error_instance
    )

    response = client.post(url_for("premium.cancel"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")
    assert mock_stripe_delete.called

    # Check flash message
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ Something went wrong while canceling your subscription." in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_select_tier_redirects_when_onboarding_incomplete(
    client: FlaskClient, user: User
) -> None:
    user.onboarding_complete = False
    db.session.commit()

    response = client.get(url_for("premium.select_tier"))
    assert response.status_code == 302
    assert response.location == url_for("onboarding")


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_select_free_sets_free_tier_when_unset(client: FlaskClient, user: User) -> None:
    user.tier_id = None
    db.session.commit()

    response = client.post(url_for("premium.select_free"))
    assert response.status_code == 302
    assert response.location == url_for("inbox")

    db.session.refresh(user)
    assert user.is_free_tier


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_status_business_user_flashes_success(client: FlaskClient, user: User) -> None:
    user.set_business_tier()
    db.session.commit()

    response = client.get(url_for("premium.status"))
    assert response.status_code == 200
    assert response.json == {"tier_id": user.tier_id}

    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "🔥 Congratulations, you've upgraded your account!" in flashed_messages


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_index_warns_on_incomplete_subscription(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    user.stripe_subscription_id = "sub_123"
    db.session.commit()
    mocker.patch("hushline.premium.get_subscription", return_value={"status": "incomplete"})

    response = client.get(url_for("premium.index"))
    assert response.status_code == 200
    with client.session_transaction():
        flashed_messages = get_flashed_messages()
    assert "⚠️ Your subscription is incomplete. Please try again." in flashed_messages


@pytest.mark.parametrize(
    ("endpoint", "method"),
    [
        ("premium.index", "get"),
        ("premium.select_tier", "get"),
        ("premium.select_free", "post"),
        ("premium.upgrade", "post"),
        ("premium.disable_autorenew", "post"),
        ("premium.enable_autorenew", "post"),
        ("premium.cancel", "post"),
        ("premium.status", "get"),
    ],
)
def test_premium_routes_redirect_to_login_when_user_missing_after_auth(
    client: FlaskClient, endpoint: str, method: str
) -> None:
    with client.session_transaction() as session:
        session["user_id"] = 999999
        session["is_authenticated"] = True
        session["username"] = "ghost"

    if method == "post":
        response = client.post(url_for(endpoint), follow_redirects=False)
    else:
        response = client.get(url_for(endpoint), follow_redirects=False)

    assert response.status_code == 302
    assert response.location == url_for("login")


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_select_tier_renders_for_complete_user(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = True
    db.session.commit()
    response = client.get(url_for("premium.select_tier"))
    assert response.status_code == 200


@pytest.mark.usefixtures("_authenticated_user")
def test_premium_waiting_page_renders(client: FlaskClient) -> None:
    response = client.get(url_for("premium.waiting"))
    assert response.status_code == 200


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_missing_business_tier(client: FlaskClient, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.Tier.business_tier", return_value=None)
    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_missing_business_price_id(client: FlaskClient, business_tier: Tier) -> None:
    business_tier.stripe_price_id = None
    db.session.commit()
    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_create_customer_failure(client: FlaskClient, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.create_customer", side_effect=StripeError("boom"))
    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 302
    assert response.location == url_for("premium.index")


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_checkout_creation_failure(client: FlaskClient, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.create_customer")
    mocker.patch("hushline.premium.stripe.checkout.Session.create", side_effect=StripeError("boom"))
    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 500


@pytest.mark.usefixtures("_authenticated_user")
def test_upgrade_checkout_session_without_url_returns_500(
    client: FlaskClient, mocker: MockFixture
) -> None:
    mocker.patch("hushline.premium.create_customer")
    mocker.patch(
        "hushline.premium.stripe.checkout.Session.create", return_value=MagicMock(url=None)
    )
    response = client.post(url_for("premium.upgrade"))
    assert response.status_code == 500


def test_premium_webhook_rejects_invalid_payload(client: FlaskClient, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.stripe.Webhook.construct_event", side_effect=ValueError("bad"))

    response = client.post(
        url_for("premium.webhook"),
        data=b"{}",
        headers={"STRIPE_SIGNATURE": "sig"},
    )
    assert response.status_code == 400
    assert response.json == {"success": False}


def test_premium_webhook_rejects_invalid_signature(
    client: FlaskClient, mocker: MockFixture
) -> None:
    mocker.patch(
        "hushline.premium.stripe.Webhook.construct_event",
        side_effect=SignatureVerificationError("bad sig", sig_header="sig"),
    )

    response = client.post(
        url_for("premium.webhook"),
        data=b"{}",
        headers={"STRIPE_SIGNATURE": "sig"},
    )
    assert response.status_code == 400
    assert response.json == {"success": False}


def test_premium_webhook_ignores_duplicate_event(client: FlaskClient, mocker: MockFixture) -> None:
    existing_event = StripeEvent(MagicMock(id="evt_dup", created=123, type="invoice.created"))
    db.session.add(existing_event)
    db.session.commit()
    mocker.patch(
        "hushline.premium.stripe.Webhook.construct_event",
        return_value=MagicMock(id="evt_dup", created=123, type="invoice.created"),
    )

    response = client.post(
        url_for("premium.webhook"),
        data=b"{}",
        headers={"STRIPE_SIGNATURE": "sig"},
    )
    assert response.status_code == 200
    assert response.json == {"success": True}
    assert db.session.scalar(db.select(db.func.count(StripeEvent.id))) == 1


def test_premium_webhook_stores_new_event(client: FlaskClient, mocker: MockFixture) -> None:
    event = MagicMock(id="evt_new", created=456, type="invoice.updated")
    mocker.patch("hushline.premium.stripe.Webhook.construct_event", return_value=event)

    response = client.post(
        url_for("premium.webhook"),
        data=b"{}",
        headers={"STRIPE_SIGNATURE": "sig"},
    )
    assert response.status_code == 200
    assert response.json == {"success": True}

    stored_event = db.session.scalar(db.select(StripeEvent).filter_by(event_id="evt_new"))
    assert stored_event is not None
    assert stored_event.event_type == "invoice.updated"


@pytest.mark.asyncio()
async def test_worker_processes_subscription_created_event(app: Flask, mocker: MockFixture) -> None:
    pending = StripeEvent(
        MagicMock(id="evt_worker_created", created=1, type="customer.subscription.created")
    )
    pending.event_data = json.dumps({"id": "evt_worker_created"})
    pending.status = StripeEventStatusEnum.PENDING
    db.session.add(pending)
    db.session.commit()

    mocker.patch("hushline.premium.sa.create_engine", return_value=MagicMock())
    inspect_obj = MagicMock()
    inspect_obj.has_table.return_value = True
    mocker.patch("hushline.premium.sa.inspect", return_value=inspect_obj)

    subscription_obj = MagicMock()
    mocker.patch(
        "hushline.premium.stripe.Subscription.construct_from", return_value=subscription_obj
    )
    handle_created = mocker.patch("hushline.premium.handle_subscription_created")
    mocker.patch(
        "hushline.premium.stripe.Event.construct_from",
        return_value=MagicMock(
            type="customer.subscription.created",
            data=MagicMock(object={"id": "sub_123"}),
        ),
    )

    async def _stop_sleep(_seconds: int) -> None:
        raise RuntimeError("stop worker")

    mocker.patch("hushline.premium.asyncio.sleep", side_effect=_stop_sleep)

    with pytest.raises(RuntimeError, match="stop worker"):
        await worker(app)

    db.session.refresh(pending)
    assert pending.status == StripeEventStatusEnum.FINISHED
    handle_created.assert_called_once_with(subscription_obj)


@pytest.mark.asyncio()
async def test_worker_marks_event_error_when_handler_raises(
    app: Flask, mocker: MockFixture
) -> None:
    pending = StripeEvent(MagicMock(id="evt_worker_error", created=1, type="invoice.updated"))
    pending.event_data = json.dumps({"id": "evt_worker_error"})
    pending.status = StripeEventStatusEnum.PENDING
    db.session.add(pending)
    db.session.commit()

    mocker.patch("hushline.premium.sa.create_engine", return_value=MagicMock())
    inspect_obj = MagicMock()
    inspect_obj.has_table.return_value = True
    mocker.patch("hushline.premium.sa.inspect", return_value=inspect_obj)

    invoice_obj = MagicMock()
    mocker.patch("hushline.premium.stripe.Invoice.construct_from", return_value=invoice_obj)
    mocker.patch(
        "hushline.premium.handle_invoice_updated", side_effect=ValueError("invoice failed")
    )
    mocker.patch(
        "hushline.premium.stripe.Event.construct_from",
        return_value=MagicMock(type="invoice.updated", data=MagicMock(object={"id": "inv_123"})),
    )

    async def _stop_sleep(_seconds: int) -> None:
        raise RuntimeError("stop worker")

    mocker.patch("hushline.premium.asyncio.sleep", side_effect=_stop_sleep)

    with pytest.raises(RuntimeError, match="stop worker"):
        await worker(app)

    db.session.refresh(pending)
    assert pending.status == StripeEventStatusEnum.ERROR
    assert pending.error_message == "invoice failed"


@pytest.mark.asyncio()
async def test_worker_waits_for_tables_before_starting(app: Flask, mocker: MockFixture) -> None:
    mocker.patch("hushline.premium.sa.create_engine", return_value=MagicMock())
    inspect_obj = MagicMock()
    inspect_obj.has_table.return_value = False
    mocker.patch("hushline.premium.sa.inspect", return_value=inspect_obj)

    async def _stop_sleep(_seconds: int) -> None:
        raise RuntimeError("stop waiting")

    mocker.patch("hushline.premium.asyncio.sleep", side_effect=_stop_sleep)

    with pytest.raises(RuntimeError, match="stop waiting"):
        await worker(app)

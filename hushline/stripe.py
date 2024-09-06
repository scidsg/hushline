import stripe
from flask import current_app

from .db import db
from .model import Tier, User


def init_stripe() -> None:
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]


def create_products_and_prices() -> None:
    # Make sure the products and prices are created in Stripe
    tiers = db.session.query(Tier).all()
    for tier in tiers:
        if tier.monthly_amount == 0:
            continue

        # Check if the product exists
        create_product = False
        if tier.stripe_product_id is None:
            create_product = True
        else:
            try:
                product = stripe.Product.retrieve(tier.stripe_product_id)
            except stripe._error.InvalidRequestError:
                create_product = True

        if create_product:
            current_app.logger.info(f"Creating product for tier: {tier.name}")
            product = stripe.Product.create(name=tier.name, type="service")
            tier.stripe_product_id = product.id
            db.session.add(tier)
            db.session.commit()

        # Check if the price exists
        create_price = False
        if tier.stripe_price_id is None:
            create_price = True
        else:
            try:
                price = stripe.Price.retrieve(tier.stripe_price_id)
            except stripe._error.InvalidRequestError:
                create_price = True

        if create_price:
            current_app.logger.info(f"Creating price for tier: {tier.name}")
            price = stripe.Price.create(
                product=product.id,
                unit_amount=tier.monthly_amount,
                currency="usd",
                recurring={"interval": "month"},
            )
            tier.stripe_price_id = price.id
            db.session.add(tier)
            db.session.commit()


def update_price(tier: Tier) -> None:
    current_app.logger.info(f"Updating price for tier {tier.name} to {tier.monthly_amount}")

    # See if we already have an appropriate price for this product
    prices = stripe.Price.search(query=f'product:"{tier.stripe_product_id}"')
    found_price_id = None
    for price in prices:
        if price.unit_amount == tier.monthly_amount:
            found_price_id = price.id
            break

    # If we found it, use it
    if found_price_id is not None:
        tier.stripe_price_id = found_price_id
        db.session.add(tier)
        db.session.commit()

        stripe.Product.modify(tier.stripe_product_id, default_price=found_price_id)
        return

    # Otherwise, create a new price
    price = stripe.Price.create(
        product=tier.stripe_product_id,
        unit_amount=tier.monthly_amount,
        currency="usd",
        recurring={"interval": "month"},
    )
    tier.stripe_price_id = price.id
    db.session.add(tier)
    db.session.commit()

    stripe.Product.modify(tier.stripe_product_id, default_price=price.id)


def create_customer(user: User) -> stripe.Customer:
    email: str = user.email if user.email is not None else ""

    if user.stripe_customer_id is None:
        stripe_customer = stripe.Customer.create(email=email)
        user.stripe_customer_id = stripe_customer.id
        db.session.add(user)
        db.session.commit()
        return stripe_customer

    return stripe.Customer.modify(user.stripe_customer_id, email=email)


def create_subscription(user: User, tier: Tier) -> stripe.Subscription:
    stripe_customer = create_customer(user)

    # Create a subscription
    stripe_subscription = stripe.Subscription.create(
        customer=stripe_customer.id,
        items=[{"price": tier.stripe_price_id}],
        payment_behavior="default_incomplete",
    )
    user.stripe_subscription_id = stripe_subscription.id
    db.session.add(user)
    db.session.commit()

    return stripe_subscription


def get_latest_invoice_payment_intent_client_secret(
    subscription: stripe.Subscription,
) -> str | None:
    if subscription.latest_invoice is None:
        return None

    stripe_invoice = stripe.Invoice.retrieve(str(subscription.latest_invoice))
    if stripe_invoice.payment_intent is None:
        return None

    stripe_payment_intent = stripe.PaymentIntent.retrieve(str(stripe_invoice.payment_intent))
    return stripe_payment_intent.client_secret

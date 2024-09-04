import stripe
from flask import current_app

from .db import db
from .model import Tier


def init_stripe() -> None:
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

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
                product=tier.stripe_product_id,
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

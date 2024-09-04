import stripe
from flask import Flask

from .db import db
from .model import Tier


def init_stripe(app: Flask) -> None:
    stripe.api_key = app.config["STRIPE_SECRET_KEY"]

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
            app.logger.info(f"Creating product for tier: {tier.name}")
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
            app.logger.info(f"Creating price for tier: {tier.name}")
            price = stripe.Price.create(
                product=tier.stripe_product_id,
                unit_amount=tier.monthly_amount,
                currency="usd",
                recurring={"interval": "month"},
            )
            tier.stripe_price_id = price.id
            db.session.add(tier)
            db.session.commit()

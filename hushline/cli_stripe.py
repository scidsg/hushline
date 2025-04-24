import asyncio

from flask import Flask
from flask.cli import AppGroup

from hushline import premium
from hushline.db import db
from hushline.model import Tier


def register_stripe_commands(app: Flask) -> None:
    stripe_cli = AppGroup("stripe", help="Stripe commands")

    @stripe_cli.command("configure")
    def configure() -> None:
        """Configure Stripe and premium tiers"""
        # Make sure tiers exist
        free_tier = Tier.free_tier()
        if not free_tier:
            free_tier = Tier(name="Free", monthly_amount=0)
            db.session.add(free_tier)
            db.session.commit()
        business_tier = Tier.business_tier()
        if not business_tier:
            business_tier = Tier(name="Business", monthly_amount=2000)
            db.session.add(business_tier)
            db.session.commit()

        # Configure Stripe
        if app.config.get("STRIPE_SECRET_KEY"):
            premium.init_stripe()
            premium.create_products_and_prices()
        else:
            app.logger.info("Skipping Stripe configuration because STRIPE_SECRET_KEY is not set")

    @stripe_cli.command("start-worker")
    def start_worker() -> None:
        """Start the Stripe worker"""
        if not app.config["STRIPE_SECRET_KEY"]:
            app.logger.error("Cannot start the Stripe worker without a STRIPE_SECRET_KEY")
            return

        with app.app_context():
            asyncio.run(premium.worker(app))

    app.cli.add_command(stripe_cli)

import click
from flask import Flask
from flask.cli import AppGroup

from hushline.billing import get_provider
from hushline.db import db
from hushline.model import Tier, User


def initialize_tiers() -> None:
    if Tier.free_tier() is None:
        free = Tier(name="Free", monthly_amount=0)
        free.id = Tier.free_tier_id()
        db.session.add(free)
    if Tier.business_tier() is None:
        business = Tier(name="Business", monthly_amount=2000)
        business.id = Tier.business_tier_id()
        db.session.add(business)
    db.session.commit()


def register_billing_commands(app: Flask) -> None:
    billing_cli = AppGroup("billing", help="Self-hosted entitlement administration")

    @billing_cli.command("configure")
    def configure() -> None:
        """Initialize local tiers without contacting a payment service."""
        initialize_tiers()
        click.echo("Local entitlement tiers initialized.")

    @billing_cli.command("set-tier")
    @click.argument("user_id", type=int)
    @click.argument("tier", type=click.Choice(["free", "business"]))
    def set_tier(user_id: int, tier: str) -> None:
        """Grant or revoke an existing account's locally managed entitlement."""
        if get_provider().name != "manual":
            raise click.ClickException("This command requires BILLING_PROVIDER=manual")
        user = db.session.scalar(db.select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise click.ClickException("Account not found")
        # A configuration change must never cancel or overwrite a real subscription.
        if user.stripe_customer_id or user.stripe_subscription_id:
            raise click.ClickException("Resolve the account's existing provider billing first")
        target = Tier.free_tier() if tier == "free" else Tier.business_tier()
        if target is None:
            raise click.ClickException("Initialize tiers with flask billing configure first")
        user.tier_id = target.id
        db.session.commit()
        click.echo(f"Account {user_id} now has the {tier} entitlement; no payment was processed.")

    app.cli.add_command(billing_cli)

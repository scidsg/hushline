import asyncio
import json
import threading
from typing import Tuple

import stripe
from flask import (
    Blueprint,
    Flask,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import desc
from werkzeug.wrappers.response import Response

from .db import db
from .model import StripeEvent, StripeInvoice, StripeInvoiceStatusEnum, Tier, User
from .utils import authentication_required

FREE_TIER = 1
BUSINESS_TIER = 2


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


def get_subscription(user: User) -> stripe.Subscription | None:
    if user.stripe_subscription_id is None:
        return None

    return stripe.Subscription.retrieve(user.stripe_subscription_id)


def handle_subscription_created(subscription: stripe.Subscription) -> None:
    # Subscription is created, but not yet paid
    user = db.session.query(User).filter_by(stripe_customer_id=subscription.customer).first()
    if user:
        user.stripe_subscription_id = subscription.id
        db.session.commit()
    else:
        raise ValueError(f"Could not find user with customer ID {subscription.customer}")


def handle_subscription_updated(subscription: stripe.Subscription) -> None:
    # If subscription changes to cancel or unpaid, downgrade user
    user = db.session.query(User).filter_by(stripe_subscription_id=subscription.id).first()
    if user:
        if subscription.status in ["canceled", "unpaid"]:
            user.tier_id = FREE_TIER
        db.session.commit()
    else:
        raise ValueError(f"Could not find user with subscription ID {subscription.id}")


def handle_subscription_deleted(subscription: stripe.Subscription) -> None:
    # If subscription is deleted, downgrade user
    user = db.session.query(User).filter_by(stripe_subscription_id=subscription.id).first()
    if user:
        user.tier_id = FREE_TIER
        user.stripe_subscription_id = None
        db.session.commit()
    else:
        raise ValueError(f"Could not find user with subscription ID {subscription.id}")


def handle_invoice_created(invoice: stripe.Invoice) -> None:
    try:
        new_invoice = StripeInvoice(invoice)
        db.session.add(new_invoice)
        db.session.commit()
    except ValueError as e:
        current_app.logger.error(f"Error creating invoice: {e}")


def handle_invoice_payment_succeeded(invoice: stripe.Invoice) -> None:
    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id=invoice.id).first()
    if stripe_invoice:
        stripe_invoice.amount_paid = invoice.amount_paid
        stripe_invoice.amount_remaining = invoice.amount_remaining
        stripe_invoice.status = StripeInvoiceStatusEnum(invoice.status)
        db.session.commit()

        # Invoice has been paid, so make sure the user is upgraded
        user = db.session.query(User).filter_by(stripe_subscription_id=invoice.subscription).first()
        if user:
            user.tier_id = BUSINESS_TIER
            db.session.commit()
    else:
        raise ValueError(f"Could not find invoice with ID {invoice.id}")


def handle_invoice_payment_failed(invoice: stripe.Invoice) -> None:
    stripe_invoice = db.session.query(StripeInvoice).filter_by(invoice_id=invoice.id).first()
    if stripe_invoice:
        stripe_invoice.amount_paid = invoice.amount_paid
        stripe_invoice.amount_remaining = invoice.amount_remaining
        stripe_invoice.status = StripeInvoiceStatusEnum(invoice.status)
        db.session.commit()
    else:
        raise ValueError(f"Could not find invoice with ID {invoice.id}")


async def worker(app: Flask) -> None:
    with app.app_context():
        while True:
            stripe_event = (
                db.session.query(StripeEvent)
                .filter_by(status="pending")
                .order_by(StripeEvent.created_at)
                .first()
            )
            if not stripe_event:
                await asyncio.sleep(10)
                continue

            stripe_event.status = "in_progress"
            db.session.add(stripe_event)
            db.session.commit()

            event_json = json.loads(stripe_event.event_data)
            event = stripe.Event.construct_from(event_json, current_app.config["STRIPE_SECRET_KEY"])

            current_app.logger.info(
                f"Processing event {stripe_event.event_type} ({stripe_event.event_id})"
            )
            try:
                # subscription events
                if event.type.startswith("customer.subscription."):
                    subscription: stripe.Subscription = stripe.Subscription.construct_from(
                        event.data.object, current_app.config["STRIPE_SECRET_KEY"]
                    )
                    if event.type == "customer.subscription.created":
                        handle_subscription_created(subscription)
                    elif event.type == "customer.subscription.updated":
                        handle_subscription_updated(subscription)
                    elif event.type == "customer.subscription.deleted":
                        handle_subscription_deleted(subscription)
                # invoice events
                elif event.type.startswith("invoice."):
                    invoice: stripe.Invoice = stripe.Invoice.construct_from(
                        event.data.object, current_app.config["STRIPE_SECRET_KEY"]
                    )
                    if event.type == "invoice.created":
                        handle_invoice_created(invoice)
                    elif event.type == "invoice.payment_succeeded":
                        handle_invoice_payment_succeeded(invoice)
                    elif event.type == "invoice.payment_failed":
                        handle_invoice_payment_failed(invoice)

            except Exception as e:
                current_app.logger.error(
                    f"Error processing event {stripe_event.event_type} ({stripe_event.event_id}): {e}\n{stripe_event.event_data}"  # noqa: E501
                )
                stripe_event.status = "error"
                db.session.add(stripe_event)
                db.session.commit()
                continue

            stripe_event.status = "finished"
            db.session.add(stripe_event)
            db.session.commit()


def start_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def create_blueprint(app: Flask) -> Blueprint:
    # Create a new asyncio event loop
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_event_loop, args=(loop,), daemon=True)
    t.start()

    # Schedule the worker task
    loop.call_soon_threadsafe(loop.create_task, worker(app))

    # Now define the blueprint
    bp = Blueprint("premium", __file__, url_prefix="/premium")

    @bp.route("/", methods=["GET"])
    @authentication_required
    def index() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        current_app.logger.info(f"User: {user}")
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # Check if we have an incomplete subscription
        stripe_subscription = get_subscription(user)
        if stripe_subscription and stripe_subscription["status"] == "incomplete":
            flash("⚠️ Your subscription is incomplete. Please try again.", "warning")

        # Load the user's invoices
        invoices = (
            db.session.query(StripeInvoice)
            .filter_by(user_id=user.id)
            .order_by(desc(StripeInvoice.created_at))
            .all()
        )

        return render_template("premium.html", user=user, invoices=invoices)

    @bp.route("/upgrade", methods=["GET", "POST"])
    @authentication_required
    def upgrade() -> Response | str:
        if request.method == "GET":
            return redirect(url_for("premium.index"))

        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # If the user is already on the business tier
        if user.tier_id == BUSINESS_TIER:
            flash("👍 You're already upgraded.")
            return redirect(url_for("premium.index"))

        # Select the business tier
        business_tier = db.session.query(Tier).get(BUSINESS_TIER)
        if not business_tier:
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        # Subscribe the user to the business tier
        try:
            stripe_subscription = create_subscription(user, business_tier)
            user.stripe_subscription_id = stripe_subscription.id
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Stripe error: {e}")
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        return render_template(
            "premium-subscribe.html",
            user=user,
            tier=business_tier,
            stripe_subscription_id=stripe_subscription.id,
            stripe_client_secret=get_latest_invoice_payment_intent_client_secret(
                stripe_subscription
            ),
            stripe_publishable_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY"),
        )

    @bp.route("/downgrade", methods=["POST"])
    @authentication_required
    def downgrade() -> Response | str | Tuple[Response | str, int]:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.stripe_subscription_id:
            try:
                # Cancel the subscription
                stripe.Subscription.delete(user.stripe_subscription_id)

                # Downgrade the user (the subscription ID will get removed in the webhook)
                user.tier_id = FREE_TIER
                db.session.add(user)
                db.session.commit()

                current_app.logger.info(
                    f"Subscription {user.stripe_subscription_id} canceled for user {user.id}"
                )

                flash("💔 Sorry to see you go!")
                return jsonify(success=True)
            except stripe._error.StripeError as e:
                current_app.logger.error(f"Stripe error: {e}")
                return jsonify(success=False), 400

        return jsonify(success=False), 400

    @bp.route("/status.json", methods=["GET"])
    @authentication_required
    def statis() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.tier_id == BUSINESS_TIER:
            flash("🔥 Congratulations, you've upgraded your account!")

        return jsonify({"tier_id": user.tier_id})

    @bp.route("/webhook", methods=["POST"])
    def webhook() -> Response | str | Tuple[Response | str, int]:
        payload = request.data
        sig_header = request.headers["STRIPE_SIGNATURE"]

        # Parse the event
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, current_app.config.get("STRIPE_WEBHOOK_SECRET")
            )
        except ValueError as e:
            current_app.logger.error(f"Invalid payload: {e}")
            return jsonify(success=False), 400
        except stripe._error.SignatureVerificationError as e:
            current_app.logger.error(f"Error verifying webhook signature: {e}")
            return jsonify(success=False), 400

        # Have we seen this one before?
        stripe_event = db.session.query(StripeEvent).filter_by(event_id=event.id).first()
        if stripe_event:
            current_app.logger.info(f"Event already seen: {event}")
            return jsonify(success=True)

        # Log it
        current_app.logger.info(f"Received event: {event.type}")
        stripe_event = StripeEvent(event)
        db.session.add(stripe_event)
        db.session.commit()

        return jsonify(success=True)

    return bp

import asyncio
import json
from datetime import datetime
from typing import Tuple

import stripe
from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers.response import Response

from .db import db
from .model import (
    StripeEvent,
    StripeEventStatusEnum,
    StripeInvoice,
    StripeInvoiceStatusEnum,
    StripeSubscriptionStatusEnum,
    Tier,
    User,
)
from .utils import authentication_required


def init_stripe() -> None:
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]


def create_products_and_prices() -> None:
    current_app.logger.info("Creating products and prices")

    # Make sure the products and prices are created in Stripe
    business_tier = Tier.business_tier()
    if not business_tier:
        current_app.logger.error("Could not find business tier")
        return

    # Check if the product exists in the db
    create_product = False
    if business_tier.stripe_product_id is None:
        create_product = True
    else:
        try:
            stripe_product = stripe.Product.retrieve(business_tier.stripe_product_id)
        except stripe._error.InvalidRequestError:
            create_product = True

    if create_product:
        # Do we already have a product in Stripe?
        found = False
        stripe_products = stripe.Product.list(limit=100)
        for stripe_product in stripe_products:
            if stripe_product.name == business_tier.name:
                current_app.logger.info(f"Found Stripe product for tier: {business_tier.name}")
                found = True
                business_tier.stripe_product_id = stripe_product.id
                db.session.add(business_tier)
                db.session.commit()
                break

        # Create a product if we didn't find one
        if not found:
            current_app.logger.info(f"Creating Stripe product for tier: {business_tier.name}")
            stripe_product = stripe.Product.create(
                name=business_tier.name,
                type="service",
                tax_code="txcd_10103001",  # Software as a service (SaaS) - business use
            )
            business_tier.stripe_product_id = stripe_product.id
            db.session.add(business_tier)
            db.session.commit()
    else:
        current_app.logger.info(f"Product already exists for tier: {business_tier.name}")

    # Check if the price exists
    create_price = False
    if business_tier.stripe_price_id is None:
        create_price = True
    else:
        try:
            price = stripe.Price.retrieve(business_tier.stripe_price_id)
        except stripe._error.InvalidRequestError:
            create_price = True

    if create_price:
        # Do we already have a price in Stripe?
        found = False
        if stripe_product.default_price:
            try:
                stripe_price = stripe.Price.retrieve(str(stripe_product.default_price))
                current_app.logger.info(f"Found Stripe price for tier: {business_tier.name}")
                business_tier.stripe_price_id = stripe_price.id
                if stripe_price.unit_amount:
                    business_tier.monthly_amount = stripe_price.unit_amount
                db.session.add(business_tier)
                db.session.commit()
                found = True
            except stripe._error.InvalidRequestError:
                found = False

        # Create a price if we didn't find one
        if not found:
            current_app.logger.info(f"Creating price for tier: {business_tier.name}")
            price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=business_tier.monthly_amount,
                currency="usd",
                recurring={"interval": "month"},
            )
            business_tier.stripe_price_id = price.id
            db.session.add(business_tier)
            db.session.commit()
    else:
        current_app.logger.info(f"Price already exists for tier: {business_tier.name}")


def update_price(tier: Tier) -> None:
    current_app.logger.info(f"Updating price for tier {tier.name} to {tier.monthly_amount}")

    if not tier.stripe_product_id:
        current_app.logger.error(f"Tier {tier.name} does not have a product ID")
        return

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

    if user.stripe_customer_id is not None:
        try:
            return stripe.Customer.modify(user.stripe_customer_id, email=email)
        except stripe._error.InvalidRequestError:
            user.stripe_customer_id = None

    stripe_customer = stripe.Customer.create(email=email)
    user.stripe_customer_id = stripe_customer.id
    db.session.add(user)
    db.session.commit()
    return stripe_customer


def get_subscription(user: User) -> stripe.Subscription | None:
    if user.stripe_subscription_id is None:
        return None

    return stripe.Subscription.retrieve(user.stripe_subscription_id)


def get_business_price_string() -> str:
    business_tier = Tier.business_tier()
    if not business_tier:
        current_app.logger.error("Could not find business tier")
        return "NA"

    business_price = f"{business_tier.monthly_amount / 100:.2f}"
    if business_price.endswith(".00"):
        business_price = business_price[:-3]
    elif business_price.endswith("0"):
        business_price = business_price[:-1]

    return business_price


def handle_subscription_created(subscription: stripe.Subscription) -> None:
    # customer.subscription.created

    user = db.session.scalars(
        db.select(User).filter_by(stripe_customer_id=subscription.customer)
    ).one_or_none()
    if user:
        user.stripe_subscription_id = subscription.id
        user.stripe_subscription_status = StripeSubscriptionStatusEnum(subscription.status)
        user.stripe_subscription_cancel_at_period_end = subscription.cancel_at_period_end
        user.stripe_subscription_current_period_end = datetime.fromtimestamp(
            subscription.current_period_end
        )
        user.stripe_subscription_current_period_start = datetime.fromtimestamp(
            subscription.current_period_start
        )
        db.session.commit()
    else:
        raise ValueError(f"Could not find user with customer ID {subscription.customer}")


def handle_subscription_updated(subscription: stripe.Subscription) -> None:
    # customer.subscription.updated

    # If subscription changes to cancel or unpaid, downgrade user
    user = db.session.scalars(
        db.select(User).filter_by(stripe_subscription_id=subscription.id)
    ).one_or_none()
    if user:
        user.stripe_subscription_status = StripeSubscriptionStatusEnum(subscription.status)
        user.stripe_subscription_cancel_at_period_end = subscription.cancel_at_period_end
        user.stripe_subscription_current_period_end = datetime.fromtimestamp(
            subscription.current_period_end
        )
        user.stripe_subscription_current_period_start = datetime.fromtimestamp(
            subscription.current_period_start
        )

        current_app.logger.info("status is: " + subscription.status)
        if subscription.status in ["active", "trialing"]:
            user.set_business_tier()
        else:
            user.set_free_tier()

        db.session.commit()
    else:
        raise ValueError(f"Could not find user with subscription ID {subscription.id}")


def handle_subscription_deleted(subscription: stripe.Subscription) -> None:
    # customer.subscription.deleted

    user = db.session.scalars(
        db.select(User).filter_by(stripe_subscription_id=subscription.id)
    ).one_or_none()
    if user:
        user.set_free_tier()
        user.stripe_subscription_id = None
        user.stripe_subscription_status = None
        user.stripe_subscription_cancel_at_period_end = None
        user.stripe_subscription_current_period_end = None
        user.stripe_subscription_current_period_start = None
        db.session.commit()
    else:
        raise ValueError(f"Could not find user with subscription ID {subscription.id}")


def handle_invoice_created(invoice: stripe.Invoice) -> None:
    # invoice.created

    try:
        new_invoice = StripeInvoice(invoice)
    except ValueError as e:
        current_app.logger.error(f"Error creating invoice: {e}")

    db.session.add(new_invoice)
    db.session.commit()


def handle_invoice_updated(invoice: stripe.Invoice) -> None:
    # invoice.updated

    stripe_invoice = db.session.scalars(
        db.select(StripeInvoice).filter_by(invoice_id=invoice.id)
    ).one_or_none()
    if stripe_invoice:
        stripe_invoice.total = invoice.total
        stripe_invoice.status = StripeInvoiceStatusEnum(invoice.status)
        db.session.commit()
    else:
        raise ValueError(f"Could not find invoice with ID {invoice.id}")


async def worker(app: Flask) -> None:
    current_app.logger.error("Starting worker")
    with app.app_context():
        while True:
            with db.session.begin() as transaction:  # Start a transaction block
                stripe_event = transaction.session.scalars(
                    db.select(StripeEvent)
                    .filter_by(status=StripeEventStatusEnum.PENDING)
                    .order_by(StripeEvent.event_created.asc())
                    .with_for_update()
                    .limit(1)
                ).one_or_none()

                if stripe_event:
                    stripe_event.status = StripeEventStatusEnum.IN_PROGRESS
                    transaction.session.add(stripe_event)
                    transaction.session.commit()
                else:
                    await asyncio.sleep(2)
                    continue

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
                    elif event.type == "invoice.updated":
                        handle_invoice_updated(invoice)

            except Exception as e:
                current_app.logger.error(
                    f"Error processing event {stripe_event.event_type} ({stripe_event.event_id}): {e}\n{stripe_event.event_data}",  # noqa: E501
                    exc_info=True,
                )
                stripe_event.status = StripeEventStatusEnum.ERROR
                stripe_event.error_message = str(e)
                db.session.add(stripe_event)
                db.session.commit()
                continue

            stripe_event.status = StripeEventStatusEnum.FINISHED
            db.session.add(stripe_event)
            db.session.commit()


def create_blueprint(app: Flask) -> Blueprint:
    # Now define the blueprint
    bp = Blueprint("premium", __file__, url_prefix="/premium")

    @bp.route("/")
    @authentication_required
    def index() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # Check if we have an incomplete subscription
        stripe_subscription = get_subscription(user)
        if stripe_subscription and stripe_subscription["status"] == "incomplete":
            flash("⚠️ Your subscription is incomplete. Please try again.", "warning")

        # Load the user's invoices
        invoices = db.session.scalars(
            db.select(StripeInvoice)
            .filter_by(user_id=user.id)
            .filter_by(status=StripeInvoiceStatusEnum.PAID)
            .order_by(StripeInvoice.created_at.desc())
        ).all()

        return render_template(
            "premium.html", user=user, invoices=invoices, business_price=get_business_price_string()
        )

    @bp.route("/select-tier")
    @authentication_required
    def select_tier() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        return render_template(
            "premium-select-tier.html", user=user, business_price=get_business_price_string()
        )

    @bp.route("/select-tier/free", methods=["POST"])
    @authentication_required
    def select_free() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.tier_id is None:
            user.set_free_tier()
            db.session.add(user)
            db.session.commit()

        return redirect(url_for("inbox"))

    @bp.route("/waiting")
    @authentication_required
    def waiting() -> Response | str:
        return render_template("premium-waiting.html")

    @bp.route("/upgrade", methods=["POST"])
    @authentication_required
    def upgrade() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        # If the user is already on the business tier
        if user.is_business_tier:
            flash("👍 You're already upgraded.")
            return redirect(url_for("premium.index"))

        # Select the business tier
        business_tier = Tier.business_tier()
        if not business_tier:
            current_app.logger.error("Could not find business tier")
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))
        if not business_tier.stripe_price_id:
            current_app.logger.error("Business tier does not have a price ID")
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        # Make sure the user has a Stripe customer
        try:
            create_customer(user)
        except stripe._error.StripeError as e:
            current_app.logger.error(f"Failed to create Stripe customer: {e}", exc_info=True)
            flash("⚠️ Something went wrong!")
            return redirect(url_for("premium.index"))

        # Create a Stripe Checkout session
        try:
            checkout_session = stripe.checkout.Session.create(
                client_reference_id=str(user.id),
                customer=user.stripe_customer_id,
                line_items=[{"price": business_tier.stripe_price_id, "quantity": 1}],
                mode="subscription",
                success_url=url_for("premium.waiting", _external=True),
                automatic_tax={"enabled": True},
                customer_update={"address": "auto"},
            )
        except stripe._error.StripeError as e:
            current_app.logger.error(
                f"Failed to create Stripe Checkout session: {e}", exc_info=True
            )
            return abort(500)

        if checkout_session.url:
            return redirect(checkout_session.url)

        return abort(500)

    @bp.route("/disable-autorenew", methods=["POST"])
    @authentication_required
    def disable_autorenew() -> Response | str | Tuple[Response | str, int]:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.stripe_subscription_id:
            try:
                stripe.Subscription.modify(user.stripe_subscription_id, cancel_at_period_end=True)
            except stripe._error.StripeError as e:
                current_app.logger.error(f"Stripe error: {e}", exc_info=True)
                return jsonify(success=False), 400
        else:
            return jsonify(success=False), 400

        user.stripe_subscription_cancel_at_period_end = True
        db.session.add(user)
        db.session.commit()

        current_app.logger.info(
            f"Autorenew disabled for subscription {user.stripe_subscription_id} for user {user.id}"
        )

        flash("Autorenew has been disabled.")
        return jsonify(success=True)

    @bp.route("/enable-autorenew", methods=["POST"])
    @authentication_required
    def enable_autorenew() -> Response | str | Tuple[Response | str, int]:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.stripe_subscription_id:
            try:
                stripe.Subscription.modify(user.stripe_subscription_id, cancel_at_period_end=False)
            except stripe._error.StripeError as e:
                current_app.logger.error(f"Stripe error: {e}", exc_info=True)
                return jsonify(success=False), 400

            user.stripe_subscription_cancel_at_period_end = False
            db.session.add(user)
            db.session.commit()

            current_app.logger.info(
                f"Autorenew enabled for subscription {user.stripe_subscription_id} for user {user.id}"  # noqa: E501
            )

            flash("Autorenew has been enabled.")
            return jsonify(success=True)

        return jsonify(success=False), 400

    @bp.route("/cancel", methods=["POST"])
    @authentication_required
    def cancel() -> Response | str | Tuple[Response | str, int]:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.stripe_subscription_id:
            try:
                # Cancel the subscription
                stripe.Subscription.delete(user.stripe_subscription_id)

                # Downgrade the user (the subscription ID will get removed in the webhook)
                user.set_free_tier()
                db.session.add(user)
                db.session.commit()

                current_app.logger.info(
                    f"Subscription {user.stripe_subscription_id} canceled for user {user.id}"
                )

                flash("💔 Sorry to see you go!")
                return jsonify(success=True)
            except stripe._error.StripeError as e:
                current_app.logger.error(f"Stripe error: {e}", exc_info=True)
                return jsonify(success=False), 400

        return jsonify(success=False), 400

    @bp.route("/status.json")
    @authentication_required
    def status() -> Response | str:
        user = db.session.get(User, session.get("user_id"))
        if not user:
            session.clear()
            return redirect(url_for("login"))

        if user.is_business_tier:
            flash("🔥 Congratulations, you've upgraded your account!")

        return jsonify({"tier_id": user.tier_id})

    @bp.route("/webhook", methods=["POST"])
    def webhook() -> Response | str | Tuple[Response | str, int]:
        sig_header = request.headers["STRIPE_SIGNATURE"]

        # Parse the event
        try:
            event = stripe.Webhook.construct_event(
                request.data, sig_header, current_app.config.get("STRIPE_WEBHOOK_SECRET")
            )
        except ValueError as e:
            current_app.logger.error(f"Invalid payload: {e}")
            return jsonify(success=False), 400
        except stripe._error.SignatureVerificationError as e:
            current_app.logger.error(f"Error verifying webhook signature: {e}")
            return jsonify(success=False), 400

        # Have we seen this one before?
        stripe_event = db.session.scalars(
            db.select(StripeEvent).filter_by(event_id=event.id)
        ).one_or_none()
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

"""Existing-account Single Tenant UI and durable subscription cancellation."""

import re
import secrets
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import click
from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required, get_session_user
from hushline.db import db
from hushline.model import SingleTenantOrder, User
from hushline.single_tenant_client import ServiceUnavailable, call, validate_settings

MAX_HOSTNAME_LENGTH = 253
MIN_HOSTNAME_LABELS = 2


def valid_customer_domain(domain: str) -> bool:
    """Check bounded labels independently; never backtrack across dotted input."""
    if not domain or len(domain) > MAX_HOSTNAME_LENGTH:
        return False
    labels = domain.split(".")
    if len(labels) < MIN_HOSTNAME_LABELS or not re.fullmatch(r"[a-z]{2,63}", labels[-1]):
        return False
    if domain == "hushline.app" or domain.endswith(".hushline.app"):
        return False
    if labels[-1] in {"onion", "local", "localhost", "invalid", "example"}:
        return False
    return all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is not None for label in labels
    )


def owned_order() -> SingleTenantOrder | None:
    return db.session.scalar(
        db.select(SingleTenantOrder).where(SingleTenantOrder.user_id == session.get("user_id"))
    )


def pending_setup(user: User) -> bool:
    if not current_app.config.get("SINGLE_TENANT_ENABLED"):
        return False
    order = db.session.scalar(
        db.select(SingleTenantOrder).where(SingleTenantOrder.user_id == user.id)
    )
    return order is not None and order.stage != "ready" and order.service_state != "retired"


def synchronize(order: SingleTenantOrder) -> dict[str, Any]:
    result = call(order, "status")
    status = result.get("status") or {}
    term = result.get("term") or {}
    service_state = term.get("state") if term.get("state") != "active" else status.get("state")
    order.service_state = (
        service_state if isinstance(service_state, str) else status.get("state", "unpaid")
    )
    order.period_end = term.get("period_end")
    order.paid = result.get("paid") is True
    if not order.cancellation_pending:
        order.cancelled = bool(term.get("cancelled_at"))
    db.session.commit()
    return result


def retain_cancellation_on_deletion(user: User) -> None:
    order = db.session.scalar(
        db.select(SingleTenantOrder).where(SingleTenantOrder.user_id == user.id)
    )
    if order:
        # Commit together with account deletion. The service owns the paid term;
        # deleting the portal account never erases its lifecycle ledger.
        order.user_id = None
        order.cancelled = True
        order.cancellation_pending = True
        db.session.add(order)
        db.session.flush()


def reconcile_cancellations() -> int:
    from hushline.single_tenant_billing import SubscriptionExpired

    count = 0
    attempted: set[str] = set()
    while True:
        # Lock one intent across its remote acknowledgement. A newer cancellation
        # or withdrawal waits for this transaction, then remains independently due.
        query = (
            db.select(SingleTenantOrder)
            .where(
                SingleTenantOrder.cancellation_pending.is_(True),
                SingleTenantOrder.id.not_in(attempted),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        order = db.session.scalar(query)
        if order is None:
            db.session.rollback()
            reconcile_destructions()
            return count
        attempted.add(order.id)
        desired = order.cancelled
        try:
            result = call(order, "cancel", cancelled=desired)
        except SubscriptionExpired:
            # Stripe ended the owned subscription while withdrawal was pending.
            # Retain a cancellation intent for the next normal acknowledgement;
            # never leave an impossible withdrawal blocking annual retirement.
            order.cancelled = True
            order.cancellation_pending = True
            db.session.commit()
            continue
        except ServiceUnavailable:
            db.session.rollback()
            continue
        if result.get("cancelled") is desired:
            order.cancellation_pending = False
            db.session.commit()
            count += 1
        else:
            db.session.rollback()


def reconcile_destructions() -> int:
    """Retry the same confirmed intent without changing the recorded annual term."""
    count = 0
    orders = db.session.scalars(
        db.select(SingleTenantOrder).where(
            SingleTenantOrder.destruction_pending.is_(True),
            SingleTenantOrder.cancellation_pending.is_(False),
        )
    ).all()
    for order in orders:
        try:
            call(order, "destroy")
        except ServiceUnavailable:
            db.session.rollback()
            continue
        order.destruction_pending = False
        db.session.commit()
        count += 1
    return count


def reconcile_billing() -> int:
    if current_app.config.get("SINGLE_TENANT_TEST_MODE"):
        return 0
    count = 0
    attempted: set[str] = set()
    while True:
        order = db.session.scalar(
            db.select(SingleTenantOrder)
            .where(
                SingleTenantOrder.billing_sync_pending.is_(True),
                SingleTenantOrder.id.not_in(attempted),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if order is None:
            db.session.rollback()
            return count
        attempted.add(order.id)
        try:
            call(order, "billing-sync")
        except ServiceUnavailable:
            db.session.rollback()
            continue
        order.billing_sync_pending = False
        db.session.commit()
        count += 1


def init_app(app: Flask) -> None:
    @app.cli.command("single-tenant-reconcile")
    @click.option("--once", is_flag=True, help="Run one durable cancellation reconciliation pass.")
    def reconcile(once: bool) -> None:
        validate_settings(app.config)
        from hushline.single_tenant_billing import refresh_expired_terms
        from hushline.single_tenant_registration import prepare_registration_code

        code_prepared = False
        while True:
            if not code_prepared:
                try:
                    prepare_registration_code()
                    code_prepared = True
                except ServiceUnavailable:
                    app.logger.warning("Single Tenant registration code setup is pending")
            refresh_expired_terms()
            reconcile_cancellations()
            reconcile_billing()
            if once:
                return
            time.sleep(30)

    if not app.config.get("SINGLE_TENANT_ENABLED"):
        return
    validate_settings(app.config)
    from hushline.single_tenant_authority import init_app as init_authority

    init_authority(app)
    if not app.config.get("STRIPE_SECRET_KEY"):
        raise ValueError("Single Tenant selection requires the existing premium plan integration")
    bp = Blueprint("single_tenant", __name__, url_prefix="/single-tenant")

    @bp.after_request
    def private_response(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @bp.route("/plans")
    @authentication_required
    def plans() -> str:
        from hushline.premium import get_business_price_string

        return render_template(
            "premium-select-tier.html",
            user=get_session_user(),
            business_price=get_business_price_string(),
        )

    @bp.route("/select", methods=["POST"])
    @authentication_required
    def select() -> Response:
        if not FlaskForm().validate_on_submit():
            abort(400)
        user = get_session_user()
        if user is None:
            abort(401)
        if owned_order() is None:
            if not app.config.get("SINGLE_TENANT_ACCEPT_PAYMENTS"):
                abort(503)
            fixture = app.config.get("SINGLE_TENANT_TEST_ORDER")
            if fixture and db.session.get(SingleTenantOrder, fixture):
                abort(409)
            order = SingleTenantOrder(
                id=app.config.get("SINGLE_TENANT_TEST_ORDER") or secrets.token_hex(16),
                user_id=user.id,
                owner_ref=secrets.token_hex(32),
            )
            db.session.add(order)
        if user.tier_id is None:
            user.set_free_tier()
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if owned_order() is None:
                abort(409)
        return redirect(url_for("single_tenant.setup"))

    @bp.route("", methods=["GET", "POST"])
    @authentication_required
    def setup() -> Response | str | dict[str, Any]:
        order = owned_order()
        if not order:
            return redirect(url_for("single_tenant.plans"))
        form = FlaskForm()
        result: dict[str, Any] = {}
        if request.method == "POST":
            if not form.validate_on_submit():
                abort(400)
            try:
                if order.stage == "licenses":
                    quantity_input = request.form.get("quantity", "")
                    if request.form.get("license_type") == "unlimited":
                        order.license_limit = None
                    elif re.fullmatch(r"[1-9][0-9]{0,8}", quantity_input):
                        order.license_limit = int(quantity_input)
                    else:
                        abort(400)
                    from hushline.single_tenant_billing import prices

                    try:
                        prices(order.license_limit)
                    except ValueError:
                        db.session.rollback()
                        flash(
                            "This annual total exceeds Stripe's checkout limit. "
                            "Choose Unlimited licenses."
                        )
                        return redirect(url_for("single_tenant.setup"))
                    order.stage = "payment"
                elif order.stage == "payment":
                    if request.form.get("payment_action") == "check":
                        result = synchronize(order)
                        if order.paid:
                            order.stage = "domain"
                        else:
                            flash(
                                "Payment has not been confirmed. "
                                "No infrastructure has been requested."
                            )
                    else:
                        if not app.config.get("SINGLE_TENANT_ACCEPT_PAYMENTS"):
                            abort(503)
                        result = call(order, "checkout", quantity=order.license_limit)
                        parsed = urlsplit(result.get("checkout_url", ""))
                        if (
                            parsed.scheme != "https"
                            or parsed.hostname != "checkout.stripe.com"
                            or parsed.username
                            or parsed.password
                        ):
                            raise ServiceUnavailable("Stripe Checkout is unavailable")
                        return redirect(result["checkout_url"], code=303)
                elif order.stage == "domain":
                    if not order.paid:
                        abort(409)
                    domain = request.form.get("domain", "").strip().lower()
                    if app.config.get("SINGLE_TENANT_TEST_ORDER"):
                        if request.form.get("fixture_action") != "provision":
                            abort(400)
                        domain = ""
                    elif not valid_customer_domain(domain):
                        abort(400)
                    call(order, "provision", domain=domain)
                    order.domain = domain
                    order.stage = "dns"
                elif order.stage == "dns":
                    result = call(order, "dns")
                    if request.form.get("dns_action") == "continue" and (
                        result.get("status") or {}
                    ).get("dns_verified"):
                        order.stage = "provision"
                elif order.stage == "provision":
                    result = synchronize(order)
                    if request.form.get("deployment_complete") == "yes" and (
                        result.get("status") or {}
                    ).get("ready"):
                        order.stage = "ready"
                elif order.stage == "ready":
                    return redirect(url_for("single_tenant.claim"))
                db.session.commit()
            except ServiceUnavailable:
                flash(
                    "The instance service is temporarily unavailable. "
                    "Your order is saved; no replacement instance was requested."
                )
            if request.accept_mimetypes.best == "application/json":
                return {"dns_verified": bool((result.get("status") or {}).get("dns_verified"))}
            return redirect(url_for("single_tenant.setup"))
        if order.stage in {"dns", "provision", "ready"}:
            try:
                result = synchronize(order)
            except ServiceUnavailable:
                flash("Deployment status is temporarily unavailable. Your order is saved.")
        quantity = order.license_limit
        licenses = Decimal("20000") if quantity is None else Decimal(quantity) * 240
        subtotal = Decimal("1282.80") + licenses
        status = result.get("status") or {
            "state": order.service_state,
            "message": "Status is temporarily unavailable.",
            "ready": False,
            "ingress": "",
        }
        return render_template(
            "single-tenant/setup.html",
            demo_form=form,
            title="Set up your Single Tenant instance",
            stage=order.stage,
            quantity=quantity,
            order=status,
            domain=order.domain or result.get("ingress"),
            verification=result.get("verification", ""),
            real_test=True,
            stripe_test=app.config.get("SINGLE_TENANT_TEST_MODE", False),
            fixture_test=bool(app.config.get("SINGLE_TENANT_TEST_ORDER")),
            clock_test=bool(app.config.get("SINGLE_TENANT_TEST_ORDER")),
            dns_verified=status.get("dns_verified", False),
            dns_failed=False,
            provision_failed=False,
            unlimited_annual_license_price="20000.00",
            infrastructure="1,282.80",
            license_total=f"{licenses:,.2f}",
            fee=f"{subtotal * Decimal('0.10'):,.2f}",
            annual=f"{subtotal * Decimal('1.30'):,.2f}",
            routing_ips=("162.159.140.98", "172.66.0.96"),
        )

    @bp.route("/payment-return")
    @authentication_required
    def payment_return() -> Response:
        order = owned_order()
        if not order or order.stage != "payment":
            abort(404)
        try:
            result = call(order, "confirm", session_id=request.args.get("session_id", ""))
            if result.get("paid") is True:
                order.paid = True
                order.stage = "domain"
                db.session.commit()
        except ServiceUnavailable:
            flash("Payment verification is pending. No infrastructure has been requested.")
        return redirect(url_for("single_tenant.setup"))

    @bp.route("/status")
    @authentication_required
    def status() -> dict[str, Any] | tuple[dict[str, Any], int]:
        order = owned_order()
        if not order:
            abort(404)
        try:
            result = synchronize(order)
        except ServiceUnavailable:
            return {"message": "Status is temporarily unavailable"}, 503
        return result.get("status") or {"state": order.service_state, "ready": False}

    @bp.route("/claim")
    @authentication_required
    def claim() -> str:
        order = owned_order()
        if not order or order.stage != "ready":
            abort(404)
        try:
            result = call(order, "claim")
        except ServiceUnavailable:
            abort(503)
        domain = result.get("domain", "")
        if not isinstance(domain, str) or not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", domain):
            abort(503)
        return render_template(
            "single-tenant/claim.html", domain=domain, invitation=result.get("invitation", "")
        )

    @bp.route("/manage", methods=["GET", "POST"])
    @authentication_required
    def manage() -> Response | str:
        order = owned_order()
        if not order:
            abort(404)
        form = FlaskForm()
        if request.method == "POST":
            if not form.validate_on_submit():
                abort(400)
            action = request.form.get("action")
            if action not in {"cancel", "resume", "destroy"}:
                abort(400)
            if action == "cancel" and request.form.get("confirm_deletion") != "yes":
                abort(400)
            if action == "destroy":
                if (
                    request.form.get("confirm_destroy_now") != "yes"
                    or not order.paid
                    or order.service_state != "ready"
                ):
                    abort(409)
                order.destroy_requested_at = (
                    order.destroy_requested_at or datetime.now(UTC).isoformat()
                )
                order.destruction_pending = True
            if action == "resume" and (
                order.destroy_requested_at is not None
                or order.service_state in {"retiring", "retired"}
                or (
                    not app.config.get("SINGLE_TENANT_TEST_MODE")
                    and order.paid
                    and order.period_end
                    and datetime.fromisoformat(order.period_end) <= datetime.now(UTC)
                )
            ):
                abort(409)
            order.cancelled = action in {"cancel", "destroy"}
            order.cancellation_pending = True
            db.session.commit()
            reconcile_cancellations()
            flash(
                "Your renewal change is saved."
                if not order.cancellation_pending
                else "Your renewal change is saved and awaiting confirmation. "
                "We will retry automatically."
            )
            return redirect(url_for("single_tenant.manage"))
        try:
            result = synchronize(order)
        except ServiceUnavailable:
            result = {}
        term = result.get("term")
        return render_template(
            "single-tenant/manage.html",
            domain=order.domain or result.get("ingress", ""),
            term=term,
            demo_form=form,
            notice=None,
            fixture_test=False,
            stripe_test=app.config.get("SINGLE_TENANT_TEST_MODE", False),
            clock_test=bool(app.config.get("SINGLE_TENANT_TEST_ORDER")),
            explicit_retirement=bool(order.destroy_requested_at),
            can_destroy=order.paid
            and order.service_state == "ready"
            and not order.destroy_requested_at,
            destruction_pending=order.destruction_pending,
            paid_through=datetime.fromisoformat(order.period_end).strftime("%B %d, %Y at %H:%M UTC")
            if order.period_end
            else None,
            cancellation_pending=order.cancellation_pending,
        )

    app.register_blueprint(bp)

    @app.before_request
    def choose_plan_before_onboarding() -> Response | None:
        if request.endpoint not in {"onboarding", "onboarding_skip", "inbox"}:
            return None
        user = get_session_user()
        if not user or not session.get("is_authenticated"):
            return None
        if user.tier_id is None:
            return redirect(url_for("single_tenant.plans"))
        if pending_setup(user):
            return redirect(url_for("single_tenant.setup"))
        return None

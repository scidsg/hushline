"""Screenshot-only server: real pages, synthetic orders, no external service calls.

Run only against the disposable Compose development database after dev_data.
This module is deliberately absent from the production app startup path.
"""

import hashlib
import os
from typing import Any

from flask import Flask, abort, request

from hushline import create_app, single_tenant
from hushline.config import load_config
from hushline.db import db
from hushline.model import SingleTenantOrder, User, Username
from hushline.single_tenant_client import ServiceUnavailable

PASSWORD = "Test-testtesttesttest-1"  # noqa: S105 -- public development fixture
STATES = (
    "plans",
    "licenses",
    "payment",
    "domain",
    "dns",
    "provision",
    "ready",
    "claim",
    "subscription",
    "cancelled",
    "retiring",
    "retired",
)


def fixture_id(state: str) -> str:
    return hashlib.sha256(f"docs-screenshot:{state}".encode()).hexdigest()[:32]


def service_response(order: SingleTenantOrder, action: str, **_fields: Any) -> dict[str, Any]:
    state = next((name for name in STATES if fixture_id(name) == order.id), None)
    if state is None or action not in {"status", "claim"}:
        raise ServiceUnavailable("Screenshot fixtures allow only owned read-only responses")
    terminal = state in {"retiring", "retired"}
    return {
        "order_id": order.id,
        "owner": order.owner_ref,
        "paid": order.paid,
        "domain": "tips.example.org",
        "invitation": "SCREENSHOT-EXAMPLE-NOT-A-VALID-INVITATION",
        "verification": "screenshot-example-verification",
        "ingress": "screenshot-example.ondigitalocean.app",
        "status": {
            "state": state if terminal else "ready",
            "ready": not terminal,
            "dns_verified": True,
            "https_ok": True,
            "ingress": "screenshot-example.ondigitalocean.app",
            "message": "Instance is healthy and ready.",
            "checks": dict.fromkeys(("infrastructure", "configuration", "tls", "health"), True),
        },
        "term": {
            "state": state if terminal else "active",
            "period_end": "2031-01-01T00:00:00+00:00",
            "cancelled_at": "2030-01-02T00:00:00+00:00" if order.cancelled else None,
        },
    }


def seed_orders() -> None:
    for state in STATES:
        username = f"docs-st-{state}"
        primary = db.session.scalar(db.select(Username).filter_by(_username=username))
        if primary is None:
            user = User(password=PASSWORD, is_admin=False)
            user.onboarding_complete = True
            user.set_free_tier()
            db.session.add(user)
            db.session.flush()
            primary = Username(
                user_id=user.id,
                _username=username,
                is_primary=True,
                display_name="Example organization",
                show_in_directory=False,
            )
            db.session.add(primary)
        if state == "plans":
            continue
        order = db.session.get(SingleTenantOrder, fixture_id(state))
        if order is None:
            order = SingleTenantOrder(
                id=fixture_id(state),
                user_id=primary.user_id,
                owner_ref=hashlib.sha256(f"docs-owner:{state}".encode()).hexdigest(),
            )
            db.session.add(order)
        order.stage = (
            state if state in {"licenses", "payment", "domain", "dns", "provision"} else "ready"
        )
        order.user_id = primary.user_id
        order.license_limit = 13
        order.domain = "tips.example.org"
        order.paid = state not in {"licenses", "payment"}
        order.cancelled = state in {"cancelled", "retiring", "retired"}
        order.service_state = state if state in {"retiring", "retired"} else "ready"
        order.period_end = "2031-01-01T00:00:00+00:00"
        order.destroy_requested_at = (
            "2030-01-02T00:00:00+00:00" if state in {"retiring", "retired"} else None
        )
    db.session.commit()


def create_screenshot_app() -> Flask:
    config = dict(load_config())
    if (
        os.environ.get("DOCS_SCREENSHOT_FIXTURES") != "1"
        or config.get("SQLALCHEMY_DATABASE_URI")
        != "postgresql+psycopg://hushline:hushline@postgres:5432/hushline"
    ):
        raise ValueError(
            "Screenshot fixtures require explicit opt-in and the disposable Compose DB"
        )
    config.update(
        SINGLE_TENANT_ENABLED=True,
        SINGLE_TENANT_ACCEPT_PAYMENTS=True,
        SINGLE_TENANT_TEST_MODE=False,
        SINGLE_TENANT_TEST_ORDER=None,
        SINGLE_TENANT_SERVICE_URL="https://screenshots.invalid",
        SINGLE_TENANT_SERVICE_KEY="a" * 64,
        STRIPE_SECRET_KEY="screenshot-placeholder-not-a-stripe-key",  # noqa: S106 -- invalid fixture
    )
    single_tenant.call = service_response
    app = create_app(config)

    @app.before_request
    def read_only_screenshot_pages() -> None:
        if (
            request.path.startswith(("/single-tenant", "/internal/", "/premium"))
            and request.method != "GET"
        ):
            abort(405)

    with app.app_context():
        seed_orders()
    return app

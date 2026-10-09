"""Screenshot fixtures render actual routes without payment or infrastructure calls."""

import os
from collections.abc import Callable

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import SingleTenantOrder, Username
from hushline.single_tenant_client import ServiceUnavailable
from scripts.docs_screenshot_app import (
    PASSWORD,
    STATES,
    create_screenshot_app,
    fixture_id,
    seed_orders,
    service_response,
)


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def configure(mocker: MockFixture) -> None:
        mocker.patch.dict(
            os.environ,
            {
                "SINGLE_TENANT_ENABLED": "true",
                "SINGLE_TENANT_ACCEPT_PAYMENTS": "true",
                "SINGLE_TENANT_TEST_MODE": "true",
                "SINGLE_TENANT_SERVICE_URL": "http://127.0.0.1:8776",
                "SINGLE_TENANT_SERVICE_KEY": "a" * 64,
            },
        )

    return configure


def test_fixture_server_rejects_missing_opt_in_and_non_development_db(mocker: MockFixture) -> None:
    mocker.patch("scripts.docs_screenshot_app.load_config", return_value={})
    mocker.patch.dict(os.environ, {"DOCS_SCREENSHOT_FIXTURES": "1"})
    with pytest.raises(ValueError, match="disposable Compose DB"):
        create_screenshot_app()
    mocker.patch(
        "scripts.docs_screenshot_app.load_config",
        return_value={
            "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://hushline:hushline@postgres:5432/hushline",
        },
    )
    mocker.patch.dict(os.environ, {"DOCS_SCREENSHOT_FIXTURES": "0"})
    with pytest.raises(ValueError, match="explicit opt-in"):
        create_screenshot_app()


def test_fixture_server_blocks_billing_and_lifecycle_writes(
    app: Flask,
    client: FlaskClient,
    mocker: MockFixture,
) -> None:
    config = dict(app.config)
    config["SQLALCHEMY_DATABASE_URI"] = (
        "postgresql+psycopg://hushline:hushline@postgres:5432/hushline"
    )
    config["STRIPE_SECRET_KEY"] = "existing-key-must-not-be-used"
    mocker.patch.dict(os.environ, {"DOCS_SCREENSHOT_FIXTURES": "1"})
    mocker.patch("scripts.docs_screenshot_app.load_config", return_value=config)
    factory = mocker.patch("scripts.docs_screenshot_app.create_app", return_value=app)
    mocker.patch("scripts.docs_screenshot_app.seed_orders")
    mocker.patch("hushline.single_tenant.call")
    create_screenshot_app()
    fixture_config = factory.call_args.args[0]
    assert fixture_config["STRIPE_SECRET_KEY"] == "screenshot-placeholder-not-a-stripe-key"
    assert fixture_config["SINGLE_TENANT_SERVICE_URL"] == "https://screenshots.invalid"
    for path in ("/single-tenant/select", "/single-tenant/manage", "/internal/billing", "/premium"):
        assert client.post(path).status_code == 405


@pytest.mark.parametrize("state", STATES)
def test_fixture_routes_are_deterministic_and_do_not_contact_external_services(
    app: Flask,
    client: FlaskClient,
    mocker: MockFixture,
    state: str,
) -> None:
    mocker.patch(
        "requests.sessions.Session.request", side_effect=AssertionError("external request")
    )
    mocker.patch("hushline.single_tenant.call", side_effect=service_response)
    app.config["SINGLE_TENANT_TEST_MODE"] = False
    seed_orders()
    seed_orders()  # Repeated startup must not create duplicate users or orders.
    primary = db.session.scalar(db.select(Username).filter_by(_username=f"docs-st-{state}"))
    assert primary is not None
    login = client.post("/login", data={"username": primary.username, "password": PASSWORD})
    assert login.status_code == 302
    path = (
        "/single-tenant/plans"
        if state == "plans"
        else "/single-tenant/claim"
        if state == "claim"
        else "/single-tenant/manage"
        if state in {"subscription", "cancelled", "retiring", "retired"}
        else "/single-tenant"
    )
    page = client.get(path)
    assert page.status_code == 200
    assert b"temporarily unavailable" not in page.data
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    if state == "retired":
        assert b"Your instance and stored messages have been deleted." in page.data
        assert b"confirm-destroy-now" not in page.data
    if state == "subscription":
        assert b"Cancel renewal and destroy my instance now" in page.data
    if state in {"dns", "provision", "ready"}:
        status = client.get("/single-tenant/status")
        assert status.status_code == 200
        assert status.json is not None
        assert status.json["checks"]["health"] is True
    if state != "plans":
        order = db.session.get(SingleTenantOrder, fixture_id(state))
        assert order is not None
        for action in ("checkout", "provision", "cancel", "destroy"):
            with pytest.raises(ServiceUnavailable):
                service_response(order, action)
        order.id = "f" * 32
        with pytest.raises(ServiceUnavailable):
            service_response(order, "status")

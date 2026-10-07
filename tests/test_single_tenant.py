"""Account-bound billing and cancellation, with production disabled by default."""

import os
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import SingleTenantOrder, User
from hushline.single_tenant import reconcile_cancellations, valid_customer_domain
from hushline.single_tenant_client import ServiceUnavailable, validate_settings
from hushline.user_deletion import delete_user_and_related

ORDER = "6368ab5a5987358f9a9083f8ec2707b7"


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
                "SINGLE_TENANT_TEST_ORDER": ORDER,
            },
        )

    return configure


@pytest.fixture()
def order(client: FlaskClient, user: User, _authenticated_user: None) -> SingleTenantOrder:
    assert client.post("/single-tenant/select").status_code == 302
    result = db.session.get(SingleTenantOrder, ORDER)
    assert result is not None
    return result


def snapshot(order: SingleTenantOrder, *, ready: bool = False) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "owner": order.owner_ref,
        "paid": True,
        "status": {
            "state": "ready" if ready else "provisioning",
            "ready": ready,
            "dns_verified": ready,
            "message": "Owned instance status",
            "ingress": "fixture.ondigitalocean.app",
        },
        "term": {
            "state": "active",
            "period_end": "2027-10-06T16:00:00+00:00",
            "cancelled_at": None,
        },
        "ingress": "fixture.ondigitalocean.app",
    }


@pytest.mark.usefixtures("_authenticated_user")
def test_plan_selection_precedes_onboarding(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = False
    user.tier_id = None
    db.session.commit()
    response = client.get("/onboarding")
    assert response.status_code == 302
    assert response.location.endswith("/single-tenant/plans")
    page = client.get("/single-tenant/plans")
    assert b"Choose Single Tenant" in page.data
    assert b"Use Free Plan" in page.data
    assert b"Upgrade to Super User" in page.data


@pytest.mark.usefixtures("_authenticated_user")
def test_free_plan_continues_to_onboarding(client: FlaskClient, user: User) -> None:
    user.tier_id = None
    user.onboarding_complete = False
    db.session.commit()
    response = client.post("/premium/select-tier/free")
    assert response.location.endswith("/onboarding")


def test_license_price_updates_without_an_extra_price_button(
    client: FlaskClient, order: SingleTenantOrder
) -> None:
    page = client.get("/single-tenant")
    assert b"Unlimited licenses" in page.data
    assert b"single-tenant-price.js" in page.data
    response = client.post("/single-tenant", data={"license_type": "numbered", "quantity": "25"})
    assert response.status_code == 302
    assert order.license_limit == 25
    assert order.stage == "payment"
    assert b"9,467.64" in client.get("/single-tenant").data


def test_unlimited_includes_all_charges(client: FlaskClient, order: SingleTenantOrder) -> None:
    client.post("/single-tenant", data={"license_type": "unlimited"})
    assert order.license_limit is None
    assert b"27,667.64" in client.get("/single-tenant").data


def test_unverified_payment_cannot_provision(
    client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    order.stage = "domain"
    db.session.commit()
    service = mocker.patch("hushline.single_tenant.call")
    response = client.post("/single-tenant", data={"fixture_action": "provision"})
    assert response.status_code == 409
    service.assert_not_called()


def test_status_success_never_advances_either_continue_gate(
    client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    mocker.patch("hushline.single_tenant.call", return_value=snapshot(order, ready=True))
    order.stage = "dns"
    db.session.commit()
    assert client.get("/single-tenant/status").status_code == 200
    assert order.stage == "dns"
    assert client.get("/single-tenant").status_code == 200
    assert order.stage == "dns"
    client.post("/single-tenant", data={"dns_action": "continue"})
    assert order.stage == "provision"
    client.get("/single-tenant/status")
    assert order.stage == "provision"
    client.post("/single-tenant", data={"deployment_complete": "yes"})
    assert order.stage == "ready"


def test_failed_status_keeps_existing_check_and_stage(
    client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    order.stage = "provision"
    db.session.commit()
    mocker.patch("hushline.single_tenant.call", side_effect=ServiceUnavailable("safe"))
    assert client.get("/single-tenant/status").status_code == 503
    assert order.stage == "provision"


def test_cancellation_is_durable_when_service_unavailable(
    client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    mocker.patch("hushline.single_tenant.call", side_effect=ServiceUnavailable("safe"))
    response = client.post(
        "/single-tenant/manage", data={"action": "cancel", "confirm_deletion": "yes"}
    )
    assert response.status_code == 302
    assert order.cancelled
    assert order.cancellation_pending
    assert order.period_end is None


def test_cancellation_requires_deletion_acknowledgement(
    client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    service = mocker.patch("hushline.single_tenant.call")
    assert client.post("/single-tenant/manage", data={"action": "cancel"}).status_code == 400
    assert not order.cancelled
    service.assert_not_called()


def test_account_deletion_retains_independent_cancellation(
    order: SingleTenantOrder, user: User, mocker: MockFixture
) -> None:
    service = mocker.patch("hushline.single_tenant.call")
    delete_user_and_related(user)
    db.session.commit()
    retained = db.session.get(SingleTenantOrder, ORDER)
    assert retained is not None
    assert retained.user_id is None
    assert retained.cancelled
    assert retained.cancellation_pending
    service.assert_not_called()


def test_reconciler_retries_same_order_without_replacing_it(
    order: SingleTenantOrder, mocker: MockFixture
) -> None:
    order.cancelled = True
    order.cancellation_pending = True
    db.session.commit()
    service = mocker.patch("hushline.single_tenant.call", side_effect=ServiceUnavailable("safe"))
    assert reconcile_cancellations() == 0
    assert order.cancellation_pending
    service.side_effect = None
    service.return_value = {"order_id": ORDER, "owner": order.owner_ref, "cancelled": True}
    assert reconcile_cancellations() == 1
    assert not order.cancellation_pending
    assert service.call_args.args == (order, "cancel")


def test_another_account_cannot_view_claim_or_order(
    client: FlaskClient, order: SingleTenantOrder, user2: User, mocker: MockFixture
) -> None:
    service = mocker.patch("hushline.single_tenant.call")
    with client.session_transaction() as session:
        session.update(
            user_id=user2.id,
            session_id=user2.session_id,
            username=user2.primary_username.username,
            is_authenticated=True,
        )
    assert client.get("/single-tenant/status").status_code == 404
    assert client.get("/single-tenant/claim").status_code == 404
    assert client.post("/single-tenant/select").status_code == 409
    service.assert_not_called()


def test_csrf_and_csp_remain_enforced(
    app: Flask, client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    service = mocker.patch("hushline.single_tenant.call")
    assert client.post("/single-tenant", data={"quantity": "2"}).status_code == 400
    page = client.get("/single-tenant")
    policy = page.headers["Content-Security-Policy"]
    assert "script-src 'self';" in policy
    assert "frame-ancestors 'none'" in policy
    assert page.headers["Cache-Control"] == "no-store"
    service.assert_not_called()


@pytest.mark.parametrize(
    "config",
    [
        {"SINGLE_TENANT_SERVICE_URL": "http://example.org"},
        {"SINGLE_TENANT_SERVICE_URL": "https://user:password@example.org"},
        {"SINGLE_TENANT_SERVICE_URL": "https://example.org?token=private"},
        {"SINGLE_TENANT_SERVICE_URL": "https://example.org", "SINGLE_TENANT_TEST_ORDER": ORDER},
    ],
)
def test_service_trust_roots_fail_closed(config: dict[str, Any]) -> None:
    config.setdefault("SINGLE_TENANT_SERVICE_KEY", "a" * 64)
    with pytest.raises(ValueError, match="Single Tenant|test order"):
        validate_settings(config)


def test_signed_service_response_must_match_account_order(
    app: Flask, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    import json
    from unittest.mock import MagicMock

    from hushline.single_tenant_client import call

    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = [
        json.dumps({"order_id": "f" * 32, "owner": order.owner_ref}).encode()
    ]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.post.return_value = response
    mocker.patch("hushline.single_tenant_client.requests.Session", return_value=connection)
    with pytest.raises(ServiceUnavailable, match="ownership verification"):
        call(order, "status")
    assert connection.trust_env is False
    assert connection.post.call_args.kwargs["allow_redirects"] is False
    headers = connection.post.call_args.kwargs["headers"]
    assert len(headers["X-Hushline-Signature"]) == 64


def test_oversized_service_response_is_rejected(
    app: Flask, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    from unittest.mock import MagicMock

    from hushline.single_tenant_client import call

    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = [b"x" * 65537]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.post.return_value = response
    mocker.patch("hushline.single_tenant_client.requests.Session", return_value=connection)
    with pytest.raises(ServiceUnavailable, match="response was invalid"):
        call(order, "status")


def test_sales_pause_blocks_checkout_but_preserves_cancellation(
    app: Flask, client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    app.config["SINGLE_TENANT_ACCEPT_PAYMENTS"] = False
    order.stage = "payment"
    db.session.commit()
    service = mocker.patch("hushline.single_tenant.call")
    assert client.post("/single-tenant").status_code == 503
    service.assert_not_called()
    service.return_value = {"cancelled": True}
    response = client.post(
        "/single-tenant/manage", data={"action": "cancel", "confirm_deletion": "yes"}
    )
    assert response.status_code == 302
    assert order.cancelled
    assert not order.cancellation_pending


def test_feature_disabled_does_not_erase_account_deletion_intent(
    app: Flask, order: SingleTenantOrder, user: User
) -> None:
    app.config["SINGLE_TENANT_ENABLED"] = False
    delete_user_and_related(user)
    db.session.commit()
    retained = db.session.get(SingleTenantOrder, order.id)
    assert retained is not None
    assert retained.user_id is None
    assert retained.cancellation_pending
    assert retained.cancelled
    assert "single-tenant-reconcile" in app.cli.commands


def test_oversized_annual_checkout_is_explained_without_charge_or_stage_advance(
    client: FlaskClient,
    order: SingleTenantOrder,
    mocker: MockFixture,
) -> None:
    charge = mocker.patch("hushline.single_tenant.call")
    response = client.post(
        "/single-tenant", data={"license_type": "numbered", "quantity": "999999999"}
    )
    assert response.status_code == 302
    db.session.refresh(order)
    assert order.stage == "licenses"
    charge.assert_not_called()
    with client.session_transaction() as saved:
        assert any("Choose Unlimited licenses" in message for _, message in saved["_flashes"])


@pytest.mark.parametrize("domain", ["hushline.foo", "tips.customer.org", "my-team.example.com"])
def test_customer_domain_accepts_public_hostnames(domain: str) -> None:
    assert valid_customer_domain(domain)


@pytest.mark.parametrize(
    "domain",
    [
        "0." * 10000,
        "0." * 100 + "0",
        "a" * 64 + ".org",
        "hushline.app",
        "tips.hushline.app",
        "customer.onion",
        "customer.local",
        "customer.invalid",
        "-customer.org",
        "customer-.org",
        "customer..org",
        "https://customer.org",
        "customer.org/path",
        "127.0.0.1",
    ],
)
def test_invalid_or_protected_domain_is_rejected(domain: str) -> None:
    assert not valid_customer_domain(domain)


@pytest.mark.parametrize("state", ["retiring", "retired"])
def test_withdrawal_cannot_change_intent_during_or_after_retirement(
    app: Flask, client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture, state: str
) -> None:
    order.service_state = state
    order.cancelled = True
    order.cancellation_pending = False
    db.session.commit()
    call = mocker.patch("hushline.single_tenant.call")
    assert client.post("/single-tenant/manage", data={"action": "resume"}).status_code == 409
    db.session.refresh(order)
    assert order.cancelled is True
    assert order.cancellation_pending is False
    call.assert_not_called()


def test_live_withdrawal_after_paid_year_is_rejected_before_intent_changes(
    app: Flask, client: FlaskClient, order: SingleTenantOrder, mocker: MockFixture
) -> None:
    app.config["SINGLE_TENANT_TEST_MODE"] = False
    order.paid = True
    order.period_end = "2025-01-01T00:00:00+00:00"
    order.cancelled = True
    order.cancellation_pending = False
    db.session.commit()
    call = mocker.patch("hushline.single_tenant.call")
    assert client.post("/single-tenant/manage", data={"action": "resume"}).status_code == 409
    db.session.refresh(order)
    assert order.cancelled is True
    assert order.cancellation_pending is False
    call.assert_not_called()

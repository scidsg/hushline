import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    StripeEvent,
    StripeEventStatusEnum,
    StripeInvoice,
    StripeInvoiceStatusEnum,
    StripeSubscriptionStatusEnum,
    Tier,
    User,
)


def _add_stripe_invoice(
    user: User,
    invoice_id: str = "inv_delete_account",
    status: StripeInvoiceStatusEnum = StripeInvoiceStatusEnum.PAID,
) -> StripeInvoice:
    user.stripe_customer_id = f"cus_{invoice_id}"
    business_tier = Tier.business_tier()
    assert business_tier is not None
    db.session.commit()

    invoice = StripeInvoice(
        SimpleNamespace(
            id=invoice_id,
            customer=user.stripe_customer_id,
            hosted_invoice_url="https://example.com/invoice",
            total=2000,
            status=status.value,
            created=None,
            lines=SimpleNamespace(
                data=[
                    SimpleNamespace(plan=SimpleNamespace(product=business_tier.stripe_product_id))
                ]
            ),
        )
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def _add_stripe_invoice_event(
    invoice_id: str,
    event_type: str = "invoice.updated",
    status: StripeEventStatusEnum = StripeEventStatusEnum.PENDING,
) -> StripeEvent:
    event = StripeEvent(
        MagicMock(
            id=f"evt_{invoice_id}",
            created=1,
            type=event_type,
        )
    )
    event.event_data = json.dumps({"data": {"object": {"id": invoice_id}}})
    event.status = status
    db.session.add(event)
    db.session.commit()
    return event


def _add_stripe_subscription_event(user: User) -> StripeEvent:
    user.stripe_customer_id = "cus_pending_subscription_event_delete_account"
    event = StripeEvent(
        MagicMock(
            id="evt_pending_subscription_event_delete_account",
            created=1,
            type="customer.subscription.created",
        )
    )
    event.event_data = json.dumps(
        {
            "data": {
                "object": {
                    "id": "sub_pending_subscription_event_delete_account",
                    "customer": user.stripe_customer_id,
                }
            }
        }
    )
    event.status = StripeEventStatusEnum.PENDING
    db.session.add(event)
    db.session.commit()
    return event


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account(client: FlaskClient, user: User) -> None:
    user.email = "primary@example.com"
    db.session.commit()

    # Make sure the user is there
    user_count = db.session.query(User).filter_by(id=user.id).count()
    assert user_count == 1

    # Delete the account
    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 302

    # Make sure the user is deleted
    user_count = db.session.query(User).filter_by(id=user.id).count()
    assert user_count == 0


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account_with_stripe_subscription_blocked(client: FlaskClient, user: User) -> None:
    user.stripe_subscription_id = "sub_delete_account"
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.CANCELED
    db.session.commit()

    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account_with_incomplete_expired_subscription_id_allowed(
    client: FlaskClient, user: User
) -> None:
    user.stripe_subscription_id = "sub_expired_checkout_delete_account"
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.INCOMPLETE_EXPIRED
    db.session.commit()

    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 302

    assert db.session.get(User, user.id) is None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account_with_open_stripe_invoice_blocked(client: FlaskClient, user: User) -> None:
    invoice = _add_stripe_invoice(user, "inv_open_delete_account", StripeInvoiceStatusEnum.OPEN)

    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeInvoice, invoice.id) is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account_with_queued_stripe_invoice_event_blocked(
    client: FlaskClient, user: User
) -> None:
    invoice = _add_stripe_invoice(user, "inv_pending_event_delete_account")
    event = _add_stripe_invoice_event(invoice.invoice_id)

    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeInvoice, invoice.id) is not None
    assert db.session.get(StripeEvent, event.id) is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account_with_queued_stripe_subscription_event_blocked(
    client: FlaskClient, user: User
) -> None:
    event = _add_stripe_subscription_event(user)

    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeEvent, event.id) is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_cannot_delete_only_admin_account(client: FlaskClient, admin_user: User) -> None:
    # Make sure there is only one admin user
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1

    # Make sure the user is there
    user_count = db.session.query(User).filter_by(id=admin_user.id).count()
    assert user_count == 1

    # Deleting the account should fail
    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 400

    # Make sure the user is still there
    user_count = db.session.query(User).filter_by(id=admin_user.id).count()
    assert user_count == 1


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_account_multiple_admins(
    client: FlaskClient, admin_user: User, admin_user2: User
) -> None:
    # Make sure there are two admin users
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 2

    # Make sure the user is there
    user_count = db.session.query(User).filter_by(id=admin_user.id).count()
    assert user_count == 1

    # Deleting the account should work
    response = client.post(url_for("settings.delete_account"))
    assert response.status_code == 302

    # Make sure the user is deleted
    user_count = db.session.query(User).filter_by(id=admin_user.id).count()
    assert user_count == 0


def test_delete_account_redirects_to_login_without_user_id(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess["username"] = "missing-id"
        sess.pop("user_id", None)

    response = client.post(url_for("settings.delete_account"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


def test_delete_account_redirects_to_login_when_user_missing(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hushline.auth.get_session_user", lambda: user)

    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess["username"] = "missing-user"
        sess["user_id"] = 999999
        sess["session_id"] = user.session_id

    response = client.post(url_for("settings.delete_account"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))

    with client.session_transaction() as sess:
        assert any(
            tuple(entry) == ("message", "🫥 User not found. Please log in again.")
            for entry in sess["_flashes"]
        )

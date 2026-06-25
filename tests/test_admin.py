import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture
from wtforms.validators import ValidationError

from hushline.db import db
from hushline.model import (
    AccountCategory,
    ChatKey,
    StripeEvent,
    StripeEventStatusEnum,
    StripeInvoice,
    StripeInvoiceStatusEnum,
    StripeSubscriptionStatusEnum,
    Tier,
    User,
    Username,
)


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_shows_verified_on_managed_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Set Verified" in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_includes_user_search(app: Flask, client: FlaskClient) -> None:
    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    assert 'id="searchInput"' in response.text
    assert 'id="admin-users-list"' in response.text
    assert "/static/js/settings_admin.js" in response.text
    search_form = soup.select_one("form.settings-search[role='search']")
    assert search_form is not None
    assert search_form.select_one('input[name="q"]') is not None
    assert "Set Cautious" in response.text
    assert "Set Suspended" in response.text
    assert "Set Featured" in response.text
    assert "Featured:" in response.text
    assert "Account Category:" in response.text

    account_category_form = soup.select_one(
        "form.admin-account-category-form[data-auto-submit-select='true']"
    )
    assert account_category_form is not None
    assert account_category_form.select_one('select[name="account_category"]') is not None
    assert account_category_form.find_parent(class_="tableActions") is None
    assert "Update Category" not in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_discloses_stripe_billing_state(client: FlaskClient, user: User) -> None:
    _add_stripe_invoice(user, "inv_admin_billing_state", StripeInvoiceStatusEnum.OPEN)
    user.stripe_subscription_id = "sub_admin_billing_state"
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE
    db.session.commit()

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    user_card = next(
        (
            card
            for card in soup.select("#admin-users-list .user")
            if card.find("h5", string=user.primary_username.username)
        ),
        None,
    )
    assert user_card is not None
    user_text = " ".join(user_card.get_text(" ", strip=True).split())

    assert "Stripe Billing: Active or unresolved subscription; deletion disabled." in user_text
    assert "1 draft, open, or unknown invoice; deletion disabled." in user_text
    assert (
        "1 invoice associated; deleting this user also deletes stored invoice receipt records."
        in user_text
    )
    delete_button = user_card.select_one("button.delete-user-button")
    assert delete_button is not None
    assert delete_button.has_attr("disabled")


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_renamed_users_and_moves_highlights(client: FlaskClient) -> None:
    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    current_tab = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current_tab is not None
    assert current_tab.get_text(strip=True) == "Users"
    assert soup.select_one("nav.settings-tabs a[href='/settings/metrics']") is not None
    assert soup.find("h3", string="Users") is not None
    assert soup.select_one(".admin-highlights") is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_metrics_settings_shows_admin_highlights(
    client: FlaskClient, admin_user: User, user: User
) -> None:
    admin_user.totp_secret = "123456"
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    db.session.add(
        ChatKey(
            user_id=user.id,
            key_version=1,
            public_key="public-chat-key",
            public_signing_key="public-signing-key",
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000, "hash": "SHA-256"},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )
    db.session.commit()

    response = client.get(url_for("settings.metrics"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    current_tab = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current_tab is not None
    assert current_tab.get_text(strip=True) == "Metrics"
    highlights = soup.select_one(".admin-highlights")
    assert highlights is not None
    metrics_text = " ".join(highlights.get_text(" ", strip=True).split())
    assert "Users 2" in metrics_text
    assert "2FA Enabled 1 50.0%" in metrics_text
    assert "PGP Enabled 1 50.0%" in metrics_text
    assert "Chat Keys Created 1 50.0%" in metrics_text


def _create_admin_list_user(username: str, display_name: str | None = None) -> User:
    test_password = "Test-testtesttesttest-1"
    user = User(password=test_password)
    user.onboarding_complete = True
    user.tier_id = 1
    db.session.add(user)
    db.session.flush()
    db.session.add(
        Username(
            user_id=user.id,
            _username=username,
            _display_name=display_name,
            is_primary=True,
        )
    )
    db.session.commit()
    return user


def _add_stripe_invoice(
    user: User,
    invoice_id: str = "inv_delete_user",
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


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_paginates_usernames(client: FlaskClient) -> None:
    for index in range(25):
        _create_admin_list_user(f"page-user-{index:02d}")

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    summary = soup.select_one(".admin-pagination-summary")
    assert summary is not None
    summary_text = " ".join(summary.get_text(" ", strip=True).split())

    assert len(soup.select("#admin-users-list .user")) == 20
    assert summary_text == "Showing 1-20 of 26 usernames."
    assert "Page 1 of 2" in soup.get_text(" ", strip=True)
    assert soup.find("a", string="Next") is not None

    response = client.get(url_for("settings.admin", page=2), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    summary = soup.select_one(".admin-pagination-summary")
    assert summary is not None
    summary_text = " ".join(summary.get_text(" ", strip=True).split())

    assert len(soup.select("#admin-users-list .user")) == 6
    assert summary_text == "Showing 21-26 of 26 usernames."
    assert "Page 2 of 2" in soup.get_text(" ", strip=True)
    assert soup.find("a", string="Previous") is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_clamps_invalid_page_requests(client: FlaskClient) -> None:
    for index in range(25):
        _create_admin_list_user(f"page-user-{index:02d}")

    response = client.get(url_for("settings.admin", page="not-a-number"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    assert "Page 1 of 2" in soup.get_text(" ", strip=True)
    assert len(soup.select("#admin-users-list .user")) == 20

    response = client.get(url_for("settings.admin", page=999), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    assert "Page 2 of 2" in soup.get_text(" ", strip=True)
    assert len(soup.select("#admin-users-list .user")) == 6


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_searches_all_usernames_before_paginating(client: FlaskClient) -> None:
    for index in range(25):
        _create_admin_list_user(f"page-user-{index:02d}")
    _create_admin_list_user("zz-global-match", display_name="Needle Recipient")

    response = client.get(url_for("settings.admin", q="Needle"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    summary = soup.select_one(".admin-pagination-summary")
    assert summary is not None
    summary_text = " ".join(summary.get_text(" ", strip=True).split())

    assert "zz-global-match" in response.text
    assert summary_text == 'Showing 1-1 of 1 usernames matching "Needle".'


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_hides_verified_on_nonmanaged_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = False

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Set Verified" not in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_managed_service(
    app: Flask, client: FlaskClient, admin_user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    response = client.post(
        url_for("admin.toggle_verified", user_id=admin_user.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    refreshed_user = db.session.get(User, admin_user.id)
    assert refreshed_user is not None
    assert refreshed_user.primary_username.is_verified is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_nonmanaged_service(
    app: Flask, client: FlaskClient, admin_user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = False

    response = client.post(
        url_for("admin.toggle_verified", user_id=admin_user.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_only_admin(client: FlaskClient, admin_user: User) -> None:
    # Make sure there is only one admin user
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1

    # Make sure the user is an admin
    assert admin_user.is_admin is True

    # Toggling admin on the user should return 400
    response = client.post(
        url_for("admin.toggle_admin", user_id=admin_user.id),
        data={"is_admin": "false"},
        follow_redirects=True,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_multiple_admins(
    client: FlaskClient, admin_user: User, admin_user2: User
) -> None:
    assert admin_user.is_admin is True
    assert admin_user2.is_admin is True

    # Make sure there are two admin users
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 2

    # Toggling admin on the user should return 302 (successfully redirect)
    response = client.post(
        url_for("admin.toggle_admin", user_id=admin_user.id), data={"is_admin": "false"}
    )
    assert response.status_code == 302

    # There should be only one admins now
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_alias_on_managed_service(
    app: Flask, client: FlaskClient, user_alias: Username
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    assert user_alias.is_verified is False

    response = client.post(
        url_for("admin.toggle_verified_username", username_id=user_alias.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_alias = db.session.get(Username, user_alias.id)
    assert refreshed_alias is not None
    assert refreshed_alias.is_verified is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_featured_username(client: FlaskClient, user_alias: Username) -> None:
    assert user_alias.is_featured is False

    response = client.post(
        url_for("admin.toggle_featured_username", username_id=user_alias.id),
        data={"is_featured": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_alias = db.session.get(Username, user_alias.id)
    assert refreshed_alias is not None
    assert refreshed_alias.is_featured is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_removes_user(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 302

    deleted_user = db.session.get(User, user.id)
    assert deleted_user is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_removes_stripe_invoices(client: FlaskClient, user: User) -> None:
    invoice = _add_stripe_invoice(user)
    invoice_id = invoice.id

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 302

    assert db.session.get(User, user.id) is None
    assert db.session.get(StripeInvoice, invoice_id) is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_with_active_stripe_subscription_blocked(
    client: FlaskClient, user: User
) -> None:
    invoice = _add_stripe_invoice(user, "inv_blocked_delete_user")
    user.stripe_subscription_id = "sub_blocked_delete_user"
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE
    db.session.commit()

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeInvoice, invoice.id) is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_with_canceled_stripe_subscription_id_blocked(
    client: FlaskClient, user: User
) -> None:
    user.stripe_subscription_id = "sub_canceled_but_not_deleted"
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.CANCELED
    db.session.commit()

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_with_open_stripe_invoice_blocked(client: FlaskClient, user: User) -> None:
    invoice = _add_stripe_invoice(user, "inv_open_delete_user", StripeInvoiceStatusEnum.OPEN)

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeInvoice, invoice.id) is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_with_queued_stripe_invoice_event_blocked(
    client: FlaskClient, user: User
) -> None:
    invoice = _add_stripe_invoice(user, "inv_pending_event_delete_user")
    event = _add_stripe_invoice_event(invoice.invoice_id)

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 400

    assert db.session.get(User, user.id) is not None
    assert db.session.get(StripeInvoice, invoice.id) is not None
    assert db.session.get(StripeEvent, event.id) is not None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_discloses_queued_stripe_invoice_event(
    client: FlaskClient, user: User
) -> None:
    invoice = _add_stripe_invoice(user, "inv_admin_pending_event")
    _add_stripe_invoice_event(invoice.invoice_id)

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    user_card = next(
        (
            card
            for card in soup.select("#admin-users-list .user")
            if card.find("h5", string=user.primary_username.username)
        ),
        None,
    )
    assert user_card is not None
    user_text = " ".join(user_card.get_text(" ", strip=True).split())

    assert "1 queued invoice webhook; deletion disabled." in user_text
    delete_button = user_card.select_one("button.delete-user-button")
    assert delete_button is not None
    assert delete_button.has_attr("disabled")


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_only_admin_blocked(client: FlaskClient, admin_user: User) -> None:
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1

    response = client.post(url_for("admin.delete_user", user_id=admin_user.id))
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_self_blocked(client: FlaskClient, admin_user: User) -> None:
    response = client.post(url_for("admin.delete_user", user_id=admin_user.id))
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_alias_does_not_delete_user(client: FlaskClient, user_alias: Username) -> None:
    user_id = user_alias.user_id

    response = client.post(url_for("admin.delete_username", username_id=user_alias.id))
    assert response.status_code == 302

    remaining_user = db.session.get(User, user_id)
    assert remaining_user is not None

    deleted_alias = db.session.get(Username, user_alias.id)
    assert deleted_alias is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_primary_deletes_aliases(client: FlaskClient, user_alias: Username) -> None:
    user = db.session.get(User, user_alias.user_id)
    assert user is not None

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 302

    remaining_alias = db.session.get(Username, user_alias.id)
    assert remaining_alias is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_actions_require_csrf_token(
    app: Flask, client: FlaskClient, user_alias: Username
) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    target_user_id = user_alias.user_id

    app.config["USER_VERIFICATION_ENABLED"] = True
    response = client.post(
        url_for("admin.toggle_verified_username", username_id=user_alias.id),
        data={"is_verified": "true"},
    )
    assert response.status_code == 400

    response = client.post(
        url_for("admin.delete_username", username_id=user_alias.id),
    )
    assert response.status_code == 400

    response = client.post(
        url_for("admin.toggle_suspended", user_id=target_user_id),
        data={"is_suspended": "true"},
    )
    assert response.status_code == 400

    response = client.post(
        url_for("admin.update_account_category", user_id=target_user_id),
        data={"account_category": AccountCategory.LAWYER.value},
    )
    assert response.status_code == 400

    app.config["WTF_CSRF_ENABLED"] = prior_setting


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_user_not_found(app: Flask, client: FlaskClient) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True
    response = client.post(
        url_for("admin.toggle_verified", user_id=999999),
        data={"is_verified": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_username_nonmanaged_forbidden(
    app: Flask, client: FlaskClient, user_alias: Username
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = False
    response = client.post(
        url_for("admin.toggle_verified_username", username_id=user_alias.id),
        data={"is_verified": "true"},
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_username_not_found(app: Flask, client: FlaskClient) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True
    response = client.post(
        url_for("admin.toggle_verified_username", username_id=999999),
        data={"is_verified": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_featured_username_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.toggle_featured_username", username_id=999999),
        data={"is_featured": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_missing_bool_field_returns_bad_request(
    client: FlaskClient, user: User
) -> None:
    response = client.post(url_for("admin.toggle_admin", user_id=user.id), data={})
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_invalid_bool_field_returns_bad_request(
    client: FlaskClient, user: User
) -> None:
    response = client.post(
        url_for("admin.toggle_admin", user_id=user.id),
        data={"is_admin": "not-a-bool"},
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_cautious_updates_user(client: FlaskClient, user: User) -> None:
    assert user.is_cautious is False

    response = client.post(
        url_for("admin.toggle_cautious", user_id=user.id),
        data={"is_cautious": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.is_cautious is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_suspended_updates_user(client: FlaskClient, user: User) -> None:
    assert user.is_suspended is False

    response = client.post(
        url_for("admin.toggle_suspended", user_id=user.id),
        data={"is_suspended": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.is_suspended is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_suspended_clears_user_state(client: FlaskClient, user: User) -> None:
    user.is_suspended = True
    db.session.commit()

    response = client.post(
        url_for("admin.toggle_suspended", user_id=user.id),
        data={"is_suspended": "false"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.is_suspended is False


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_account_category_validates_and_updates_user(
    client: FlaskClient,
    user: User,
) -> None:
    assert user.account_category is None

    response = client.post(
        url_for("admin.update_account_category", user_id=user.id),
        data={"account_category": AccountCategory.LAWYER.value},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "User account category updated." in response.text

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.account_category == AccountCategory.LAWYER.value

    response = client.post(
        url_for("admin.update_account_category", user_id=user.id),
        data={"account_category": "not-a-real-category"},
    )
    assert response.status_code == 400

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.account_category == AccountCategory.LAWYER.value

    response = client.post(
        url_for("admin.update_account_category", user_id=user.id),
        data={"account_category": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.account_category is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_account_category_rejects_missing_field_and_unknown_user(
    client: FlaskClient, user: User
) -> None:
    response = client.post(url_for("admin.update_account_category", user_id=user.id), data={})
    assert response.status_code == 400

    response = client.post(
        url_for("admin.update_account_category", user_id=999999),
        data={"account_category": AccountCategory.LAWYER.value},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_cautious_user_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.toggle_cautious", user_id=999999),
        data={"is_cautious": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_user")
def test_toggle_suspended_forbidden_for_non_admin(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("admin.toggle_suspended", user_id=user.id),
        data={"is_suspended": "true"},
    )
    assert response.status_code == 403

    refreshed_user = db.session.get(User, user.id)
    assert refreshed_user is not None
    assert refreshed_user.is_suspended is False


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_suspended_user_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.toggle_suspended", user_id=999999),
        data={"is_suspended": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_user_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.toggle_admin", user_id=999999),
        data={"is_admin": "true"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_tier_missing_tier_returns_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.update_tier", tier_id=999999),
        data={"monthly_price": "20"},
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_tier_missing_monthly_price(client: FlaskClient) -> None:
    response = client.post(url_for("admin.update_tier", tier_id=Tier.business_tier_id()), data={})
    assert response.status_code == 302


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_tier_invalid_monthly_price(client: FlaskClient) -> None:
    response = client.post(
        url_for("admin.update_tier", tier_id=Tier.business_tier_id()),
        data={"monthly_price": "abc"},
    )
    assert response.status_code == 302


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_update_tier_success(client: FlaskClient, app: Flask, mocker: MockFixture) -> None:
    update_price = mocker.patch("hushline.admin.update_price")
    response = client.post(
        url_for("admin.update_tier", tier_id=Tier.business_tier_id()),
        data={"monthly_price": "25.50"},
    )
    assert response.status_code == 302

    business_tier = db.session.get(Tier, Tier.business_tier_id())
    assert business_tier is not None
    assert business_tier.monthly_amount == 2550
    update_price.assert_called_once_with(business_tier)


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_not_found(client: FlaskClient) -> None:
    response = client.post(url_for("admin.delete_user", user_id=999999))
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_username_not_found(client: FlaskClient) -> None:
    response = client.post(url_for("admin.delete_username", username_id=999999))
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_primary_username_blocked(client: FlaskClient, admin_user: User) -> None:
    response = client.post(
        url_for("admin.delete_username", username_id=admin_user.primary_username.id)
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_csrf_invalid_token_returns_bad_request(
    app: Flask, client: FlaskClient, mocker: MockFixture, user: User
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    mocker.patch("hushline.admin.validate_csrf", side_effect=ValidationError("bad csrf"))
    response = client.post(
        url_for("admin.toggle_admin", user_id=user.id),
        data={"csrf_token": "bad", "is_admin": "true"},
    )
    assert response.status_code == 400

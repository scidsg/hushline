import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_profile_submission_data
from pytest_mock import MockFixture

from hushline.billing import get_provider
from hushline.db import db
from hushline.model import Message, Tier, User


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def configure(mocker: MockFixture) -> None:
        mocker.patch.dict("os.environ", {"BILLING_PROVIDER": "manual", "STRIPE_SECRET_KEY": ""})

    return configure


def test_manual_app_does_not_import_stripe(app: Flask) -> None:
    # A fresh interpreter prevents already-imported modules from hiding SDK dependencies.
    script = """
import builtins
original_import = builtins.__import__
def guard(name, *args, **kwargs):
    if name == 'stripe' or name.startswith('stripe.'):
        raise AssertionError('Manual deployment imported the Stripe SDK')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guard
from hushline import create_app
app = create_app()
assert app.extensions['billing_provider'].name == 'manual'
"""
    command = [sys.executable, "-c", script]
    subprocess.run(command, check=True, timeout=30)  # noqa: S603


@pytest.mark.usefixtures("_authenticated_user")
def test_manual_entitlements_work_without_payment_routes(
    app: Flask, client: FlaskClient, user: User
) -> None:
    assert get_provider().name == "manual"
    runner = app.test_cli_runner()
    assert runner.invoke(args=["billing", "configure"]).exit_code == 0
    result = runner.invoke(args=["billing", "set-tier", str(user.id), "business"])
    assert result.exit_code == 0, result.output
    db.session.refresh(user)
    assert user.is_business_tier
    assert user.has_active_premium_entitlement
    assert not user.is_current_paid_super_user
    assert user.primary_username.embed_owner_has_required_plan
    assert user.stripe_customer_id is None
    assert user.stripe_subscription_id is None

    for endpoint in ["inbox", "settings.profile", "settings.developer"]:
        response = client.get(url_for(endpoint))
        assert response.status_code == 200
        assert "stripe.com" not in response.headers["Content-Security-Policy"]
        assert "stripe.com" not in response.text
    for path in ["/premium/", "/premium/waiting", "/premium/select-tier"]:
        assert client.get(path).status_code == 404
    for path in ["/premium/upgrade", "/premium/webhook", "/premium/cancel"]:
        assert client.post(path).status_code == 404

    result = runner.invoke(args=["billing", "set-tier", str(user.id), "free"])
    assert result.exit_code == 0, result.output
    db.session.refresh(user)
    assert user.is_free_tier
    assert not user.has_active_premium_entitlement
    assert not user.primary_username.embed_owner_has_required_plan
    assert client.get(url_for("settings.developer")).status_code == 401


def test_manual_command_rejects_provider_linked_accounts(app: Flask, user: User) -> None:
    user.stripe_customer_id = "cus_existing"
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["billing", "set-tier", str(user.id), "business"])
    assert result.exit_code != 0
    assert "existing provider billing" in result.output
    db.session.refresh(user)
    assert user.is_free_tier


def test_manual_command_rejects_missing_account(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["billing", "set-tier", "999999", "business"])
    assert result.exit_code != 0
    assert "Account not found" in result.output


def test_manual_configure_initializes_stable_tiers(app: Flask) -> None:
    db.session.execute(db.delete(Tier))
    db.session.commit()
    runner = app.test_cli_runner()
    assert runner.invoke(args=["billing", "configure"]).exit_code == 0
    assert runner.invoke(args=["billing", "configure"]).exit_code == 0
    assert Tier.free_tier() is not None
    assert Tier.business_tier() is not None
    assert db.session.scalar(db.select(db.func.count(Tier.id))) == 2


def test_manual_deployment_accepts_anonymous_disclosure(client: FlaskClient, user: User) -> None:
    user.pgp_key = Path("tests/test_pgp_key.txt").read_text()
    db.session.commit()
    data = get_profile_submission_data(client, user.primary_username.username)
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={**data, "field_0": "Anonymous", "field_1": "Manual deployment disclosure"},
    )
    assert response.status_code == 302
    message = db.session.scalar(
        db.select(Message).where(Message.username_id == user.primary_username.id)
    )
    assert message is not None


def test_manual_login_does_not_redirect_to_billing(
    client: FlaskClient, user: User, user_password: str
) -> None:
    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
    )
    assert response.status_code == 302
    assert "/premium" not in response.location

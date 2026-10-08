"""A gift is explicitly configured and never reissued after use or expiry."""

import pytest
import stripe
from flask import current_app
from pytest_mock import MockFixture

from hushline.single_tenant_client import ServiceUnavailable
from hushline.single_tenant_registration import prepare_registration_code
from tests.test_single_tenant_billing import live_context

CODE = "HL-LAUNCH-UNIT-TEST-ONLY"
COUPON = "first-year-unit-test"


def test_unconfigured_worker_does_not_create_stripe_objects(mocker: MockFixture) -> None:
    api = mocker.patch("hushline.single_tenant_registration.client")
    with live_context():
        prepare_registration_code()
    api.assert_not_called()


@pytest.mark.parametrize("active", [True, False])
def test_existing_code_is_verified_without_reactivation(mocker: MockFixture, active: bool) -> None:
    api = mocker.patch("hushline.single_tenant_registration.client").return_value
    api.coupons.retrieve.return_value = {
        "id": COUPON,
        "livemode": True,
        "percent_off": 100,
        "duration": "once",
        "max_redemptions": 1,
    }
    api.promotion_codes.list.return_value = {
        "data": [
            {
                "livemode": True,
                "code": CODE,
                "max_redemptions": 1,
                "coupon": {"id": COUPON},
                "active": active,
            }
        ]
    }
    with live_context():
        current_app.config.update(
            SINGLE_TENANT_ENABLED=True,
            SINGLE_TENANT_FREE_COUPON_ID=COUPON,
            SINGLE_TENANT_FREE_REGISTRATION_CODE=CODE,
        )
        prepare_registration_code()
    api.coupons.create.assert_not_called()
    api.promotion_codes.create.assert_not_called()


def test_foreign_coupon_code_cannot_be_replaced(mocker: MockFixture) -> None:
    api = mocker.patch("hushline.single_tenant_registration.client").return_value
    api.coupons.retrieve.return_value = {
        "id": COUPON,
        "livemode": True,
        "percent_off": 100,
        "duration": "once",
        "max_redemptions": 1,
    }
    api.promotion_codes.list.return_value = {
        "data": [
            {"livemode": True, "code": CODE, "max_redemptions": 1, "coupon": {"id": "foreign"}}
        ]
    }
    with live_context():
        current_app.config.update(
            SINGLE_TENANT_ENABLED=True,
            SINGLE_TENANT_FREE_COUPON_ID=COUPON,
            SINGLE_TENANT_FREE_REGISTRATION_CODE=CODE,
        )
        with pytest.raises(ServiceUnavailable):
            prepare_registration_code()
    api.promotion_codes.create.assert_not_called()


def test_gift_creation_is_live_single_use_and_idempotently_reserved(mocker: MockFixture) -> None:
    api = mocker.patch("hushline.single_tenant_registration.client").return_value
    api.coupons.retrieve.side_effect = stripe.InvalidRequestError(
        "Not found", param="id", code="resource_missing"
    )
    coupon = {
        "id": COUPON,
        "livemode": True,
        "percent_off": 100,
        "duration": "once",
        "max_redemptions": 1,
    }
    api.coupons.create.return_value = coupon
    api.promotion_codes.list.return_value = {"data": []}
    api.promotion_codes.create.return_value = {
        "livemode": True,
        "code": CODE,
        "max_redemptions": 1,
        "coupon": coupon,
    }
    mocker.patch("hushline.single_tenant_registration.time.time", return_value=1000)
    with live_context():
        current_app.config.update(
            SINGLE_TENANT_ENABLED=True,
            SINGLE_TENANT_FREE_COUPON_ID=COUPON,
            SINGLE_TENANT_FREE_REGISTRATION_CODE=CODE,
        )
        prepare_registration_code()
    values = api.coupons.create.call_args.args[0]
    assert values["percent_off"] == 100
    assert values["duration"] == "once"
    assert values["max_redemptions"] == 1
    assert "idempotency_key" in api.coupons.create.call_args.kwargs["options"]
    promotion = api.promotion_codes.create.call_args.args[0]
    assert promotion["max_redemptions"] == 1
    assert promotion["expires_at"] == 1000 + 7 * 24 * 60 * 60
    assert CODE not in api.promotion_codes.create.call_args.kwargs["options"]["idempotency_key"]


def test_permission_error_never_creates_a_replacement_coupon(mocker: MockFixture) -> None:
    api = mocker.patch("hushline.single_tenant_registration.client").return_value
    api.coupons.retrieve.side_effect = stripe.InvalidRequestError(
        "Denied", param="id", code="permission_denied"
    )
    with live_context():
        current_app.config.update(
            SINGLE_TENANT_ENABLED=True,
            SINGLE_TENANT_FREE_COUPON_ID=COUPON,
            SINGLE_TENANT_FREE_REGISTRATION_CODE=CODE,
        )
        with pytest.raises(ServiceUnavailable):
            prepare_registration_code()
    api.coupons.create.assert_not_called()
    api.promotion_codes.create.assert_not_called()

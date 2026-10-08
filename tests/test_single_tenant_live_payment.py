"""Workflow payment authority cannot be reused for another order or deadline."""

from datetime import UTC, datetime, timedelta

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_payment import validate_response, verify

ORDER = "a" * 32
OWNER = "b" * 64
NOW = datetime(2026, 10, 6, 2, tzinfo=UTC)


def response() -> tuple[dict, dict]:
    payment = {
        "payment_mode": "stripe_live",
        "license_limit": 2,
        "receipt": "c" * 32,
        "session_id": "cs_owned",
        "subscription_id": "sub_owned",
        "customer_id": "cus_owned",
        "invoice_id": "in_owned",
        "period_start": "2026-10-06T00:00:00+00:00",
        "period_end": "2027-10-06T00:00:00+00:00",
        "cancelled_at": None,
    }
    return {
        "order_id": ORDER,
        "owner": OWNER,
        "authorized": "provision",
        "checked_at": NOW.isoformat(),
        "payment": dict(payment),
    }, payment


def test_exact_fresh_live_payment_can_authorize_provisioning() -> None:
    data, expected = response()
    assert validate_response(data, ORDER, OWNER, "provision", expected, NOW) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("order_id", "f" * 32),
        ("owner", "f" * 64),
        ("authorized", "retire"),
        ("checked_at", (NOW - timedelta(seconds=61)).isoformat()),
        ("checked_at", (NOW + timedelta(seconds=1)).isoformat()),
    ],
)
def test_foreign_and_stale_authority_cannot_authorize_resources(field: str, value: object) -> None:
    data, expected = response()
    data[field] = value
    with pytest.raises(ValueError, match="verification|stale"):
        validate_response(data, ORDER, OWNER, "provision", expected, NOW)


def test_renewed_paid_year_blocks_old_retirement_request() -> None:
    data, expected = response()
    data["authorized"] = "retire"
    data["payment"]["period_end"] = "2028-10-06T00:00:00+00:00"
    with pytest.raises(ValueError, match="exact-order"):
        validate_response(data, ORDER, OWNER, "retire", expected, NOW)


def test_clock_expiry_and_cancellation_both_required_for_retirement() -> None:
    data, expected = response()
    data["authorized"] = "retire"
    expected["cancelled_at"] = "2026-10-06T01:00:00+00:00"
    data["payment"] = dict(expected)
    with pytest.raises(ValueError, match="paid-year expiry"):
        validate_response(data, ORDER, OWNER, "retire", expected, NOW)
    end = datetime(2027, 10, 6, tzinfo=UTC)
    data["checked_at"] = end.isoformat()
    assert validate_response(data, ORDER, OWNER, "retire", expected, end) == expected


@pytest.mark.parametrize(
    "origin",
    [
        "http://tips.hushline.app",
        "https://hushline.app.evil.example",
        "https://127.0.0.1",
        "https://tips.hushline.app/other",
        "https://user@tips.hushline.app",
    ],
)
def test_untrusted_origin_is_rejected_before_network_access(
    mocker: MockFixture, origin: str
) -> None:
    network = mocker.patch("scripts.single_tenant_live_payment.urllib.request.build_opener")
    _, expected = response()
    with pytest.raises(ValueError, match="trust root"):
        verify(origin, "a" * 64, ORDER, OWNER, "provision", expected)
    network.assert_not_called()


def test_explicit_fresh_destruction_authority_allows_early_retirement() -> None:
    data, expected = response()
    data["authorized"] = "retire"
    expected["cancelled_at"] = NOW.isoformat()
    data["payment"] = dict(expected)
    data["destroy_requested_at"] = NOW.isoformat()
    assert validate_response(data, ORDER, OWNER, "retire", expected, NOW) == expected
    data["destroy_requested_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="destruction"):
        validate_response(data, ORDER, OWNER, "retire", expected, NOW)

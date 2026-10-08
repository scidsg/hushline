"""Durable isolation and same-commit publication recovery without cloud writes."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from scripts.single_tenant_live_ledger import Ledger

ORDER = "a" * 32
OWNER = "b" * 64


def payload() -> dict[str, Any]:
    return {
        "order_id": ORDER,
        "owner": OWNER,
        "domain": "customer.foo",
        "state": "queued",
        "created_at": "2026-10-06T00:00:00+00:00",
        "verification": "test-verification",
        "payment": {
            "payment_mode": "stripe_live",
            "license_limit": 2,
            "receipt": "c" * 32,
            "session_id": "cs_live_owned",
            "subscription_id": "sub_owned",
            "customer_id": "cus_owned",
            "invoice_id": "in_owned",
            "period_start": "2026-10-06T00:00:00+00:00",
            "period_end": "2027-10-06T00:00:00+00:00",
            "cancelled_at": None,
        },
    }


@pytest.fixture()
def ledger(tmp_path: Path) -> Ledger:
    return Ledger.create(tmp_path / "customer.sqlite3", Fernet.generate_key())


def test_cannot_adopt_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "fixture.sqlite3"
    path.write_bytes(b"old fixture")
    with pytest.raises(FileExistsError):
        Ledger.create(path, Fernet.generate_key())
    assert path.read_bytes() == b"old fixture"


def test_ledger_identity_and_encryption_are_required(ledger: Ledger) -> None:
    with pytest.raises(ValueError, match="authentication"):
        Ledger(ledger.path, Fernet.generate_key())


def test_reservation_is_atomic_private_and_idempotent(ledger: Ledger) -> None:
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    ledger.reserve(ORDER, OWNER, data)
    assert ledger.get(ORDER, OWNER) == data
    assert len(ledger.pending()) == 1
    raw = ledger.path.read_bytes()
    assert OWNER.encode() not in raw
    assert b"cs_live_owned" not in raw
    assert b"customer.foo" not in raw
    with pytest.raises(ValueError, match="ownership"):
        ledger.get(ORDER, "d" * 64)


@pytest.mark.parametrize("field", ["domain", "receipt", "subscription_id"])
def test_one_domain_or_payment_cannot_fund_another_order(ledger: Ledger, field: str) -> None:
    original = payload()
    ledger.reserve(ORDER, OWNER, original)
    other = deepcopy(original)
    other.update(order_id="d" * 32, owner="e" * 64, domain="other.foo")
    other["payment"].update(receipt="f" * 32, subscription_id="sub_other")
    if field == "domain":
        other[field] = original[field]
    else:
        other["payment"][field] = original["payment"][field]
    with pytest.raises(ValueError, match="already belongs"):
        ledger.reserve(other["order_id"], other["owner"], other)
    assert len(ledger.pending()) == 1


def test_publication_recovery_preserves_exact_commits(tmp_path: Path) -> None:
    key = Fernet.generate_key()
    ledger = Ledger.create(tmp_path / "restart.sqlite3", key)
    ledger.reserve(ORDER, OWNER, payload())
    ledger.checkpoint(ORDER, "provision", 1, private_sha="1" * 40, public_sha="2" * 40)
    restarted = Ledger(ledger.path, key)
    assert restarted.pending()[0]["public_sha"] == "2" * 40
    with pytest.raises(ValueError, match="cannot replace"):
        ledger.checkpoint(ORDER, "provision", 1, private_sha="1" * 40, public_sha="3" * 40)
    ledger.published(ORDER, "provision", 1, private_sha="1" * 40, public_sha="2" * 40)
    assert ledger.pending() == []
    ledger.reserve(ORDER, OWNER, payload())
    assert ledger.pending() == []


def test_nonce_replay_survives_transactions(ledger: Ledger) -> None:
    assert ledger.nonce("a" * 32, now=100)
    assert not ledger.nonce("a" * 32, now=101)
    assert not ledger.nonce("invalid", now=101)


def test_expiry_requires_cancelled_unchanged_paid_year(ledger: Ledger) -> None:
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    after = datetime(2027, 10, 6, tzinfo=UTC)
    assert ledger.expiry(now=after) == 0
    paid = deepcopy(data["payment"])
    paid["cancelled_at"] = "2026-10-07T00:00:00+00:00"
    ledger.billing(ORDER, OWNER, paid)
    assert ledger.expiry(now=datetime(2027, 10, 5, tzinfo=UTC)) == 0
    assert ledger.expiry(now=after) == 1
    assert ledger.expiry(now=after) == 0
    request = next(row for row in ledger.pending() if row["purpose"] == "retire")
    assert request["payload"]["payment"] == paid
    assert request["revision"] == 2


def test_billing_withdrawal_and_renewal_do_not_rewrite_requests(ledger: Ledger) -> None:
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    cancelled = deepcopy(data["payment"])
    cancelled["cancelled_at"] = "2026-10-07T00:00:00+00:00"
    ledger.billing(ORDER, OWNER, cancelled)
    assert ledger.expiry(now=datetime(2027, 10, 6, tzinfo=UTC)) == 1
    ledger.billing(ORDER, OWNER, data["payment"])
    assert ledger.expiry(now=datetime(2027, 10, 6, tzinfo=UTC)) == 0
    old = next(row for row in ledger.pending() if row["purpose"] == "retire")
    assert old["payload"]["payment"]["cancelled_at"]
    assert ledger.get(ORDER, OWNER)["payment"]["cancelled_at"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"receipt": "foreign"},
        {"period_end": "2027-10-05T00:00:00+00:00"},
        {"invoice_id": "in_foreign"},
        {"license_limit": None},
    ],
)
def test_billing_cannot_replace_identity_or_shorten_term(
    ledger: Ledger, change: dict[str, Any]
) -> None:
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    paid = {**data["payment"], **change}
    with pytest.raises(ValueError, match="Billing|paid year"):
        ledger.billing(ORDER, OWNER, paid)
    assert ledger.get(ORDER, OWNER) == data


def test_only_verified_retirement_releases_hostname_for_a_new_order(ledger: Ledger) -> None:
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    payment = deepcopy(data["payment"])
    payment["cancelled_at"] = "2026-10-06T01:00:00+00:00"
    ledger.billing(ORDER, OWNER, payment)
    assert ledger.expiry(now=datetime(2027, 10, 7, tzinfo=UTC)) == 1
    request = next(row for row in ledger.pending() if row["purpose"] == "retire")
    ledger.checkpoint(
        ORDER, "retire", request["revision"], private_sha="3" * 40, public_sha="4" * 40
    )
    other = deepcopy(data)
    other.update(order_id="e" * 32, owner="f" * 64)
    other["payment"].update(receipt="e" * 32, subscription_id="sub_new", invoice_id="in_new")
    with pytest.raises(ValueError, match="already belongs"):
        ledger.reserve(other["order_id"], other["owner"], other)
    ledger.event(
        ORDER,
        OWNER,
        purpose="retire",
        revision=request["revision"],
        public_sha="4" * 40,
        result={"state": "retiring"},
    )
    with pytest.raises(ValueError, match="already belongs"):
        ledger.reserve(other["order_id"], other["owner"], other)
    ledger.event(
        ORDER,
        OWNER,
        purpose="retire",
        revision=request["revision"],
        public_sha="4" * 40,
        result={"state": "retired"},
    )
    ledger.reserve(other["order_id"], other["owner"], other)
    assert ledger.get(other["order_id"], other["owner"])["state"] == "queued"
    assert ledger.get(ORDER, OWNER)["state"] == "retired"
    with pytest.raises(ValueError, match="adopted or replaced"):
        ledger.reserve(ORDER, OWNER, data)


def test_immediate_destruction_is_owned_idempotent_and_keeps_paid_dates(ledger: Ledger) -> None:
    data = payload()
    data["state"] = "ready"
    data["payment"]["cancelled_at"] = "2026-10-06T02:00:00+00:00"
    ledger.reserve(ORDER, OWNER, data)
    with pytest.raises(ValueError, match="own"):
        ledger.destroy(ORDER, "d" * 64)
    ledger.destroy(ORDER, OWNER)
    ledger.destroy(ORDER, OWNER)
    current = ledger.get(ORDER, OWNER)
    assert current["state"] == "retiring"
    assert current["payment"]["period_end"] == data["payment"]["period_end"]
    assert len([item for item in ledger.pending() if item["purpose"] == "retire"]) == 1


def test_immediate_destruction_requires_confirmed_cancellation(ledger: Ledger) -> None:
    data = payload()
    data["state"] = "ready"
    ledger.reserve(ORDER, OWNER, data)
    with pytest.raises(ValueError, match="cancelled"):
        ledger.destroy(ORDER, OWNER)


@pytest.mark.parametrize("state", ["ready", "retiring", "failed", "retired"])
def test_hostname_returns_only_after_confirmed_retirement(ledger: Ledger, state: str) -> None:
    original = payload()
    original["state"] = state
    original["retirement_started"] = True
    original["last_workflow_event"] = {"purpose": "retire"}
    ledger.reserve(ORDER, OWNER, original)
    other = deepcopy(original)
    other.update(order_id="d" * 32, owner="e" * 64, state="queued")
    other["payment"].update(receipt="f" * 32, subscription_id="sub_new")
    if state == "retired":
        ledger.reserve(other["order_id"], other["owner"], other)
        assert ledger.get(ORDER, OWNER) == original
        assert ledger.get(other["order_id"], other["owner"]) == other
    else:
        with pytest.raises(ValueError, match="already belongs"):
            ledger.reserve(other["order_id"], other["owner"], other)


def test_unconfirmed_retired_label_does_not_release_hostname(ledger: Ledger) -> None:
    original = payload()
    original["state"] = "retired"
    ledger.reserve(ORDER, OWNER, original)
    other = deepcopy(original)
    other.update(order_id="d" * 32, owner="e" * 64)
    other["payment"].update(receipt="f" * 32, subscription_id="sub_new")
    with pytest.raises(ValueError, match="already belongs"):
        ledger.reserve(other["order_id"], other["owner"], other)


def test_release_is_durable_once_and_keeps_ready_state(ledger: Ledger) -> None:
    value = payload()
    value["state"] = "ready"
    ledger.reserve(ORDER, OWNER, value)
    target = {
        "tag": "v0.7.27",
        "source_sha": "1" * 40,
        "build_sha": "2" * 40,
        "previous_sha": "3" * 40,
    }
    ledger.queue_release(ORDER, OWNER, target)
    ledger.queue_release(ORDER, OWNER, target)
    upgrades = [r for r in ledger.pending() if r["purpose"] == "upgrade"]
    assert len(upgrades) == 1
    request = upgrades[0]
    ledger.checkpoint(
        ORDER, "upgrade", request["revision"], private_sha="4" * 40, public_sha="5" * 40
    )
    ledger.event(
        ORDER,
        OWNER,
        purpose="upgrade",
        revision=request["revision"],
        public_sha="5" * 40,
        result={
            "state": "upgraded",
            "release_tag": target["tag"],
            "release_source": target["source_sha"],
        },
    )
    actual = ledger.get(ORDER, OWNER)
    assert actual["state"] == "ready"
    assert actual["release"]["state"] == "upgraded"
    assert actual["payment"] == value["payment"]


def test_late_upgrade_cannot_restore_a_retiring_instance(ledger: Ledger) -> None:
    value = payload()
    value["state"] = "ready"
    value["payment"]["cancelled_at"] = "2026-10-07T00:00:00+00:00"
    ledger.reserve(ORDER, OWNER, value)
    target = {
        "tag": "v0.7.27",
        "source_sha": "1" * 40,
        "build_sha": "2" * 40,
        "previous_sha": "3" * 40,
    }
    ledger.queue_release(ORDER, OWNER, target)
    request = next(r for r in ledger.pending() if r["purpose"] == "upgrade")
    ledger.checkpoint(
        ORDER, "upgrade", request["revision"], private_sha="4" * 40, public_sha="5" * 40
    )
    ledger.destroy(ORDER, OWNER)
    ledger.event(
        ORDER,
        OWNER,
        purpose="upgrade",
        revision=request["revision"],
        public_sha="5" * 40,
        result={
            "state": "upgraded",
            "release_tag": target["tag"],
            "release_source": target["source_sha"],
        },
    )
    assert ledger.get(ORDER, OWNER)["state"] == "retiring"


@pytest.mark.parametrize("state", ["queued", "retiring", "retired", "failed"])
def test_rollout_excludes_instances_without_active_service(ledger: Ledger, state: str) -> None:
    value = payload()
    value["state"] = state
    ledger.reserve(ORDER, OWNER, value)
    assert ledger.release_candidates(now=datetime(2026, 10, 7, tzinfo=UTC)) == []


def test_rollout_keeps_cancelled_renewal_until_paid_term_ends(ledger: Ledger) -> None:
    value = payload()
    value["state"] = "ready"
    value["payment"]["cancelled_at"] = "2026-10-07T00:00:00+00:00"
    ledger.reserve(ORDER, OWNER, value)
    assert len(ledger.release_candidates(now=datetime(2026, 10, 7, tzinfo=UTC))) == 1
    assert ledger.release_candidates(now=datetime(2027, 10, 6, tzinfo=UTC)) == []


@pytest.mark.parametrize("bad", ["claim", "deployment_id", "failure_stage", "workflow_url"])
def test_upgrade_callback_cannot_change_claim_or_add_unbounded_fields(
    ledger: Ledger, bad: str
) -> None:
    value = payload()
    value["state"] = "ready"
    ledger.reserve(ORDER, OWNER, value)
    target = {
        "tag": "v0.7.27",
        "source_sha": "1" * 40,
        "build_sha": "2" * 40,
        "previous_sha": "3" * 40,
    }
    ledger.queue_release(ORDER, OWNER, target)
    revision = next(r["revision"] for r in ledger.pending() if r["purpose"] == "upgrade")
    ledger.checkpoint(ORDER, "upgrade", revision, private_sha="4" * 40, public_sha="5" * 40)
    result = {
        "state": "upgraded",
        "release_tag": target["tag"],
        "release_source": target["source_sha"],
        bad: "untrusted!",
    }
    with pytest.raises(ValueError, match="Invalid|escaped"):
        ledger.event(
            ORDER, OWNER, purpose="upgrade", revision=revision, public_sha="5" * 40, result=result
        )
    assert ledger.get(ORDER, OWNER)["state"] == "ready"
    assert ledger.get(ORDER, OWNER)["release"]["state"] == "queued"

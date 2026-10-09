"""New sales fail closed while durable publication and expiry remain recoverable."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from pytest_mock import MockFixture

from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_release import Release
from scripts.single_tenant_live_worker import reconcile
from tests.test_single_tenant_live_ledger import ORDER, OWNER, payload


@pytest.fixture()
def worker(tmp_path: Path, mocker: MockFixture) -> tuple[Ledger, Any, Any]:
    ledger = Ledger.create(tmp_path / "worker.sqlite3", Fernet.generate_key())
    ledger.reserve(ORDER, OWNER, payload())
    transport = Mock()
    collector = Mock()
    mocker.patch("scripts.single_tenant_live_worker.publisher", return_value=transport)
    mocker.patch("scripts.single_tenant_live_worker.Collector", return_value=collector)
    mocker.patch("scripts.single_tenant_live_worker.time.time", return_value=1000)
    return ledger, transport, collector


def test_unreleased_workflow_never_publishes_or_enables_sales(
    worker: tuple[Ledger, Any, Any],
) -> None:
    ledger, transport, collector = worker
    ledger.heartbeat(now=1000)
    collector.release.side_effect = ValueError("Not released")
    with pytest.raises(ValueError, match="Not released"):
        reconcile({}, ledger)
    transport.one.assert_not_called()
    assert ledger.healthy(now=1000) is False
    assert len(ledger.pending()) == 1


def test_failed_publication_preserves_order_and_withholds_readiness(
    worker: tuple[Ledger, Any, Any],
) -> None:
    ledger, transport, _ = worker
    transport.one.side_effect = ValueError("Publication interrupted")
    with pytest.raises(ValueError, match="publication"):
        reconcile({}, ledger)
    assert ledger.get(ORDER, OWNER)["publication_error"] is True
    assert len(ledger.pending()) == 1
    assert ledger.healthy(now=1000) is False


def test_healthy_worker_is_required_and_readiness_expires(worker: tuple[Ledger, Any, Any]) -> None:
    ledger, transport, collector = worker
    reconcile({}, ledger)
    collector.release.assert_called_once()
    collector.reconcile.assert_called_once()
    transport.one.assert_called_once()
    assert ledger.healthy(now=1000) is True
    assert ledger.healthy(now=1100) is False


@pytest.mark.parametrize("failed", [False, True])
def test_production_release_queues_active_tenant_without_losing_pending_publication(
    worker: tuple[Ledger, Any, Any], mocker: MockFixture, failed: bool
) -> None:
    ledger, transport, collector = worker
    value = payload()
    value.update(order_id="d" * 32, owner="e" * 64, domain="other.foo", state="ready")
    value["payment"].update(receipt="f" * 32, subscription_id="sub_other")
    ledger.reserve(value["order_id"], value["owner"], value)
    release = mocker.patch(
        "scripts.single_tenant_live_worker.resolve", return_value=Release("v0.7.27", "1" * 40)
    )
    if failed:
        transport.prepare_release.side_effect = ValueError("Branch changed")
        with pytest.raises(ValueError, match="reconciliation"):
            reconcile({"authority_origin": "https://tips.hushline.app"}, ledger)
    else:
        reconcile({"authority_origin": "https://tips.hushline.app"}, ledger)
    release.assert_called_once_with("https://tips.hushline.app", collector.document)
    transport.prepare_release.assert_called_once_with(value, "v0.7.27", "1" * 40)
    assert transport.one.call_count == 2
    assert ledger.healthy(now=1000) is not failed
    assert ledger.get(value["order_id"], value["owner"])["release_blocked"] is failed


def test_release_discovery_outage_does_not_stop_existing_publication(
    worker: tuple[Ledger, Any, Any], mocker: MockFixture
) -> None:
    ledger, transport, _ = worker
    value = payload()
    value.update(order_id="d" * 32, owner="e" * 64, domain="other.foo", state="ready")
    value["payment"].update(receipt="f" * 32, subscription_id="sub_other")
    ledger.reserve(value["order_id"], value["owner"], value)
    mocker.patch("scripts.single_tenant_live_worker.resolve", side_effect=ValueError("Unavailable"))
    with pytest.raises(ValueError, match="reconciliation"):
        reconcile({"authority_origin": "https://tips.hushline.app"}, ledger)
    assert transport.one.call_count == 2
    transport.prepare_release.assert_not_called()
    assert ledger.healthy(now=1000) is False


def test_unavailable_release_image_withholds_sales_after_durable_work(
    worker: tuple[Ledger, Any, Any],
) -> None:
    ledger, transport, collector = worker
    collector.image.side_effect = ValueError("Image provenance unavailable")
    with pytest.raises(ValueError, match="provenance"):
        reconcile({"authority_origin": "https://tips.hushline.app"}, ledger)
    transport.one.assert_called_once()
    assert ledger.healthy(now=1000) is False

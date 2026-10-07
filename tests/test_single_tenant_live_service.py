"""Signed controller isolation and paid-order acknowledgement without cloud calls."""

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from scripts.single_tenant_live_envelope import encrypt, keys
from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_service import create_service
from tests.test_single_tenant_live_ledger import ORDER, OWNER, payload

PORTAL = "1" * 64
WORKFLOW = "2" * 64


def signed(
    client: Any, action: str, data: dict[str, Any], *, key: str = PORTAL, nonce: str = "a" * 32
) -> Any:
    path = "/internal/single-tenant/" + action
    body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(int(time.time()))
    value = f"POST\n{path}\n{timestamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()
    signature = hmac.new(bytes.fromhex(key), value, hashlib.sha256).hexdigest()
    return client.post(
        path,
        data=body,
        headers={
            "X-Hushline-Timestamp": timestamp,
            "X-Hushline-Nonce": nonce,
            "X-Hushline-Signature": signature,
            "Content-Type": "application/json",
        },
    )


@pytest.fixture()
def controller(tmp_path: Path) -> tuple[Flask, Ledger]:
    ledger = Ledger.create(tmp_path / "service.sqlite3", Fernet.generate_key())
    service = create_service(
        ledger=ledger,
        portal_key=PORTAL,
        workflow_key=WORKFLOW,
        authority_origin="https://hushline.app",
        accepts_payments=False,
        healthy=lambda: True,
        billing_verify=lambda origin, key, order, owner, purpose, expected: expected,
    )
    return service, ledger


def test_unsigned_request_cannot_reserve_instance(controller: tuple[Flask, Ledger]) -> None:
    app, ledger = controller
    result = app.test_client().post("/internal/single-tenant/provision", json=payload())
    assert result.status_code == 401
    assert ledger.pending() == []


def test_capabilities_never_enable_sales_implicitly(controller: tuple[Flask, Ledger]) -> None:
    app, _ = controller
    result = signed(app.test_client(), "capabilities", {"order_id": ORDER, "owner": OWNER})
    assert result.status_code == 200
    assert result.json["accepts_payments"] is False
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_signed_provision_reserves_once_and_replay_is_rejected(
    controller: tuple[Flask, Ledger],
) -> None:
    app, ledger = controller
    data = {key: payload()[key] for key in ("order_id", "owner", "domain", "payment")}
    result = signed(app.test_client(), "provision", data)
    assert result.status_code == 200
    assert result.json["status"]["state"] == "queued"
    assert "claim" not in result.json
    assert "payment" not in result.json
    assert signed(app.test_client(), "provision", data).status_code == 401
    assert signed(app.test_client(), "provision", data, nonce="b" * 32).status_code == 200
    assert len(ledger.pending()) == 1


def test_payment_verification_failure_queues_nothing(
    controller: tuple[Flask, Ledger], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ledger = controller

    def unavailable(*args: Any) -> dict[str, Any]:
        raise ValueError("Authority unavailable")

    app = create_service(
        ledger=ledger,
        portal_key=PORTAL,
        workflow_key=WORKFLOW,
        authority_origin="https://hushline.app",
        accepts_payments=False,
        healthy=lambda: False,
        billing_verify=unavailable,
    )
    data = {key: payload()[key] for key in ("order_id", "owner", "domain", "payment")}
    assert signed(app.test_client(), "provision", data).status_code == 409
    assert ledger.pending() == []


def test_foreign_owner_cannot_read_status(controller: tuple[Flask, Ledger]) -> None:
    app, ledger = controller
    ledger.reserve(ORDER, OWNER, payload())
    result = signed(app.test_client(), "status", {"order_id": ORDER, "owner": "f" * 64})
    assert result.status_code == 409


def test_billing_sync_does_not_call_locked_portal(controller: tuple[Flask, Ledger]) -> None:
    app, ledger = controller
    data = payload()
    ledger.reserve(ORDER, OWNER, data)
    data["payment"]["cancelled_at"] = "2026-10-06T01:00:00+00:00"
    result = signed(
        app.test_client(),
        "billing-sync",
        {"order_id": ORDER, "owner": OWNER, "payment": data["payment"]},
    )
    assert result.status_code == 200
    assert ledger.get(ORDER, OWNER)["payment"]["cancelled_at"]


def test_portal_key_cannot_publish_workflow_result(controller: tuple[Flask, Ledger]) -> None:
    app, _ = controller
    result = signed(app.test_client(), "workflow-result", {"order_id": ORDER, "owner": OWNER})
    assert result.status_code == 401


def test_matching_workflow_preserves_successful_checks(controller: tuple[Flask, Ledger]) -> None:
    app, ledger = controller
    private, public = keys()
    ledger.reserve(
        ORDER, OWNER, {**payload(), "claim_private_key": private, "claim_public_key": public}
    )
    ledger.published(ORDER, "provision", 1, private_sha="1" * 40, public_sha="2" * 40)
    data = {
        "order_id": ORDER,
        "owner": OWNER,
        "purpose": "provision",
        "revision": 1,
        "public_sha": "2" * 40,
        "result": encrypt(public, {"state": "provisioning", "checks": {"infrastructure": True}}),
    }
    assert signed(app.test_client(), "workflow-result", data, key=WORKFLOW).status_code == 200
    data["result"] = encrypt(
        public,
        {
            "state": "failed",
            "failure_stage": "configuration",
            "checks": {"configuration": False, "infrastructure": False},
        },
    )
    assert (
        signed(app.test_client(), "workflow-result", data, key=WORKFLOW, nonce="b" * 32).status_code
        == 200
    )
    assert ledger.get(ORDER, OWNER)["checks"] == {"infrastructure": True, "configuration": False}

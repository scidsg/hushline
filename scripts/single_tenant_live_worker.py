"""Explicit private configuration, controller factory and automatic expiry worker.

This installer does not enable live sales, alter production configuration, or
initialize a database implicitly. Use a new customer-only ledger and reviewed
release configuration. Publishing recovers the same commits; cloud runs do not
retry or adopt failed provisioning resources.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask

from scripts.single_tenant_live_collect import Collector
from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_publish import Publisher
from scripts.single_tenant_live_service import create_service
from scripts.single_tenant_live_storage import require_storage_path

MAX_CONFIG_BYTES = 16384


def private_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Private controller configuration must be owner-only")
    value = path.read_bytes()
    if len(value) > MAX_CONFIG_BYTES:
        raise ValueError("Private controller configuration exceeded safety limit")
    return value


def configuration() -> dict[str, Any]:
    filename = os.environ.get("SINGLE_TENANT_CONTROL_CONFIG", "")
    if not filename:
        raise ValueError("An explicit reviewed controller configuration is required")
    values = json.loads(private_file(Path(filename)))
    expected = {
        "namespace",
        "ledger_path",
        "ledger_key_path",
        "portal_key_path",
        "workflow_key_path",
        "authority_origin",
        "accepts_payments",
        "publisher",
    }
    if (
        not isinstance(values, dict)
        or set(values) != expected
        or values["namespace"] != "hushline-single-tenant"
        or not isinstance(values["accepts_payments"], bool)
    ):
        raise ValueError("Controller configuration is not the isolated customer namespace")
    require_storage_path(Path(values["ledger_path"]))
    return values


def ledger(values: dict[str, Any]) -> Ledger:
    return Ledger(
        Path(values["ledger_path"]),
        private_file(Path(values["ledger_key_path"])).strip(),
        storage_guard=lambda: require_storage_path(Path(values["ledger_path"])),
    )


def create_app() -> Flask:
    values = configuration()
    store = ledger(values)
    return create_service(
        ledger=store,
        portal_key=private_file(Path(values["portal_key_path"])).decode().strip(),
        workflow_key=private_file(Path(values["workflow_key_path"])).decode().strip(),
        authority_origin=values["authority_origin"],
        accepts_payments=values["accepts_payments"],
        healthy=lambda: store.healthy(now=int(time.time())),
    )


def publisher(values: dict[str, Any], store: Ledger) -> Publisher:
    fields = values["publisher"]
    if set(fields) != {"app", "infra", "app_sha", "infra_sha", "artifacts", "signing_key"}:
        raise ValueError("Explicit immutable publisher source configuration is required")
    return Publisher(
        ledger=store,
        app=Path(fields["app"]),
        infra=Path(fields["infra"]),
        app_sha=fields["app_sha"],
        infra_sha=fields["infra_sha"],
        artifacts=Path(fields["artifacts"]),
        signing_key=Path(fields["signing_key"]),
    )


def reconcile(values: dict[str, Any], store: Ledger) -> None:
    store.unhealthy()
    transport = publisher(values, store)
    collector = Collector(ledger=store, publisher=transport)
    collector.release()
    collector.reconcile()
    store.expiry(now=datetime.now(UTC))
    failed = False
    for request in store.pending():
        try:
            transport.one(request)
            store.publication_notice(request["order_id"], failed=False)
        except (ValueError, OSError):
            store.publication_notice(request["order_id"], failed=True)
            failed = True
    if failed:
        raise ValueError("An original request publication needs reconciliation")
    # This heartbeat proves the automatic worker and trusted Git transport work;
    # live sales still need the separate explicit release feature flag.
    store.heartbeat(now=int(time.time()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        values = configuration()
        if args.initialize:
            Ledger.create(
                Path(values["ledger_path"]),
                private_file(Path(values["ledger_key_path"])).strip(),
                storage_guard=lambda: require_storage_path(Path(values["ledger_path"])),
            )
            return
        store = ledger(values)
        while True:
            try:
                reconcile(values, store)
            except (ValueError, OSError):
                # Fail closed for new sales until a healthy worker pass. Existing
                # obligations remain durable; never expose private subprocess output.
                if args.once:
                    raise ValueError("Customer reconciliation failed") from None
            if args.once:
                return
            time.sleep(30)
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit(
            "Single Tenant controller stopped; inspect sanitized stage diagnostics"
        ) from None


if __name__ == "__main__":
    main()

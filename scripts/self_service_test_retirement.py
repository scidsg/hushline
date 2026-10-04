"""Annual cancellation proof for the original disposable instance only."""

from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from scripts import self_service_test_ownership as ownership
from scripts.self_service_test_request import emit


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("A UTC billing timestamp is required")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("Billing timestamps must be UTC")
    return parsed


def validate(data: dict, current: datetime) -> None:
    if set(data) != {
        "order_id",
        "custom_domain",
        "receipt",
        "payment_mode",
        "period_start",
        "period_end",
        "cancelled_at",
    }:
        raise ValueError("Invalid annual cancellation proof")
    if data["order_id"] != ownership.RECOVERY_ORDER or data["custom_domain"] != "hushline.foo":
        raise ValueError("Retirement is restricted to the original test order")
    if (
        data["payment_mode"] != "simulated"
        or not isinstance(data["receipt"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", data["receipt"])
    ):
        raise ValueError("Invalid test payment receipt")
    start = timestamp(data["period_start"])
    end = timestamp(data["period_end"])
    cancelled = timestamp(data["cancelled_at"])
    day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
    if end != start.replace(year=start.year + 1, day=day):
        raise ValueError("A full paid annual period is required")
    if not start <= cancelled < end or current < end:
        raise ValueError("Cancellation is absent, invalid, or not yet due")


def prepare(path: Path, destination: Path) -> None:
    data = json.loads(path.read_text())
    validate(data, datetime.now(UTC))
    ids = ownership.owned(data["order_id"])
    if ids["digitalocean_app.staging"] != ownership.RECOVERY_APP or any(
        ids[address] != value for address, value in ownership.RECOVERY_IDS.items()
    ):
        raise ValueError("Original test resource identity changed")
    destination.write_text(json.dumps({"custom_domain": "hushline.foo"}))
    destination.chmod(0o600)
    name, _ = ownership.identity(data["order_id"])
    emit("order_id", data["order_id"])
    emit("workspace", name)


def guard(path: Path, latest: Path, plan: Path) -> None:
    data = json.loads(path.read_text())
    if data != json.loads(latest.read_text()):
        raise ValueError("Annual cancellation changed after planning")
    validate(data, datetime.now(UTC))
    ids = ownership.owned(data["order_id"])
    if ids["digitalocean_app.staging"] != ownership.RECOVERY_APP:
        raise ValueError("Original test app changed")
    ownership.guard_destroy(plan, data["order_id"], ids)


def pointer(path: Path) -> None:
    if not path.is_file():
        emit("enabled", "false")
        return
    data = json.loads(path.read_text())
    if set(data) != {"order_id", "config_ref"} or data["order_id"] != ownership.RECOVERY_ORDER:
        raise ValueError("Retirement pointer must identify the original test order")
    if not re.fullmatch(r"[a-f0-9]{40}", data["config_ref"]):
        raise ValueError("An immutable cancellation commit is required")
    emit("enabled", "true")
    emit("config_ref", data["config_ref"])
    emit("proof_path", f"self-service-tests/retirements/{data['order_id']}.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pointer", "prepare", "guard"])
    parser.add_argument("proof", type=Path)
    parser.add_argument("target", type=Path, nargs="?")
    parser.add_argument("plan", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "pointer":
        pointer(args.proof)
        return
    if args.target is None:
        raise ValueError("A target path is required")
    if args.action == "prepare":
        prepare(args.proof, args.target)
    else:
        if args.plan is None:
            raise ValueError("An exact saved deletion plan is required")
        guard(args.proof, args.target, args.plan)


if __name__ == "__main__":
    main()

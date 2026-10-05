"""Annual cancellation proof for the original disposable instance only."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import time
import urllib.error
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

from scripts import self_service_teardown_fixture as fixture
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
    expected = {
        "order_id",
        "custom_domain",
        "receipt",
        "payment_mode",
        "period_start",
        "period_end",
        "cancelled_at",
    }
    stripe_order = data.get("payment_mode") == "stripe_test"
    if set(data) != (expected | {"stripe_payment", "license_limit"} if stripe_order else expected):
        raise ValueError("Invalid annual cancellation proof")
    authorized = {ownership.RECOVERY_ORDER: "hushline.foo", fixture.ORDER: ""}
    if not stripe_order and (
        data["order_id"] not in authorized or data["custom_domain"] != authorized[data["order_id"]]
    ):
        raise ValueError("Retirement is restricted to explicitly authorized test orders")
    if (
        data["payment_mode"] not in {"simulated", "stripe_test"}
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
    if stripe_order:
        from scripts.self_service_stripe_payment import verify

        proof = data["stripe_payment"]
        if any(data[key] != proof[key] for key in ["receipt", "period_start", "period_end"]):
            raise ValueError("Retirement must preserve the verified Stripe billing term")
        if data["order_id"] in authorized or not re.fullmatch(r"[a-f0-9]{32}", data["order_id"]):
            raise ValueError("Stripe retirement cannot target a protected previous test order")
        verify(data, retiring=True)


PROJECT_ADDRESS = "digitalocean_project.staging"
SERVICE_ADDRESSES = ownership.ADDRESSES - {PROJECT_ADDRESS}


def recorded(order: str) -> tuple[dict, dict]:
    data = ownership.workspace(order)
    if data is None:
        raise ValueError("Owned retirement workspace is missing")
    manifest = ownership.validate_workspace(data, order)
    ids = manifest.get("resources") or {}
    if set(ids) != ownership.ADDRESSES:
        raise ValueError("Retirement requires the complete original ownership record")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]+", value)
        for value in ids.values()
    ):
        raise ValueError("Invalid recorded resource identities")
    name, _ = ownership.identity(order)
    if os.environ.get("WORKSPACE_NAME", name) != name:
        raise ValueError("Retirement workspace does not match the order")
    return ids, ownership.read_state(data)


def verify_absent(path: str) -> None:
    try:
        ownership.do(path)
    except urllib.error.HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            return
        raise
    raise ValueError("A recorded resource has not been confirmed absent")


def project_identity(value: dict, order: str, ids: dict) -> None:
    name, _ = ownership.identity(order)
    if (
        value.get("id") != ids[PROJECT_ADDRESS]
        or value.get("name") != name
        or value.get("description") != f"Owned disposable Hush Line test {name}"
        or value.get("is_default") is not False
    ):
        raise ValueError("Remaining project is not the recorded non-default order project")


def remaining_project(order: str) -> dict:
    ids, resources = recorded(order)
    if set(resources) != {PROJECT_ADDRESS}:
        raise ValueError("Project-only teardown requires exactly one remaining recorded project")
    project_identity(resources[PROJECT_ADDRESS], order, ids)
    verify_absent(f"/apps/{ids['digitalocean_app.staging']}")
    verify_absent(f"/databases/{ids['digitalocean_database_cluster.db']}")
    project = ownership.do(f"/projects/{ids[PROJECT_ADDRESS]}")["project"]
    project_identity(project, order, ids)
    # Provider membership removal can settle after DELETE succeeds. Never move members.
    expected = {
        f"do:app:{ids['digitalocean_app.staging']}",
        f"do:dbaas:{ids['digitalocean_database_cluster.db']}",
    }
    for _ in range(30):
        members = {
            item["urn"]
            for item in ownership.inventory(
                f"/projects/{ids[PROJECT_ADDRESS]}/resources", "resources"
            )
        }
        if not members:
            return ids
        if not members <= expected:
            raise ValueError("Remaining project contains resources with different ownership")
        time.sleep(2)
    raise ValueError("Remaining project has not settled to an empty membership list")


def all_absent(order: str) -> None:
    ids, resources = recorded(order)
    if resources:
        raise ValueError("Retirement state is not empty")
    verify_absent(f"/apps/{ids['digitalocean_app.staging']}")
    verify_absent(f"/databases/{ids['digitalocean_database_cluster.db']}")
    verify_absent(f"/projects/{ids[PROJECT_ADDRESS]}")


def authorize_ids(order: str, ids: dict, initial: bool = False) -> None:
    if order == fixture.ORDER:
        fixture.isolated(ids)
        if initial:
            fixture.preserve_original()
            Path(".retirement-fixture-ids.json").write_text(json.dumps(ids))
        else:
            fixture.check_original()
    elif order == ownership.RECOVERY_ORDER and (
        ids["digitalocean_app.staging"] != ownership.RECOVERY_APP
        or any(ids[address] != value for address, value in ownership.RECOVERY_IDS.items())
    ):
        raise ValueError("Original test resource identity changed")
    elif order not in {fixture.ORDER, ownership.RECOVERY_ORDER} and set(ids.values()) & {
        ownership.RECOVERY_APP,
        *ownership.RECOVERY_IDS.values(),
    }:
        raise ValueError("Stripe retirement overlaps a protected test identity")


def checkout_matches(path: Path, data: dict) -> None:
    if data["order_id"] != fixture.ORDER:
        return
    from scripts.self_service_fixture_checkout import contract

    paid_path = path.parent.parent / "lifecycle-orders" / f"{fixture.ORDER}.json"
    paid = json.loads(paid_path.read_text())
    contract(paid)
    keys = {"order_id", "receipt", "payment_mode", "period_start", "period_end"}
    if any(paid[key] != data[key] for key in keys):
        raise ValueError("Fixture retirement must preserve the original checkout term")


def prepare(path: Path, destination: Path) -> None:
    data = json.loads(path.read_text())
    validate(data, datetime.now(UTC))
    checkout_matches(path, data)
    order = data["order_id"]
    ids, resources = recorded(order)
    if set(resources) == ownership.ADDRESSES:
        ids = ownership.owned(order)
        emit("services", "true")
        emit("project", "true")
    elif set(resources) == {PROJECT_ADDRESS}:
        ids = remaining_project(order)
        emit("services", "false")
        emit("project", "true")
    elif not resources:
        all_absent(order)
        emit("services", "false")
        emit("project", "false")
    else:
        raise ValueError("Partial retirement is not a verified empty-project recovery")
    authorize_ids(order, ids, initial=True)
    destination.write_text(json.dumps({"custom_domain": data["custom_domain"]}))
    destination.chmod(0o600)
    name, _ = ownership.identity(order)
    emit("order_id", order)
    emit("workspace", name)


def guard_services(plan: dict, order: str, ids: dict) -> None:
    changes = plan.get("resource_changes", [])
    addresses = {item["address"] for item in changes}
    if len(addresses) != len(changes) or not SERVICE_ADDRESSES <= addresses <= ownership.ADDRESSES:
        raise ValueError("Service deletion escaped the original owned resources")
    _, current = recorded(order)
    before = {PROJECT_ADDRESS: current[PROJECT_ADDRESS]}
    for item in changes:
        change = item["change"]
        expected = ["no-op"] if item["address"] == PROJECT_ADDRESS else ["delete"]
        if (
            change["actions"] != expected
            or change.get("importing")
            or item.get("previous_address")
            or item.get("module_address")
        ):
            raise ValueError("Service phase may only delete the three recorded services")
        before[item["address"]] = change["before"]
    if ownership.validate_resources(before, order) != ids:
        raise ValueError("Service deletion plan contains different ownership IDs")


def guard_project(plan: dict, order: str, ids: dict) -> None:
    changes = plan.get("resource_changes", [])
    if len(changes) != 1 or changes[0]["address"] != PROJECT_ADDRESS:
        raise ValueError("Project phase may only delete the recorded empty project")
    item = changes[0]
    change = item["change"]
    if (
        change["actions"] != ["delete"]
        or change.get("importing")
        or item.get("previous_address")
        or item.get("module_address")
    ):
        raise ValueError("Project phase may only delete the recorded empty project")
    project_identity(change["before"], order, ids)
    if change["before"].get("resources"):
        raise ValueError("Project plan must refresh away all removed members before deletion")


def guard(path: Path, latest: Path, plan: Path) -> None:
    data = json.loads(path.read_text())
    if data != json.loads(latest.read_text()):
        raise ValueError("Annual cancellation changed after planning")
    validate(data, datetime.now(UTC))
    checkout_matches(path, data)
    order = data["order_id"]
    checkout_matches(latest, data)
    if os.environ.get("RETIREMENT_PHASE") == "services":
        ids = ownership.owned(order)
        authorize_ids(order, ids)
        guard_services(json.loads(plan.read_text()), order, ids)
    elif os.environ.get("RETIREMENT_PHASE") == "project":
        ids = remaining_project(order)
        authorize_ids(order, ids)
        guard_project(json.loads(plan.read_text()), order, ids)
    else:
        raise ValueError("An explicit guarded retirement phase is required")


def pointer(path: Path) -> None:
    if not path.is_file():
        emit("enabled", "false")
        return
    data = json.loads(path.read_text())
    stripe_pointer = (
        set(data) == {"order_id", "config_ref", "payment_mode"}
        and data.get("payment_mode") == "stripe_test"
    )
    if (
        not stripe_pointer
        and (
            set(data) != {"order_id", "config_ref"}
            or data["order_id"] not in {ownership.RECOVERY_ORDER, fixture.ORDER}
        )
    ) or not re.fullmatch(r"[a-f0-9]{32}", data["order_id"]):
        raise ValueError("Retirement pointer must identify an explicitly authorized test order")
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

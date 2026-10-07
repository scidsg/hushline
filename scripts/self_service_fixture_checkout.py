"""The one new fixture requires a signed, unexpired simulated annual payment."""

from __future__ import annotations

import argparse
import calendar
import ipaddress
import json
import re
import socket
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import override

from scripts import self_service_teardown_fixture as fixture
from scripts import self_service_test_ownership as ownership
from scripts.self_service_test_request import emit
from scripts.self_service_test_retirement import timestamp


def pointer(path: Path) -> None:
    data = json.loads(path.read_text())
    if (
        set(data) != {"order_id", "config_ref"}
        or data["order_id"] != fixture.ORDER
        or not isinstance(data["config_ref"], str)
        or not re.fullmatch(r"[a-f0-9]{40}", data["config_ref"])
    ):
        raise ValueError("Only the newly authorized fixture may be created")
    emit("enabled", "true")
    emit("config_ref", data["config_ref"])


def contract(data: dict) -> tuple[datetime, datetime]:
    if set(data) != {
        "order_id",
        "receipt",
        "source",
        "payment_mode",
        "period_start",
        "period_end",
        "license_limit",
    }:
        raise ValueError("Invalid fixture payment contract")
    if (
        data["order_id"] != fixture.ORDER
        or data["source"] != "fixture_checkout"
        or data["payment_mode"] != "simulated"
        or not isinstance(data["receipt"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", data["receipt"])
    ):
        raise ValueError("Fixture payment escaped its authorized scope")
    limit = data["license_limit"]
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ValueError("Invalid license selection")
    start, end = timestamp(data["period_start"]), timestamp(data["period_end"])
    day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
    if end != start.replace(year=start.year + 1, day=day):
        raise ValueError("Fixture still requires a complete calendar-year term")
    return start, end


def validate(data: dict, current: datetime) -> None:
    start, end = contract(data)
    if not start <= current < end <= current + timedelta(hours=26):
        raise ValueError("Fixture payment must be unexpired and confined to its test window")


def unchanged(path: Path, latest: Path) -> None:
    data = json.loads(path.read_text())
    if data != json.loads(latest.read_text()):
        raise ValueError("Fixture payment changed after planning")
    validate(data, datetime.now(UTC))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    @override
    def redirect_request(  # — standard library override signature
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


def healthy(path: Path) -> None:
    data = json.loads(path.read_text())
    if data["order_id"] != fixture.ORDER:
        raise ValueError("Health check must belong to the fresh fixture")
    ids = ownership.owned(fixture.ORDER)
    if ids != data["resources"]:
        raise ValueError("Fixture resource identity changed")
    app = ownership.do(f"/apps/{ids['digitalocean_app.staging']}")["app"]
    ingress = app.get("default_ingress", "").removeprefix("https://").rstrip("/")
    if not re.fullmatch(r"[a-z0-9-]+\.ondigitalocean\.app", ingress):
        raise ValueError("Fixture endpoint must be its owned provider HTTPS hostname")
    addresses = socket.getaddrinfo(ingress, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Fixture endpoint must resolve to public addresses")
    opener = urllib.request.build_opener(NoRedirect())
    for _ in range(120):
        try:
            with opener.open(f"https://{ingress}/health.json", timeout=8) as response:
                if (
                    response.status == HTTPStatus.OK
                    and json.loads(response.read(16384)).get("status") == "ok"
                ):
                    break
        except (OSError, ValueError):
            pass
        time.sleep(5)
    else:
        raise ValueError("Fixture HTTPS application health did not pass")
    fixture.check_original()
    data.update(ingress=ingress, https_ok=True)
    path.write_text(json.dumps(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pointer", "validate"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "pointer":
        pointer(args.path)
    else:
        validate(json.loads(args.path.read_text()), datetime.now(UTC))


if __name__ == "__main__":
    main()

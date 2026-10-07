"""Read only one immutable private order; never check out private repository code."""

import argparse
import base64
import json
import os
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_ORDER_BYTES = 32768
MAX_RESPONSE_BYTES = 65536


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise ValueError("Private order redirects are forbidden")


def json_document(raw: bytes) -> dict[str, Any]:
    try:
        document = json.loads(raw)
    except ValueError:
        raise ValueError("Private order JSON is invalid") from None
    if not isinstance(document, dict):
        raise ValueError("Private order JSON must be an object")
    return document


def read_order(order_id: str, revision: str, token: str) -> bytes:
    if (
        not re.fullmatch(r"[a-f0-9]{32}", order_id)
        or not re.fullmatch(r"[a-f0-9]{40}", revision)
        or not token
    ):
        raise ValueError("An immutable private order reference is required")
    path = f"self-service-tests/orders/{order_id}.json"
    request = Request(  # noqa: S310 — fixed HTTPS GitHub API, hex-only coordinates, no redirects
        f"https://api.github.com/repos/scidsg/hushline-infra/contents/{path}?ref={revision}",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if response.status != HTTPStatus.OK or len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Private order response exceeded its boundary")
    document = json_document(raw)
    if (
        not isinstance(document, dict)
        or document.get("type") != "file"
        or document.get("path") != path
        or document.get("encoding") != "base64"
        or isinstance(document.get("size"), bool)
        or not isinstance(document.get("size"), int)
        or not 0 < document["size"] <= MAX_ORDER_BYTES
        or not isinstance(document.get("content"), str)
    ):
        raise ValueError("Private order response did not match its reservation")
    try:
        content = base64.b64decode(document["content"].replace("\n", ""), validate=True)
    except ValueError:
        raise ValueError("Private order encoding is invalid") from None
    if len(content) != document["size"] or len(content) > MAX_ORDER_BYTES:
        raise ValueError("Private order size differs from the immutable response")
    order = json_document(content)
    if order.get("order_id") != order_id:
        raise ValueError("Private order identity does not match its reservation")
    return content


def save_order(destination: Path, order_id: str, content: bytes) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", order_id):
        raise ValueError("Invalid private order identity")
    # New data tree only: existing paths, symlinks and retries cannot overwrite.
    destination.mkdir(mode=0o700)
    orders = destination / "self-service-tests"
    orders.mkdir(mode=0o700)
    orders = orders / "orders"
    orders.mkdir(mode=0o700)
    descriptor = os.open(orders / f"{order_id}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        order_id = os.environ["PRIVATE_ORDER_ID"]
        content = read_order(order_id, os.environ["PRIVATE_CONFIG_REF"], os.environ["GH_TOKEN"])
        save_order(args.destination, order_id, content)
    except (OSError, ValueError, KeyError):
        raise SystemExit(
            "Private order read failed; credentials and response were not printed"
        ) from None


if __name__ == "__main__":
    main()

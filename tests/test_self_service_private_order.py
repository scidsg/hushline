"""Private order reads are immutable, bounded and cannot become executable code."""

import base64
import io
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockFixture

from scripts import self_service_private_order as private

ORDER = "a" * 32
REVISION = "b" * 40


def response(payload: bytes | None = None, **changes: Any) -> bytes:
    content = payload or json.dumps({"order_id": ORDER}).encode()
    document = {
        "type": "file",
        "path": f"self-service-tests/orders/{ORDER}.json",
        "encoding": "base64",
        "size": len(content),
        "content": base64.b64encode(content).decode(),
    }
    document.update(changes)
    return json.dumps(document).encode()


class Response(io.BytesIO):
    status = 200


def mocked_read(mocker: MockFixture, value: bytes) -> Any:
    stream = Response(value)
    opener = mocker.patch.object(private, "build_opener").return_value
    opener.open.return_value = stream
    return opener


def test_only_exact_revision_and_order_are_requested(mocker: MockFixture) -> None:
    opener = mocked_read(mocker, response())
    content = private.read_order(ORDER, REVISION, "fixture-token")
    request = opener.open.call_args.args[0]
    assert request.full_url == (
        f"https://api.github.com/repos/scidsg/hushline-infra/contents/"
        f"self-service-tests/orders/{ORDER}.json?ref={REVISION}"
    )
    assert json.loads(content) == {"order_id": ORDER}
    assert opener.open.call_args.kwargs == {"timeout": 30}


@pytest.mark.parametrize(
    ("order", "revision", "token"),
    [("../escape", REVISION, "fixture"), (ORDER, "main", "fixture"), (ORDER, REVISION, "")],
)
def test_mutable_refs_and_path_escape_stop_before_network(
    mocker: MockFixture, order: str, revision: str, token: str
) -> None:
    opener = mocker.patch.object(private, "build_opener")
    with pytest.raises(ValueError, match="immutable"):
        private.read_order(order, revision, token)
    opener.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        response(type="symlink"),
        response(path="scripts/untrusted.py"),
        response(size=private.MAX_ORDER_BYTES + 1),
        response(size=True),
        response(content="not-base64!"),
        response(json.dumps({"order_id": "c" * 32}).encode()),
        response(b"print('untrusted code')"),
        b"x" * (private.MAX_RESPONSE_BYTES + 1),
    ],
)
def test_foreign_or_unbounded_content_is_rejected(mocker: MockFixture, value: bytes) -> None:
    mocked_read(mocker, value)
    with pytest.raises(ValueError, match="Private order"):
        private.read_order(ORDER, REVISION, "fixture-token")


def test_redirect_cannot_forward_a_private_credential() -> None:
    with pytest.raises(ValueError, match="redirects"):
        private.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.test")


def test_private_data_cannot_overwrite_or_follow_an_existing_tree(tmp_path: Path) -> None:
    destination = tmp_path / "customer-config"
    content = json.dumps({"order_id": ORDER}).encode()
    private.save_order(destination, ORDER, content)
    path = destination / "self-service-tests" / "orders" / f"{ORDER}.json"
    assert path.read_bytes() == content
    assert path.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        private.save_order(destination, ORDER, b"replacement")
    link = tmp_path / "linked-config"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(FileExistsError):
        private.save_order(link, ORDER, b"replacement")
    assert path.read_bytes() == content

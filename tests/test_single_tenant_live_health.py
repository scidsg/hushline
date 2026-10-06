"""Public DNS ownership and pinned HTTPS cannot reach private networks."""

from typing import Any

import pytest

from scripts import single_tenant_live_health as health


def records(origin: str, hostname: str, kind: str) -> list[dict[str, Any]]:
    return {
        "TXT": [{"type": 16, "data": '"hushline-verification=owned"'}],
        "CNAME": [{"type": 5, "data": "owned.ondigitalocean.app."}],
        "A": [{"type": 1, "data": "162.159.140.98"}],
    }[kind]


def test_two_resolvers_require_exact_txt_and_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "answers", records)
    assert health.dns("customer.foo", "owned.ondigitalocean.app", "owned")
    assert not health.dns("customer.foo", "owned.ondigitalocean.app", "foreign")
    assert not health.dns("hushline.app", "owned.ondigitalocean.app", "owned")


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "100.100.63.77"]
)
def test_health_never_connects_to_private_or_tailnet_addresses(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(health, "answers", lambda *args: [{"type": 1, "data": address}])

    def forbidden(*args: Any) -> None:
        raise AssertionError("A private network must never be contacted")

    monkeypatch.setattr(health, "PinnedHTTPS", forbidden)
    assert not health.healthy("customer.foo")


def test_health_connects_to_exact_public_ip_and_fixed_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    class Response:
        status = 200

        def read(self, limit: int) -> bytes:
            return b'{"status":"ok"}'

    class Connection:
        def __init__(self, domain: str, address: str) -> None:
            seen.append((domain, address))

        def request(self, method: str, path: str, **kwargs: Any) -> None:
            seen.append((method, path))

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(health, "answers", records)
    monkeypatch.setattr(health, "PinnedHTTPS", Connection)
    assert health.healthy("customer.foo")
    assert seen == [("customer.foo", "162.159.140.98"), ("GET", "/health.json")]

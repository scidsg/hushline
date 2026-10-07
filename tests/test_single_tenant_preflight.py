"""Read-only setup never crosses production ownership or follows provider redirects."""

import secrets
import urllib.error
import urllib.request
from email.message import Message
from typing import Any

import pytest

from scripts.single_tenant_preflight import (
    DO_ACCOUNT,
    ORGANIZATION,
    PROJECT_NAME,
    TF_ROOT,
    NoRedirect,
    PreflightError,
    check,
    get,
)

TEAM = "12345678-1234-1234-1234-123456789abc"


def provider(
    *, team: str = "HushLineDev", project: bool = True, organization: str = ORGANIZATION
) -> tuple[Any, list[str]]:
    calls: list[str] = []

    def fetch(url: str, token: str) -> dict[str, Any]:
        assert token
        calls.append(url)
        if url == DO_ACCOUNT:
            return {"account": {"status": "active", "team": {"uuid": TEAM, "name": team}}}
        value = {
            "id": "prj-customer",
            "attributes": {"name": PROJECT_NAME},
            "relationships": {"organization": {"data": {"id": organization}}},
        }
        if "/projects?" in url:
            return {"data": [value] if project else [], "links": {"next": None}}
        assert url == TF_ROOT + "/projects/prj-customer"
        return {"data": value}

    return fetch, calls


def test_read_only_discovery_returns_only_customer_metadata() -> None:
    fetch, calls = provider()
    result = check(fetch, secrets.token_hex(16), secrets.token_hex(16))
    assert result == {
        "ready": True,
        "stage": "read-only-ownership-verified",
        "team_verified": True,
        "team_id": TEAM,
        "organization": ORGANIZATION,
        "project_id": "prj-customer",
    }
    assert len(calls) == 3


@pytest.mark.parametrize("team", ["Hush Line", "Other Tenant", ""])
def test_foreign_team_stops_before_terraform(team: str) -> None:
    fetch, calls = provider(team=team)
    with pytest.raises(PreflightError, match="ownership-mismatch"):
        check(fetch, secrets.token_hex(16), secrets.token_hex(16))
    assert calls == [DO_ACCOUNT]


def test_missing_project_does_not_create_one() -> None:
    fetch, calls = provider(project=False)
    result = check(fetch, secrets.token_hex(16), secrets.token_hex(16))
    assert result["ready"] is False
    assert result["stage"] == "customer-project-missing"
    assert len(calls) == 2


def test_project_in_other_organization_is_rejected() -> None:
    fetch, _ = provider(organization="foreign")
    with pytest.raises(PreflightError, match="ownership-mismatch"):
        check(fetch, secrets.token_hex(16), secrets.token_hex(16))


def test_unapproved_endpoint_rejected_before_network() -> None:
    with pytest.raises(PreflightError, match="endpoint-rejected"):
        get("https://untrusted.example/", secrets.token_hex(16))


def test_redirects_cannot_receive_credentials() -> None:
    assert (
        NoRedirect().redirect_request(
            None, None, 307, "redirect", None, "https://untrusted.example/"
        )
        is None
    )


def test_http_failure_never_exposes_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    token = secrets.token_hex(16)

    class FailedOpener:
        def open(self, request: Any, timeout: int) -> Any:
            raise urllib.error.HTTPError(DO_ACCOUNT, 401, token, Message(), None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: FailedOpener())
    with pytest.raises(PreflightError) as failure:
        get(DO_ACCOUNT, token)
    assert str(failure.value) == "digitalocean-account-http-401"
    assert token not in str(failure.value)

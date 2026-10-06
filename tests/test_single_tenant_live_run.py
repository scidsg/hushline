"""Privileged driver refuses untrusted triggers before contacting any provider."""

import json
import secrets
from pathlib import Path

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_run import origin, trusted_event, variables
from tests.test_single_tenant_live_ledger import payload


@pytest.mark.parametrize(
    "value",
    [
        "http://hushline.app",
        "https://hushline.app.evil.foo",
        "https://127.0.0.1",
        "https://user@hushline.app",
        "https://hushline.app/private",
        "https://hushline.app?redirect=1",
    ],
)
def test_control_origin_never_redirects_credentials(value: str) -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        origin(value)


@pytest.mark.parametrize("failure", ["attempt", "branch", "event", "repository", "upstream"])
def test_privileged_trigger_is_default_branch_first_attempt_only(
    tmp_path: Path, mocker: MockFixture, failure: str
) -> None:
    env = {
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "scidsg/hushline",
    }
    run = {
        "conclusion": "success",
        "event": "push",
        "name": "Validate paid Single Tenant request",
        "head_repository": {"full_name": "scidsg/hushline"},
        "head_sha": "a" * 40,
        "head_branch": "single-tenant-request/test",
    }
    filename = tmp_path / "event.json"
    filename.write_text(json.dumps({"workflow_run": run}))
    env["GITHUB_EVENT_PATH"] = str(filename)
    mocker.patch.dict("os.environ", env)
    assert trusted_event() == ("a" * 40, "single-tenant-request/test")
    if failure == "attempt":
        mocker.patch.dict("os.environ", {"GITHUB_RUN_ATTEMPT": "2"})
    elif failure == "branch":
        mocker.patch.dict("os.environ", {"GITHUB_REF": "refs/heads/customer"})
    elif failure == "event":
        mocker.patch.dict("os.environ", {"GITHUB_EVENT_NAME": "workflow_dispatch"})
    elif failure == "repository":
        mocker.patch.dict("os.environ", {"GITHUB_REPOSITORY": "foreign/hushline"})
    else:
        run["head_repository"]["full_name"] = "foreign/hushline"  # type: ignore[index]
        filename.write_text(json.dumps({"workflow_run": run}))
    with pytest.raises(ValueError, match="first-attempt"):
        trusted_event()


def test_retirement_never_reuses_an_app_secret_and_retains_existing_smtp(
    mocker: MockFixture,
) -> None:
    # Synthetic per-run credentials; no actual account is represented.
    smtp = {
        "SMTP_USERNAME": secrets.token_hex(8),
        "SMTP_PASSWORD": secrets.token_hex(16),
        "SMTP_SERVER": "mail.riseup.net",
        "SMTP_PORT": "587",
        "SMTP_ENCRYPTION": "StartTLS",
        "NOTIFICATIONS_ADDRESS": "existing-sender@riseup.net",
    }
    mocker.patch.dict(
        "os.environ",
        {"SINGLE_TENANT_SMTP_JSON": json.dumps(smtp), "SINGLE_TENANT_DO_TOKEN": "unit-only"},
    )
    first = variables(payload(), service=None)
    second = variables(payload(), service=None)
    assert first["single_tenant_smtp"] == smtp
    for name in ("SECRET_KEY", "ENCRYPTION_KEY", "SESSION_FERNET_KEY", "single_tenant_admin_claim"):
        assert first[name] != second[name]
    assert first["license_limit"] == 2
    assert first["branch"].startswith("single-tenant/")

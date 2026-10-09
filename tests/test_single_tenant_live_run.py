"""Privileged driver refuses untrusted triggers before contacting any provider."""

import json
import secrets
from pathlib import Path

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_run import GitHub, origin, trusted_event, variables
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


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/repos/scidsg/hushline/git/refs/heads/main", {"sha": "a" * 40, "force": False}),
        (
            "/repos/scidsg/hushline-infra/git/refs/heads/single-tenant/" + "a" * 32,
            {"sha": "a" * 40, "force": False},
        ),
        (
            "/repos/scidsg/hushline/git/refs/heads/single-tenant/" + "a" * 32,
            {"sha": "a" * 40, "force": True},
        ),
        (
            "/repos/scidsg/hushline/git/refs/heads/single-tenant/" + "a" * 32,
            {"sha": "main", "force": False},
        ),
        (
            "/repos/scidsg/hushline/git/refs/heads/single-tenant/" + "a" * 32,
            {"sha": "a" * 40, "force": False, "extra": True},
        ),
    ],
)
def test_github_ref_update_rejects_writes_outside_customer_scope(
    mocker: MockFixture, path: str, payload: dict[str, object]
) -> None:
    session = mocker.patch("scripts.single_tenant_live_run.requests.Session")
    with pytest.raises(ValueError, match="exact customer scope"):
        GitHub("fixture-only").request("PATCH", path, payload)
    session.assert_not_called()


def test_github_client_permits_exact_non_force_customer_upgrade(mocker: MockFixture) -> None:
    session = mocker.patch("scripts.single_tenant_live_run.requests.Session")
    client = session.return_value.__enter__.return_value
    response = client.request.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [b'{"object":{"sha":"approved"}}']
    path = "/repos/scidsg/hushline/git/refs/heads/single-tenant/" + "a" * 32
    payload = {"sha": "b" * 40, "force": False}
    assert GitHub("fixture-only").request("PATCH", path, payload) == {"object": {"sha": "approved"}}
    assert client.request.call_args.args == ("PATCH", "https://api.github.com" + path)
    assert client.request.call_args.kwargs["json"] == payload
    assert client.request.call_args.kwargs["allow_redirects"] is False
    assert client.trust_env is False


def test_release_archive_uses_fixed_cli_and_explicit_credential(mocker: MockFixture) -> None:
    mocker.patch("scripts.single_tenant_live_run.sys.platform", "linux")
    process = mocker.patch(
        "scripts.single_tenant_live_run.subprocess.run",
        return_value=mocker.Mock(returncode=0, stdout=b"zip-fixture"),
    )
    assert GitHub("fixture-only").artifact(123) == b"zip-fixture"
    assert process.call_args.args[0] == [
        "/usr/bin/gh",
        "api",
        "repos/scidsg/hushline/actions/artifacts/123/zip",
    ]
    assert process.call_args.kwargs["env"]["GH_TOKEN"] == "fixture-only"
    assert process.call_args.kwargs["env"]["GH_HOST"] == "github.com"
    assert process.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize("identifier", [True, 0, -1])
def test_release_archive_rejects_ambiguous_id_before_execution(
    mocker: MockFixture, identifier: int
) -> None:
    process = mocker.patch("scripts.single_tenant_live_run.subprocess.run")
    with pytest.raises(ValueError, match="artifact identity"):
        GitHub("fixture-only").artifact(identifier)
    process.assert_not_called()

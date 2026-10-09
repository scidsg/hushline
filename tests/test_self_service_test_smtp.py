"""SMTP update plans cannot escape the recorded original test instance."""

import copy
import json
from pathlib import Path

import pytest

from scripts import self_service_test_smtp as smtp
from tests.test_self_service_test_ownership import ORDER, resources


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "replace",
        "foreign-id",
        "database",
        "firewall",
        "project",
        "secret",
        "command",
        "source",
        "domain",
        "extra-resource",
        "recipient",
        "password",
        "tls",
        "port",
        "missing-field",
        "secret-scope",
        "baseline",
        "unknown-field",
        "duplicate-field",
        "sender-only",
        "sender-only-auth",
    ],
)
def test_guard_rejects_every_non_smtp_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: str | None
) -> None:
    state = resources()
    spec = state["digitalocean_app.staging"]["spec"][0]
    spec.update(
        {
            "service": [
                {
                    "name": name,
                    "git": [{"branch": "original"}],
                    "env": [
                        {
                            "key": "SECRET_KEY",
                            "value": "original-secret",
                            "type": "SECRET",
                            "scope": "RUN_TIME",
                        }
                    ],
                }
                for name in ["app", "app-onion"]
            ],
            "job": [{"name": "initialize-instance", "run_command": "original-command", "env": []}],
            "worker": [{"name": "onion-service", "env": []}],
            "domain": [{"name": "hushline.foo"}],
        }
    )
    expected = {
        "SMTP_USERNAME": "dedicated-test",
        "SMTP_PASSWORD": "dedicated-test-password",
        "SMTP_SERVER": "mail.riseup.net",
        "SMTP_PORT": "587",
        "SMTP_ENCRYPTION": "StartTLS",
        "NOTIFICATIONS_ADDRESS": "dedicated-test@riseup.net",
    }
    if problem in {"sender-only", "sender-only-auth"}:
        monkeypatch.setenv("SMTP_UPDATE_SENDER_ONLY", "true")
        for service in spec["service"]:
            service["env"] += [
                {
                    "key": key,
                    "value": "old-sender@example.test"
                    if key == "NOTIFICATIONS_ADDRESS"
                    else "old-authentication"
                    if key == "SMTP_PASSWORD" and problem == "sender-only-auth"
                    else value,
                    "type": "SECRET",
                    "scope": "RUN_TIME",
                }
                for key, value in expected.items()
            ]
    monkeypatch.setattr(smtp, "original", lambda order: (state, {}))
    monkeypatch.setattr(smtp, "approved_smtp", lambda: expected)
    ids = {address: value["id"] for address, value in state.items()}
    monkeypatch.setattr(smtp.ownership, "validate_resources", lambda data, order: ids)
    plan: dict = {
        "prior_state": {
            "values": {
                "root_module": {
                    "resources": [
                        {"address": address, "values": value} for address, value in state.items()
                    ]
                }
            }
        },
        "resource_changes": [
            {
                "address": address,
                "change": {
                    "actions": ["update"] if address == "digitalocean_app.staging" else ["no-op"],
                    "before": copy.deepcopy(value),
                    "after": copy.deepcopy(value),
                },
            }
            for address, value in state.items()
        ],
    }
    change = next(
        item["change"]
        for item in plan["resource_changes"]
        if item["address"] == "digitalocean_app.staging"
    )
    after = change["after"]["spec"][0]
    for service in after["service"]:
        service["env"] = [entry for entry in service["env"] if entry["key"] not in smtp.SMTP_KEYS]
        service["env"] += [
            {"key": key, "value": value, "type": "SECRET", "scope": "RUN_TIME"}
            for key, value in expected.items()
        ]
    fields = {entry["key"]: entry for entry in after["service"][0]["env"]}
    if problem == "replace":
        change["actions"] = ["delete", "create"]
    elif problem == "foreign-id":
        change["after"]["id"] = "another-app"
    elif problem in {"database", "firewall", "project"}:
        address = {
            "database": "digitalocean_database_cluster.db",
            "firewall": "digitalocean_database_firewall.staging",
            "project": "digitalocean_project.staging",
        }[problem]
        next(item["change"] for item in plan["resource_changes"] if item["address"] == address)[
            "actions"
        ] = ["update"]
    elif problem == "secret":
        fields["SECRET_KEY"]["value"] = "rotated"
    elif problem == "command":
        after["job"][0]["run_command"] = "changed"
    elif problem == "source":
        after["service"][0]["git"][0]["branch"] = "changed"
    elif problem == "domain":
        after["domain"][0]["name"] = "another.example"
    elif problem == "extra-resource":
        plan["resource_changes"].append({"address": "foreign"})
    elif problem in {"recipient", "password", "tls", "port", "unknown-field"}:
        key = {
            "recipient": "NOTIFICATIONS_ADDRESS",
            "password": "SMTP_PASSWORD",
            "tls": "SMTP_ENCRYPTION",
            "port": "SMTP_PORT",
            "unknown-field": "SMTP_USERNAME",
        }[problem]
        fields[key]["value"] = None if problem == "unknown-field" else "unapproved"
    elif problem == "missing-field":
        after["service"][0]["env"].remove(fields["SMTP_PASSWORD"])
    elif problem == "duplicate-field":
        after["service"][0]["env"].append(copy.deepcopy(fields["SMTP_PASSWORD"]))
    elif problem == "secret-scope":
        fields["SMTP_PASSWORD"]["scope"] = "RUN_AND_BUILD_TIME"
    elif problem == "baseline":
        after["job"][0]["run_command"] = "foreign-baseline"
        change["before"]["spec"][0]["job"][0]["run_command"] = "foreign-baseline"
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    if problem not in {None, "sender-only"}:
        with pytest.raises(ValueError, match="SMTP"):
            smtp.guard(path, ORDER)
    else:
        smtp.guard(path, ORDER)


def test_inspection_reports_presence_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    state = resources()
    live_spec = {
        "services": [
            {"name": "app", "envs": [{"key": "SMTP_PASSWORD", "value": "private-smtp-value"}]}
        ]
    }
    monkeypatch.setattr(
        smtp,
        "original",
        lambda order: (
            state,
            {
                "spec": live_spec,
                "active_deployment": {"id": "original-deployment", "spec": live_spec},
            },
        ),
    )
    monkeypatch.setattr(smtp.ownership, "do", lambda path: {"deployment": {"spec": live_spec}})
    result = smtp.inspect(ORDER)
    assert result["active_runtime_spec_smtp_presence"]["app"]["SMTP_PASSWORD"] is True
    assert result["active_runtime_spec_smtp_presence"]["app"]["SMTP_USERNAME"] is False
    assert "private-smtp-value" not in json.dumps(result)


def test_smtp_operations_reject_foreign_order_before_cloud_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object) -> None:
        pytest.fail("Foreign order reached cloud API")

    monkeypatch.setattr(smtp.ownership, "finalize_original", forbidden)
    with pytest.raises(ValueError, match="original authorized"):
        smtp.original(ORDER)


def test_workflow_does_not_reinitialize_or_provision_for_smtp() -> None:
    text = Path("tests/fixtures/archived-workflows/self_service_test_deploy.yml").read_text()
    job = text.split("  smtp-configure:\n")[1]
    assert "self-service-test-2447" in job
    assert "HUSHLINE_SINGLE_TENANT_SMTP_PASSWORD" in job
    assert "claim-repair" not in job
    assert "terraform-plan" in job
    assert "terraform-apply" in job
    assert job.index("Reject every change outside") < job.index("Apply the exact guarded")
    assert "secrets.DIGITALOCEAN_TOKEN" not in job


@pytest.mark.parametrize("username", ["dedicated-test", "dedicated-test@riseup.net"])
def test_sender_display_name_uses_authorized_address_and_dedicated_authentication(
    monkeypatch: pytest.MonkeyPatch, username: str
) -> None:
    from email.message import EmailMessage
    from email.utils import getaddresses, parseaddr

    monkeypatch.setenv("HUSHLINE_SINGLE_TENANT_SMTP_USERNAME", username)
    monkeypatch.setenv("HUSHLINE_SINGLE_TENANT_SMTP_PASSWORD", "dedicated-test-password")
    config = smtp.approved_smtp()
    message = EmailMessage()
    message["From"] = config["NOTIFICATIONS_ADDRESS"]
    assert parseaddr(str(message["From"])) == (
        "Hush Line Notifications",
        "notifications@hushline.app",
    )
    # smtplib.send_message derives the envelope address from this header.
    assert getaddresses([message["From"]])[0][1] == "notifications@hushline.app"
    assert config["SMTP_USERNAME"] == "dedicated-test"

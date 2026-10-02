"""Private requests and plans cannot escape the disposable test boundary."""

import base64
import json
from pathlib import Path

import pytest

from scripts.self_service_test_request import guard_plan, validate_config


def config() -> dict:
    return {
        "order_id": "a" * 32,
        "custom_domain": "tips.customer.org",
        "license_limit": None,
        "claim_public_key": base64.b64encode(b"-----BEGIN PUBLIC KEY-----\nplaceholder").decode(),
    }


@pytest.mark.parametrize(
    "host",
    [
        "hushline.app",
        "tips.hushline.app",
        "localhost",
        "a.local",
        "https://customer.org",
        "customer.org/",
        "127.0.0.1",
        "evil.org\nextra",
    ],
)
def test_rejects_unsafe_hostnames(host: str) -> None:
    request = config()
    request["custom_domain"] = host
    with pytest.raises(ValueError, match="Invalid|cannot|Plan"):
        validate_config(request)


@pytest.mark.parametrize("limit", [1, 13, 150, None])
def test_license_selection_has_no_twelve_license_cap(limit: int | None) -> None:
    request = config()
    request["license_limit"] = limit
    validate_config(request)


@pytest.mark.parametrize("limit", [0, -1, True, "unlimited"])
def test_rejects_invalid_license_selection(limit: object) -> None:
    request = config()
    request["license_limit"] = limit
    with pytest.raises(ValueError, match="Invalid|cannot|Plan"):
        validate_config(request)


@pytest.mark.parametrize(
    ("address", "actions", "name"),
    [
        ("digitalocean_app.production", ["create"], "hushline-staging-pr-123"),
        ("digitalocean_project.staging", ["delete", "create"], "hushline-staging-pr-123"),
        ("digitalocean_project.staging", ["create"], "shared-project"),
    ],
)
def test_rejects_shared_or_destructive_plans(
    tmp_path: Path, address: str, actions: list[str], name: str
) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "resource_changes": [
                    {"address": address, "change": {"actions": actions, "after": {"name": name}}}
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="Invalid|cannot|Plan"):
        guard_plan(plan, "hushline-staging-pr-123")


def test_accepts_isolated_plan(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "resource_changes": [
                    {
                        "address": "digitalocean_project.staging",
                        "change": {
                            "actions": ["create"],
                            "after": {"name": "hushline-staging-pr-123"},
                        },
                    }
                ]
            }
        )
    )
    guard_plan(plan, "hushline-staging-pr-123")

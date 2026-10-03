"""Private requests and plans cannot escape the disposable test boundary."""

import base64
import json
import secrets
import subprocess
from pathlib import Path

import pytest

from scripts.self_service_test_request import guard_plan, pointer, prepare, validate_config


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
        (
            "digitalocean_app.production",
            ["create"],
            "hushline-self-service-test-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        (
            "digitalocean_project.staging",
            ["delete", "create"],
            "hushline-self-service-test-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        ("digitalocean_project.staging", ["create"], "shared-project"),
    ],
)
def test_rejects_shared_or_destructive_plans(
    tmp_path: Path, address: str, actions: list[str], name: str
) -> None:
    plan = tmp_path / "plan.json"
    data = isolated_plan()
    data["resource_changes"][0] = {
        "address": address,
        "change": {"actions": actions, "after": {"name": name}},
    }
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid|cannot|Plan"):
        guard_plan(plan, "hushline-self-service-test-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")


def isolated_plan() -> dict:
    name = "hushline-self-service-test-" + "a" * 32
    values = {
        "digitalocean_project.staging": ({"name": name}, {}),
        "digitalocean_database_cluster.db": (
            {"name": name, "project_id": None},
            {"project_id": True},
        ),
        "digitalocean_app.staging": (
            {"spec": [{"name": name}], "project_id": None},
            {"project_id": True},
        ),
        "digitalocean_database_firewall.staging": ({"cluster_id": None}, {"cluster_id": True}),
    }
    return {
        "resource_changes": [
            {
                "address": address,
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": after,
                    "after_unknown": unknown,
                },
            }
            for address, (after, unknown) in values.items()
        ]
    }


def test_accepts_isolated_plan(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(isolated_plan()))
    guard_plan(plan, "hushline-self-service-test-" + "a" * 32)


@pytest.mark.parametrize(
    "actions", [["update"], ["no-op"], ["read"], ["delete"], ["delete", "create"]]
)
def test_existing_resource_actions_are_rejected(tmp_path: Path, actions: list[str]) -> None:
    data = isolated_plan()
    data["resource_changes"][0]["change"]["actions"] = actions
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cannot"):
        guard_plan(plan, "hushline-self-service-test-" + "a" * 32)


@pytest.mark.parametrize("key", ["before", "importing"])
def test_import_and_existing_state_are_rejected(tmp_path: Path, key: str) -> None:
    data = isolated_plan()
    data["resource_changes"][0]["change"][key] = {"id": "production-id"}
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cannot"):
        guard_plan(plan, "hushline-self-service-test-" + "a" * 32)


def test_attach_to_existing_project_is_rejected(tmp_path: Path) -> None:
    data = isolated_plan()
    data["resource_changes"][1]["change"]["after"]["project_id"] = "production-id"
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="existing project"):
        guard_plan(plan, "hushline-self-service-test-" + "a" * 32)


def openssl(*arguments: str, payload: bytes | None = None) -> bytes:
    command = ["/usr/bin/openssl", *arguments]
    result = subprocess.run(command, input=payload, capture_output=True, check=True)  # noqa: S603 — fixed executable and isolated test paths
    return result.stdout


def test_admin_claim_is_encrypted_and_plaintext_inputs_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    private_key = tmp_path / "private.pem"
    openssl(
        "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)
    )
    request = config()
    request["claim_public_key"] = base64.b64encode(
        openssl("pkey", "-in", str(private_key), "-pubout")
    ).decode()
    source = tmp_path / "request.json"
    source.write_text(json.dumps(request))
    inputs = tmp_path / "private-inputs.json"
    prepare(source, inputs)
    assert "::add-mask::" in capsys.readouterr().out
    assert inputs.stat().st_mode & 0o777 == 0o600
    invitation = json.loads(inputs.read_text())["self_service_claim_code"]
    ciphertext = (tmp_path / "self-service-status/admin-claim.enc").read_bytes()
    assert invitation.encode() not in ciphertext
    assert invitation not in (tmp_path / "outputs").read_text()
    plaintext = openssl(
        "pkeyutl",
        "-decrypt",
        "-inkey",
        str(private_key),
        "-pkeyopt",
        "rsa_padding_mode:oaep",
        "-pkeyopt",
        "rsa_oaep_md:sha256",
        payload=ciphertext,
    )
    assert secrets.compare_digest(plaintext, invitation.encode())


def test_pointer_locates_private_order_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    request = tmp_path / "pointer.json"
    request.write_text(json.dumps({"order_id": "a" * 32, "config_ref": "b" * 40}))
    pointer(request)
    assert f"order_path=self-service-tests/orders/{'a' * 32}.json" in output.read_text()

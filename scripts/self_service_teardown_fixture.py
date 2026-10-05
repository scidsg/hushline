"""One explicitly authorized fresh fixture, never an existing customer instance."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.error
from http import HTTPStatus
from pathlib import Path

from scripts import self_service_test_ownership as ownership
from scripts.self_service_test_request import guard_plan

ORDER = "1c08c360da985ca24e9e246371ffc97f"
RETIRED_ORDER = "d9a565c4b17aca835b1f23a0b69b482b"
SNAPSHOT = Path(".retirement-original-snapshot.json")


def original_snapshot() -> dict:
    ids = ownership.owned(ownership.RECOVERY_ORDER)
    if ids["digitalocean_app.staging"] != ownership.RECOVERY_APP or any(
        ids[address] != value for address, value in ownership.RECOVERY_IDS.items()
    ):
        raise ValueError("Original resource identity changed")
    data = ownership.workspace(ownership.RECOVERY_ORDER)
    if data is None:
        raise ValueError("Original workspace is missing")
    state = ownership.read_state(data)
    app = ownership.do(f"/apps/{ownership.RECOVERY_APP}")["app"]
    return {
        "ids": ids,
        "state": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
        "spec": hashlib.sha256(json.dumps(app["spec"], sort_keys=True).encode()).hexdigest(),
        "deployment": app.get("active_deployment", {}).get("id"),
    }


def preserve_original() -> None:
    SNAPSHOT.write_text(json.dumps(original_snapshot()))
    SNAPSHOT.chmod(0o600)


def check_original() -> None:
    if json.loads(SNAPSHOT.read_text()) != original_snapshot():
        raise ValueError("The original instance changed during fixture operations")


def isolated(ids: dict) -> None:
    original = ownership.owned(ownership.RECOVERY_ORDER)
    if set(ids.values()) & set(original.values()):
        raise ValueError("Fixture resources overlap the original instance")


def prepare(destination: Path) -> None:
    name, _ = ownership.identity(ORDER)
    values = {
        "DO_TOKEN": os.environ["STAGING_DO_TOKEN"],
        "name": name,
        "branch": f"self-service-test/{ORDER}",
        "custom_domain": "",
        "SECRET_KEY": secrets.token_hex(32),
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "SESSION_FERNET_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "self_service_claim_code": secrets.token_urlsafe(16),
        **{
            key: os.environ[key]
            for key in [
                "ONION_HOSTNAME",
                "ONION_PUBLIC_KEY_B64",
                "ONION_SECRET_KEY_B64",
            ]
        },
    }
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(values, output)


def guard_create(path: Path) -> None:
    name, _ = ownership.identity(ORDER)
    if os.environ.get("WORKSPACE_NAME") != name:
        raise ValueError("Fixture workspace is not the authorized fresh namespace")
    guard_plan(path, name)
    plan = json.loads(path.read_text())
    for change in plan["resource_changes"]:
        if change["address"] != "digitalocean_app.staging":
            continue
        spec = change["change"]["after"]["spec"][0]
        if spec.get("domain"):
            raise ValueError("A teardown fixture cannot claim a custom hostname")
        for component in spec.get("service", []) + spec.get("job", []):
            git = component.get("git", [{}])[0]
            if (
                git.get("branch") != f"self-service-test/{ORDER}"
                or git.get("repo_clone_url") != "https://github.com/scidsg/hushline.git"
            ):
                raise ValueError("Fixture build escaped its order-only branch")
            if any(env["key"].startswith("SMTP_") for env in component.get("env", [])):
                raise ValueError("Fixture cannot use customer SMTP credentials")
    check_original()


def created(destination: Path) -> None:
    ownership.record(ORDER)
    ids = ownership.owned(ORDER)
    isolated(ids)
    check_original()
    destination.write_text(
        json.dumps(
            {
                "order_id": ORDER,
                "resources": ids,
                "original_unchanged": True,
            }
        )
    )


def deleted() -> None:
    check_original()
    if ownership.workspace(ORDER) is not None:
        raise ValueError("Fixture workspace still exists")
    # The exact IDs were captured before destruction; never discover/adopt new IDs.
    ids = json.loads(Path(".retirement-fixture-ids.json").read_text())
    paths = {
        "digitalocean_app.staging": "/apps/",
        "digitalocean_database_cluster.db": "/databases/",
        "digitalocean_project.staging": "/projects/",
    }
    for address, prefix in paths.items():
        try:
            ownership.do(prefix + ids[address])
        except urllib.error.HTTPError as error:
            if error.code == HTTPStatus.NOT_FOUND:
                continue
            raise
        raise ValueError("A recorded fixture resource still exists")
    print("Fixture app, database, project and empty workspace are absent; original unchanged.")

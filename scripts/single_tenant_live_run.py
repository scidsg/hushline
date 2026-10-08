"""Trusted default-branch workflow entry point; secret output is never printed."""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from cryptography.fernet import Fernet

from scripts.single_tenant_live_envelope import encrypt
from scripts.single_tenant_live_hcp import HCP
from scripts.single_tenant_live_lifecycle import Lifecycle
from scripts.single_tenant_live_ownership import CloudAPI, Ownership, verify_team
from scripts.single_tenant_live_payment import verify
from scripts.single_tenant_live_plan import identity
from scripts.single_tenant_live_release import resolve
from scripts.single_tenant_live_request import Request, commit
from scripts.single_tenant_live_upgrade import Upgrade

MAX_BYTES = 1048576
MAX_HEALTH_BYTES = 16384


class GitHub:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("An explicit repository credential is required")
        self.token = token

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not path.startswith("/repos/scidsg/hushline/") and not path.startswith(
            "/repos/scidsg/hushline-infra/"
        ):
            raise ValueError("Repository request escaped its trust root")
        if method not in {"GET", "POST"}:
            raise ValueError("Unsupported repository request")
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.request(
                    method,
                    "https://api.github.com" + path,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + self.token,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=(5, 30),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if not HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES:
                        raise ValueError("Exact repository request failed")
                    data = bytearray()
                    for chunk in response.iter_content(8192):
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ValueError("Repository response exceeded safety limit")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("Invalid repository response")
            return result
        except requests.RequestException:
            raise ValueError("Exact repository request failed") from None

    def content(self, repo: str, path: str, sha: str) -> dict[str, Any]:
        result = self.request("GET", f"/repos/scidsg/{repo}/contents/{path}?ref={sha}")
        if (
            result.get("type") != "file"
            or result.get("encoding") != "base64"
            or result.get("size", MAX_BYTES + 1) > MAX_BYTES
        ):
            raise ValueError("Invalid immutable request document")
        value = json.loads(base64.b64decode(result["content"], validate=False))
        if not isinstance(value, dict):
            raise ValueError("Invalid immutable request document")
        return value

    def build(self, order: str, source: str) -> None:
        identity(order)
        # GitHub createRef fails on any existing ref. Never patch or force it.
        self.request(
            "POST",
            "/repos/scidsg/hushline/git/refs",
            {"ref": "refs/heads/single-tenant/" + order, "sha": source},
        )


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (parsed.hostname == "hushline.app" or parsed.hostname.endswith(".hushline.app"))
        or parsed.port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Controller trust root requires a configured Hush Line HTTPS origin")
    return value.rstrip("/")


def callback(url: str, key: str, body: dict[str, Any]) -> None:
    destination = origin(url) + "/internal/single-tenant/workflow-result"
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Dedicated workflow signing key is required")
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
    digest = hashlib.sha256(raw).hexdigest()
    signed = (
        f"POST\n/internal/single-tenant/workflow-result\n{timestamp}\n{nonce}\n{digest}"
    ).encode()
    signature = hmac.new(bytes.fromhex(key), signed, hashlib.sha256).hexdigest()
    with requests.Session() as client:
        client.trust_env = False
        with client.post(
            destination,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "X-Hushline-Timestamp": timestamp,
                "X-Hushline-Nonce": nonce,
                "X-Hushline-Signature": signature,
            },
            timeout=(5, 30),
            allow_redirects=False,
        ) as response:
            if response.status_code != HTTPStatus.OK:
                raise ValueError("Private workflow acknowledgement is pending")


@contextlib.contextmanager
def tor() -> Iterator[tuple[Path, str]]:
    with tempfile.TemporaryDirectory(prefix="owned-single-tenant-tor-") as temporary:
        path = Path(temporary)
        service = path / "service"
        service.mkdir(mode=0o700)
        with (path / "tor.log").open("wb") as output:
            process = subprocess.Popen(
                [  # noqa: S603 — fixed Tor binary and private paths
                    "/usr/bin/tor",
                    "--DataDirectory",
                    str(path / "data"),
                    "--SocksPort",
                    "9150",
                    "--HiddenServiceDir",
                    str(service),
                    "--HiddenServicePort",
                    "80 127.0.0.1:9",
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        try:
            for _ in range(60):
                if all(
                    (service / name).is_file()
                    for name in ("hostname", "hs_ed25519_public_key", "hs_ed25519_secret_key")
                ):
                    break
                if process.poll() is not None:
                    raise ValueError("Fresh onion identity generation failed")
                time.sleep(1)
            else:
                raise ValueError("Fresh onion identity generation timed out")
            yield service, "socks5h://127.0.0.1:9150"
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def onion(hostname: str, proxy: str) -> None:
    if not re.fullmatch(r"[a-z2-7]{56}\.onion", hostname) or proxy != "socks5h://127.0.0.1:9150":
        raise ValueError("Invalid owned onion probe")
    for _ in range(60):
        response = subprocess.run(
            [  # noqa: S603 — fixed curl, Tor proxy and validated onion hostname
                "/usr/bin/curl",
                "--silent",
                "--show-error",
                "--fail",
                "--max-time",
                "20",
                "--proxy",
                proxy,
                "http://" + hostname + "/health.json",
            ],
            capture_output=True,
            check=False,
            timeout=25,
        )
        if response.returncode == 0 and len(response.stdout) <= MAX_HEALTH_BYTES:
            try:
                if json.loads(response.stdout) == {"status": "ok"}:
                    return
            except ValueError:
                pass
        time.sleep(5)
    raise ValueError("Owned onion application health did not pass")


def variables(config: dict[str, Any], *, service: Path | None) -> dict[str, Any]:
    name, _ = identity(config["order_id"])
    smtp = json.loads(os.environ["SINGLE_TENANT_SMTP_JSON"])
    expected = {
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_SERVER",
        "SMTP_PORT",
        "SMTP_ENCRYPTION",
        "NOTIFICATIONS_ADDRESS",
    }
    if (
        not isinstance(smtp, dict)
        or set(smtp) != expected
        or smtp["SMTP_SERVER"] != "mail.riseup.net"
        or smtp["SMTP_PORT"] != "587"
        or smtp["SMTP_ENCRYPTION"] != "StartTLS"
        or any(not isinstance(value, str) or not value.strip() for value in smtp.values())
    ):
        raise ValueError("Complete existing dedicated Riseup routing is required")
    result = {
        "DO_TOKEN": os.environ["SINGLE_TENANT_DO_TOKEN"],
        "name": name,
        "branch": "single-tenant/" + config["order_id"],
        "license_limit": config["payment"]["license_limit"],
        "custom_domain": config["domain"],
        "SECRET_KEY": secrets.token_hex(32),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "SESSION_FERNET_KEY": Fernet.generate_key().decode(),
        "single_tenant_admin_claim": secrets.token_urlsafe(16),
        "single_tenant_smtp": smtp,
        "ONION_HOSTNAME": "a" * 56 + ".onion",
        "ONION_PUBLIC_KEY_B64": "unused-for-guarded-retirement",
        "ONION_SECRET_KEY_B64": "unused-for-guarded-retirement",
    }
    if service is not None:
        result.update(
            ONION_HOSTNAME=(service / "hostname").read_text().strip(),
            ONION_PUBLIC_KEY_B64=base64.b64encode(
                (service / "hs_ed25519_public_key").read_bytes()
            ).decode(),
            ONION_SECRET_KEY_B64=base64.b64encode(
                (service / "hs_ed25519_secret_key").read_bytes()
            ).decode(),
        )
    return result


def trusted_event() -> tuple[str, str]:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    run = event.get("workflow_run", {})
    if (
        os.environ.get("GITHUB_EVENT_NAME") != "workflow_run"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
        or os.environ.get("GITHUB_REPOSITORY") != "scidsg/hushline"
        or run.get("conclusion") != "success"
        or run.get("event") != "push"
        or run.get("name") != "Validate paid Single Tenant request"
        or run.get("head_repository", {}).get("full_name") != "scidsg/hushline"
    ):
        raise ValueError("Only first-attempt trusted default-branch request workflows may operate")
    return run["head_sha"], run["head_branch"]


def execute(root: Path, result_dir: Path) -> None:
    public_sha, branch = trusted_event()
    public = GitHub(os.environ["GITHUB_TOKEN"])
    source, infra = os.environ["SINGLE_TENANT_SOURCE_SHA"], os.environ["SINGLE_TENANT_INFRA_SHA"]
    pointer = Request(
        public.content("hushline", ".single-tenant-request.json", public_sha),
        branch=branch,
        source=source,
        infra=infra,
    )
    commit(
        public.request("GET", "/repos/scidsg/hushline/commits/" + public_sha),
        expected_parent=source,
        path=".single-tenant-request.json",
    )
    private = GitHub(os.environ["SINGLE_TENANT_CONFIG_READ_TOKEN"])
    commit(
        private.request("GET", "/repos/scidsg/hushline-infra/commits/" + pointer.config_ref),
        expected_parent=infra,
        path=pointer.filename,
    )
    config = pointer.private(
        private.content("hushline-infra", pointer.filename, pointer.config_ref)
    )
    control_origin = origin(os.environ["SINGLE_TENANT_CONTROL_ORIGIN"])
    authority_origin = origin(os.environ["SINGLE_TENANT_AUTHORITY_ORIGIN"])
    cloud = CloudAPI(
        terraform_token=os.environ["SINGLE_TENANT_TF_TOKEN"],
        digitalocean_token=os.environ["SINGLE_TENANT_DO_TOKEN"],
    )
    owner = Ownership(
        organization=os.environ["SINGLE_TENANT_TF_ORGANIZATION"],
        project_id=os.environ["SINGLE_TENANT_TF_PROJECT"],
        request=cloud.request,
    )
    stage = "authority"

    def progress(result: dict[str, Any]) -> None:
        if pointer.purpose == "upgrade":
            result.update(
                release_tag=config["release"]["tag"], release_source=config["release"]["source_sha"]
            )
        result["workflow_url"] = (
            "https://github.com/scidsg/hushline/actions/runs/" + os.environ["GITHUB_RUN_ID"]
        )
        body = {
            "order_id": pointer.order,
            "owner": config["owner"],
            "purpose": pointer.purpose,
            "revision": pointer.revision,
            "public_sha": public_sha,
            "result": encrypt(config["claim_public_key"], result),
        }
        result_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        filename = result_dir / "single-tenant-result.json"
        filename.write_text(json.dumps({"ciphertext": encrypt(config["claim_public_key"], body)}))
        filename.chmod(0o600)
        # A transient UI outage must not interrupt the owned cloud operation.
        # The encrypted artifact retains the exact result for worker reconciliation.
        with contextlib.suppress(requests.RequestException, OSError, ValueError):
            callback(control_origin, os.environ["SINGLE_TENANT_WORKFLOW_KEY"], body)

    def authority(data: dict[str, Any], purpose: str) -> dict[str, Any]:
        verify_team(cloud.request, os.environ["SINGLE_TENANT_DO_TEAM_ID"])
        return verify(
            authority_origin,
            os.environ["SINGLE_TENANT_PORTAL_KEY"],
            data["order_id"],
            data["owner"],
            purpose,
            data["payment"],
        )

    engine = Lifecycle(
        ownership=owner,
        hcp=HCP(request=cloud.request),
        authority=authority,
        branch=lambda order: public.build(order, config.get("build_source_sha", source)),
        progress=progress,
        onion_check=lambda hostname: onion(hostname, "socks5h://127.0.0.1:9150"),
    )
    try:
        if pointer.purpose == "provision":
            stage = "release"
            config["build_source_sha"] = resolve(
                authority_origin, lambda path: public.request("GET", "/" + path)
            ).source_sha
            stage = "onion-identity"
            with tor() as (service, _):
                stage = "provisioning"
                result = engine.provision(config, root, variables(config, service=service))
        elif pointer.purpose == "upgrade":
            upgrade = Upgrade(
                ownership=owner,
                hcp=engine.hcp,
                github=public.request,
                authority=authority,
                authority_origin=authority_origin,
                progress=progress,
            )
            stage = "upgrade"
            result = upgrade.run(config)
        else:
            stage = "retirement"
            result = engine.retire(config, root, variables(config, service=None))
        progress(result)
    except Exception:
        with contextlib.suppress(Exception):
            progress(
                {
                    "state": "upgrade_failed" if pointer.purpose == "upgrade" else "failed",
                    **({"checks": dict(engine.checks)} if pointer.purpose != "upgrade" else {}),
                    "failure_stage": upgrade.stage
                    if stage == "upgrade"
                    else (engine.stage if stage in {"provisioning", "retirement"} else stage),
                }
            )
        raise ValueError(
            "Exact-order lifecycle failed; resources left for guarded diagnosis"
        ) from None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    try:
        execute(args.root, args.result)
    except Exception:
        raise SystemExit(
            "Single Tenant workflow failed; private diagnostics were not printed"
        ) from None


if __name__ == "__main__":
    main()

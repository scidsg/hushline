"""Read-only development credential and customer-project discovery, without secrets in output."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

DO_ACCOUNT = "https://api.digitalocean.com/v2/account"
TF_ROOT = "https://app.terraform.io/api/v2"
ORGANIZATION = "hushline-single-tenant"
TEAM_ID = "dfa95e0b-9384-48b1-8711-95a3e3eafb48"
PROJECT_ID = "prj-o3XPaT8P9Q4GBZ1c"
PROJECT_NAME = "Hush Line Single Tenant"
MAX_BYTES = 1048576


class PreflightError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # noqa: PLR0913 — stdlib override requires this signature
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def get(url: str, token: str) -> dict[str, Any]:
    if url != DO_ACCOUNT and not re.fullmatch(
        re.escape(TF_ROOT)
        + r"/(?:organizations/hushline-single-tenant/projects\?page%5Bsize%5D=100"
        + r"&page%5Bnumber%5D=[1-9][0-9]?|projects/prj-[A-Za-z0-9]+)",
        url,
    ):
        raise PreflightError("read-only-endpoint-rejected")
    stage = (
        "digitalocean-account"
        if url == DO_ACCOUNT
        else "terraform-project-list"
        if "/organizations/" in url
        else "terraform-customer-project"
    )
    request = urllib.request.Request(  # noqa: S310 — exact HTTPS host/path whitelist above
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json" if url == DO_ACCOUNT else "application/vnd.api+json",
        },
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise PreflightError("provider-response-too-large")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise PreflightError("provider-response-invalid")
        return value
    except urllib.error.HTTPError as exc:
        raise PreflightError(stage + "-http-" + str(exc.code)) from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if isinstance(exc, PreflightError):
            raise
        raise PreflightError(stage + "-read-unavailable") from None


def check(
    fetch: Callable[[str, str], dict[str, Any]], do_token: str, tf_token: str
) -> dict[str, Any]:
    if not do_token or not tf_token:
        raise PreflightError("development-credentials-missing")
    account = fetch(DO_ACCOUNT, do_token).get("account", {})
    team = account.get("team", {})
    identifier = team.get("uuid", "")
    if (
        account.get("status") != "active"
        or team.get("name") != "HushLineDev"
        or identifier != TEAM_ID
        or not isinstance(identifier, str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identifier)
    ):
        raise PreflightError("development-team-ownership-mismatch")
    matches: list[dict[str, Any]] = []
    for page in range(1, 11):
        response = fetch(
            TF_ROOT
            + f"/organizations/{ORGANIZATION}/projects?page%5Bsize%5D=100&page%5Bnumber%5D={page}",
            tf_token,
        )
        values = response.get("data")
        if not isinstance(values, list):
            raise PreflightError("customer-project-response-invalid")
        matches.extend(
            p
            for p in values
            if isinstance(p, dict) and p.get("attributes", {}).get("name") == PROJECT_NAME
        )
        if not response.get("links", {}).get("next"):
            break
    else:
        raise PreflightError("customer-project-pagination-limit")
    result = {"team_verified": True, "team_id": identifier, "organization": ORGANIZATION}
    if not matches:
        return {**result, "ready": False, "stage": "customer-project-missing"}
    if len(matches) != 1 or not re.fullmatch(r"prj-[A-Za-z0-9]+", matches[0].get("id", "")):
        raise PreflightError("customer-project-ambiguous")
    project_id = matches[0]["id"]
    if project_id != PROJECT_ID:
        raise PreflightError("customer-project-ownership-mismatch")
    project = fetch(TF_ROOT + "/projects/" + project_id, tf_token).get("data", {})
    if (
        project.get("id") != project_id
        or project.get("attributes", {}).get("name") != PROJECT_NAME
        or project.get("relationships", {}).get("organization", {}).get("data", {}).get("id")
        != ORGANIZATION
    ):
        raise PreflightError("customer-project-ownership-mismatch")
    return {
        **result,
        "ready": True,
        "stage": "read-only-ownership-verified",
        "project_id": project_id,
    }


def main() -> None:
    if (
        os.environ.get("GITHUB_REPOSITORY") != "scidsg/hushline"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
    ):
        raise SystemExit("Read-only preflight requires the trusted default branch")
    try:
        result = check(
            get,
            os.environ.get("SINGLE_TENANT_DO_TOKEN", ""),
            os.environ.get("SINGLE_TENANT_TF_TOKEN", ""),
        )
    except PreflightError as exc:
        result = {"ready": False, "stage": str(exc)}
    except (KeyError, TypeError, AttributeError):
        result = {"ready": False, "stage": "provider-response-invalid"}
    print(json.dumps(result, sort_keys=True))
    if not result["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Resolve only the published, successfully built release actually serving production."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any
from urllib.parse import urlsplit

import requests

from scripts.release import ReleaseError, extract_live_version

MAX_HTML_BYTES = 262144


@dataclass(frozen=True)
class Release:
    tag: str
    source_sha: str


def production_version(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "tips.hushline.app"
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Release discovery requires the existing production portal")
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.get(
                origin.rstrip("/") + "/login", timeout=(5, 20), allow_redirects=False, stream=True
            ) as response:
                if response.status_code != HTTPStatus.OK:
                    raise ValueError("Production release is unavailable")
                data = bytearray()
                for chunk in response.iter_content(4096):
                    data.extend(chunk)
                    if len(data) > MAX_HTML_BYTES:
                        raise ValueError("Production release response exceeded its bound")
        return "v" + extract_live_version(data.decode("utf-8"))
    except (requests.RequestException, UnicodeError, ReleaseError):
        raise ValueError("Production release could not be verified") from None


def resolve(origin: str, document: Callable[[str], dict[str, Any]]) -> Release:
    tag = production_version(origin)
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("An exact production release version is required")
    prefix = "repos/scidsg/hushline/"
    release = document(prefix + "releases/tags/" + tag)
    commit = document(prefix + "commits/" + tag)
    sha = commit.get("sha", "")
    if (
        release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not re.fullmatch(r"[a-f0-9]{40}", sha)
        or commit.get("commit", {}).get("verification", {}).get("verified") is not True
    ):
        raise ValueError("Production does not identify a verified published release")
    comparison = document(prefix + "compare/" + sha + "...main")
    if comparison.get("status") not in {"ahead", "identical"}:
        raise ValueError("Release source is outside reviewed main history")
    runs = document(
        prefix
        + "actions/workflows/build-release.yml/runs?event=push&head_sha="
        + sha
        + "&status=success&per_page=100"
    )
    if not any(
        run.get("head_sha") == sha
        and run.get("head_branch") == tag
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("head_repository", {}).get("full_name") == "scidsg/hushline"
        for run in runs.get("workflow_runs", [])
    ):
        raise ValueError("The exact production release build has not succeeded")
    return Release(tag, sha)


def validate_target(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"tag", "source_sha", "build_sha", "previous_sha"}
        or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", value.get("tag", ""))
        or any(
            not re.fullmatch(r"[a-f0-9]{40}", value.get(key, ""))
            for key in ("source_sha", "build_sha", "previous_sha")
        )
    ):
        raise ValueError("Invalid immutable customer release target")

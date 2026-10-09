"""Bind deployed bytes to the successful production release build artifact."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable
from typing import Any

ARTIFACT_NAME = "single-tenant-release-image"
MAX_ARTIFACTS = 100
MAX_ARCHIVE_BYTES = 65536
MAX_DOCUMENT_BYTES = 1024
IMAGE = {"registry_type": "GHCR", "registry": "scidsg", "repository": "hushline/hushline"}


def image_source(digest: str) -> dict[str, str]:
    if not isinstance(digest, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is None:
        raise ValueError("An exact release image digest is required")
    return {**IMAGE, "digest": digest}


def release_image(
    tag: str,
    source: str,
    document: Callable[[str], dict[str, Any]],
    archive: Callable[[int], bytes],
) -> str:
    if (
        re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is None
        or re.fullmatch(r"[a-f0-9]{40}", source) is None
    ):
        raise ValueError("Exact release identity is required")
    prefix = "repos/scidsg/hushline/"
    runs = document(
        prefix
        + "actions/workflows/build-release.yml/runs?event=push&head_sha="
        + source
        + "&status=success&per_page=100"
    )
    candidates = [
        r
        for r in runs.get("workflow_runs", [])
        if r.get("head_sha") == source
        and r.get("head_branch") == tag
        and r.get("event") == "push"
        and r.get("conclusion") == "success"
        and r.get("status") == "completed"
        and r.get("head_repository", {}).get("full_name") == "scidsg/hushline"
        and r.get("run_attempt") == 1
        and isinstance(r.get("id"), int)
        and r["id"] > 0
    ]
    if len(candidates) != 1:
        raise ValueError("One original successful release build is required")
    run = candidates[0]
    result = document(prefix + "actions/runs/" + str(run["id"]) + "/artifacts?per_page=100")
    artifacts = [a for a in result.get("artifacts", []) if a.get("name") == ARTIFACT_NAME]
    if len(artifacts) != 1 or result.get("total_count", MAX_ARTIFACTS + 1) > MAX_ARTIFACTS:
        raise ValueError("The original release image artifact is unavailable")
    artifact = artifacts[0]
    if (
        artifact.get("expired") is not False
        or artifact.get("workflow_run", {}).get("id") != run["id"]
        or artifact.get("workflow_run", {}).get("head_sha") != source
        or not isinstance(artifact.get("id"), int)
        or artifact["id"] < 1
        or not isinstance(artifact.get("size_in_bytes"), int)
        or not 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES
    ):
        raise ValueError("Image artifact provenance is invalid")
    data = archive(artifact["id"])
    if (
        len(data) > MAX_ARCHIVE_BYTES
        or artifact.get("digest") != "sha256:" + hashlib.sha256(data).hexdigest()
    ):
        raise ValueError("Release image artifact integrity failed")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            files = bundle.infolist()
            if (
                len(files) != 1
                or files[0].filename != "release-image.json"
                or files[0].file_size > MAX_DOCUMENT_BYTES
            ):
                raise ValueError("Release image artifact escaped its exact document")
            value = json.loads(bundle.read(files[0]))
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid release image artifact") from None
    if (
        not isinstance(value, dict)
        or set(value) != {"tag", "source_sha", "digest", "image"}
        or value["tag"] != tag
        or value["source_sha"] != source
        or value["image"] != "ghcr.io/scidsg/hushline/hushline"
    ):
        raise ValueError("Release image belongs to another source")
    image_source(value["digest"])
    return str(value["digest"])

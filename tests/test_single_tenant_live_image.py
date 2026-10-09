"""Immutable images must come from the exact successful production build."""

import hashlib
import io
import json
import zipfile
from copy import deepcopy
from typing import Any

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_image import image_source, release_image

SOURCE = "1" * 40
DIGEST = "sha256:" + "b" * 64
TAG = "v0.7.27"


def evidence() -> tuple[list[dict[str, Any]], bytes]:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as bundle:
        bundle.writestr(
            "release-image.json",
            json.dumps(
                {
                    "tag": TAG,
                    "source_sha": SOURCE,
                    "digest": DIGEST,
                    "image": "ghcr.io/scidsg/hushline/hushline",
                }
            ),
        )
    archive = data.getvalue()
    return [
        {
            "workflow_runs": [
                {
                    "id": 123,
                    "run_attempt": 1,
                    "head_sha": SOURCE,
                    "head_branch": TAG,
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_repository": {"full_name": "scidsg/hushline"},
                }
            ]
        },
        {
            "total_count": 1,
            "artifacts": [
                {
                    "id": 456,
                    "name": "single-tenant-release-image",
                    "expired": False,
                    "size_in_bytes": len(archive),
                    "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
                    "workflow_run": {"id": 123, "head_sha": SOURCE},
                }
            ],
        },
    ], archive


def test_exact_build_digest_is_bound_to_source_and_archive(mocker: MockFixture) -> None:
    values, data = evidence()
    document, archive = mocker.Mock(side_effect=values), mocker.Mock(return_value=data)
    assert release_image(TAG, SOURCE, document, archive) == DIGEST
    archive.assert_called_once_with(456)
    assert image_source(DIGEST) == {
        "registry_type": "GHCR",
        "registry": "scidsg",
        "repository": "hushline/hushline",
        "digest": DIGEST,
    }


@pytest.mark.parametrize(
    "bad",
    [
        "source",
        "tag",
        "repo",
        "rerun",
        "failed",
        "expired",
        "duplicate",
        "other_run",
        "archive_digest",
        "oversized",
        "missing",
    ],
)
def test_untrusted_or_missing_build_cannot_select_runtime_bytes(
    mocker: MockFixture, bad: str
) -> None:
    values, data = evidence()
    run, artifact = values[0]["workflow_runs"][0], values[1]["artifacts"][0]
    if bad == "source":
        run["head_sha"] = "2" * 40
    elif bad == "tag":
        run["head_branch"] = "v0.7.28"
    elif bad == "repo":
        run["head_repository"]["full_name"] = "foreign/hushline"
    elif bad == "rerun":
        run["run_attempt"] = 2
    elif bad == "failed":
        run["conclusion"] = "failure"
    elif bad == "expired":
        artifact["expired"] = True
    elif bad == "duplicate":
        values[1]["artifacts"].append(deepcopy(artifact))
    elif bad == "other_run":
        artifact["workflow_run"]["id"] = 999
    elif bad == "archive_digest":
        artifact["digest"] = "sha256:" + "0" * 64
    elif bad == "oversized":
        artifact["size_in_bytes"] = 65537
    else:
        values[1]["artifacts"] = []
    with pytest.raises(ValueError, match="release|build|Image|artifact|digest"):
        release_image(TAG, SOURCE, mocker.Mock(side_effect=values), mocker.Mock(return_value=data))


@pytest.mark.parametrize(
    "digest", ["latest", "v0.7.27", "sha256:" + "z" * 64, "sha256:" + "a" * 63]
)
def test_mutable_or_invalid_image_identity_is_rejected(digest: str) -> None:
    with pytest.raises(ValueError, match="release|build|Image|artifact|digest"):
        image_source(digest)


@pytest.mark.parametrize(
    "bad", ["tag", "source_sha", "image", "digest", "extra", "path", "oversized"]
)
def test_archive_document_cannot_override_its_approved_release(
    mocker: MockFixture, bad: str
) -> None:
    values, _ = evidence()
    value = {
        "tag": TAG,
        "source_sha": SOURCE,
        "digest": DIGEST,
        "image": "ghcr.io/scidsg/hushline/hushline",
    }
    if bad == "extra":
        value["extra"] = "unapproved"
    elif bad not in {"path", "oversized"}:
        value[bad] = "foreign"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as bundle:
        bundle.writestr(
            "../release-image.json" if bad == "path" else "release-image.json",
            "x" * 1025 if bad == "oversized" else json.dumps(value),
        )
    archive = data.getvalue()
    values[1]["artifacts"][0].update(
        size_in_bytes=len(archive), digest="sha256:" + hashlib.sha256(archive).hexdigest()
    )
    with pytest.raises(ValueError, match="release|artifact|digest|source"):
        release_image(
            TAG, SOURCE, mocker.Mock(side_effect=values), mocker.Mock(return_value=archive)
        )

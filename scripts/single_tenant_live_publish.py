"""Publish signed immutable per-order requests, recovering only the same commits.

No working tree is changed. A create-only Git lease prohibits overwriting any
existing remote branch. Public commits contain only opaque request identities.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.single_tenant_live_ledger import Ledger
from scripts.single_tenant_live_plan import identity
from scripts.single_tenant_live_storage import require_storage_path

TRUSTED_PATH = "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PUBLIC_REMOTE = "git@github.com:scidsg/hushline.git"
PRIVATE_REMOTE = "git@github.com:scidsg/hushline-infra.git"


class Publisher:
    def __init__(  # noqa: PLR0913 — explicit repository trust roots and ledger
        self,
        *,
        ledger: Ledger,
        app: Path,
        infra: Path,
        app_sha: str,
        infra_sha: str,
        artifacts: Path,
        signing_key: Path,
    ) -> None:
        if any(not re.fullmatch(r"[a-f0-9]{40}", sha) for sha in (app_sha, infra_sha)):
            raise ValueError("Reviewed immutable source commits are required")
        for path in (app, infra, artifacts):
            require_storage_path(path)
        if not artifacts.is_dir():
            raise ValueError("Publisher artifacts require an existing private directory")
        if not signing_key.is_file() or not signing_key.resolve().is_relative_to(
            Path.home() / ".ssh"
        ):
            raise ValueError("An approved internal SSH signing identity is required")
        self.signing_key = signing_key
        self.ledger, self.app, self.infra = ledger, app, infra
        self.app_sha, self.infra_sha, self.artifacts = app_sha, infra_sha, artifacts
        for path, remote, sha in (
            (app, PUBLIC_REMOTE, app_sha),
            (infra, PRIVATE_REMOTE, infra_sha),
        ):
            if self.git(path, ["remote", "get-url", "origin"]).strip() != remote:
                raise ValueError("Publisher repository trust root does not match")
            if self.git(path, ["rev-parse", sha + "^{commit}"]).strip() != sha:
                raise ValueError("Publisher source commit is unavailable")
            self.git(path, ["verify-commit", sha])

    def git(
        self, path: Path, args: list[str], *, data: str | None = None, index: str | None = None
    ) -> str:
        environment = {
            **{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
            "PATH": TRUSTED_PATH,
            "GIT_TERMINAL_PROMPT": "0",
        }
        if index:
            environment["GIT_INDEX_FILE"] = index
        try:
            result = subprocess.run(
                [  # noqa: S603,S607 — trusted PATH and validated Git arguments
                    "git",
                    "-C",
                    str(path),
                    *args,
                ],
                input=data,
                text=True,
                capture_output=True,
                timeout=90,
                env=environment,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("Original Git request transport is unavailable") from None
        if result.returncode:
            raise ValueError("Signed request publication failed; no replacement request permitted")
        return result.stdout

    def commit(  # noqa: PLR0913 — fixed source, private file and signed commit message
        self, path: Path, base: str, filename: str, payload: dict[str, Any], message: str
    ) -> str:
        with tempfile.TemporaryDirectory(
            prefix="single-tenant-index-", dir=self.artifacts
        ) as temporary:
            index = str(Path(temporary) / "index")
            self.git(path, ["read-tree", base], index=index)
            blob = self.git(
                path,
                ["hash-object", "-w", "--stdin"],
                data=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            ).strip()
            self.git(
                path,
                ["update-index", "--add", "--cacheinfo", "100644," + blob + "," + filename],
                index=index,
            )
            tree = self.git(path, ["write-tree"], index=index).strip()
            sha = self.git(
                path,
                [
                    "-c",
                    "user.name=hushline-dev",
                    "-c",
                    "user.email=166439242+hushline-dev@users.noreply.github.com",
                    "-c",
                    "gpg.format=ssh",
                    "-c",
                    "user.signingkey=" + str(self.signing_key),
                    "commit-tree",
                    "-S",
                    tree,
                    "-p",
                    base,
                ],
                data=message + "\n",
            ).strip()
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                raise ValueError("Signed request commit was invalid")
            self.git(path, ["verify-commit", sha])
            return sha

    def signed_request(  # noqa: PLR0913 — exact immutable request and local retention identity
        self,
        path: Path,
        base: str,
        filename: str,
        payload: dict[str, Any],
        message: str,
        anchor: str,
    ) -> str:
        existing = self.git(
            path, ["for-each-ref", "--format=%(refname) %(objectname)", anchor]
        ).split()
        if existing:
            if (
                len(existing) != len((anchor, base))
                or existing[0] != anchor
                or not re.fullmatch(r"[a-f0-9]{40}", existing[1])
            ):
                raise ValueError("Local request retention identity is ambiguous")
            sha = existing[1]
            self.git(path, ["verify-commit", sha])
            if (
                self.git(path, ["show", "-s", "--format=%P", sha]).strip() != base
                or json.loads(self.git(path, ["show", sha + ":" + filename])) != payload
            ):
                raise ValueError("Retained request cannot adopt a different source or payload")
            return sha
        sha = self.commit(path, base, filename, payload, message)
        self.git(path, ["update-ref", anchor, sha, "0" * 40])
        return sha

    def publish_ref(self, path: Path, ref: str, sha: str) -> None:
        existing = self.git(path, ["ls-remote", "--heads", "origin", ref]).split()
        if existing:
            if existing != [sha, ref]:
                raise ValueError("Remote request branch is not owned by this exact commit")
            return
        # Empty expected ref means the destination must not exist, even if racing.
        self.git(path, ["push", "--force-with-lease=" + ref + ":", "origin", sha + ":" + ref])
        if self.git(path, ["ls-remote", "--heads", "origin", ref]).split() != [sha, ref]:
            raise ValueError("Published request identity is unverified")

    def one(self, request: dict[str, Any]) -> None:
        order, purpose, revision = request["order_id"], request["purpose"], request["revision"]
        identity(order)
        if (
            purpose not in {"provision", "retire"}
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
        ):
            raise ValueError("Invalid immutable publication coordinates")
        suffix = f"{order}/{purpose}-{revision}"
        private_sha, public_sha = request["private_sha"], request["public_sha"]
        if not private_sha and not public_sha:
            private_sha = self.signed_request(
                self.infra,
                self.infra_sha,
                f"single-tenant/orders/{suffix}.json",
                {
                    key: request["payload"][key]
                    for key in (
                        "order_id",
                        "owner",
                        "domain",
                        "payment",
                        "verification",
                        "claim_public_key",
                    )
                    if key in request["payload"]
                },
                f"Record Single Tenant {purpose} request {order}",
                "refs/single-tenant-outbox/" + suffix + "/private",
            )
            public_sha = self.signed_request(
                self.app,
                self.app_sha,
                ".single-tenant-request.json",
                {
                    "order_id": order,
                    "purpose": purpose,
                    "revision": revision,
                    "config_ref": private_sha,
                    "source_ref": self.app_sha,
                    "infra_ref": self.infra_sha,
                },
                f"Request Single Tenant {purpose} {order}",
                "refs/single-tenant-outbox/" + suffix + "/public",
            )
            # Both commits are durable before either push. A timeout resumes these
            # same identities; it never builds a second provisioning request.
            self.ledger.checkpoint(
                order, purpose, revision, private_sha=private_sha, public_sha=public_sha
            )
        if not private_sha or not public_sha:
            raise ValueError("Partial publication checkpoint cannot be replaced")
        self.publish_ref(self.infra, "refs/heads/single-tenant-config/" + suffix, private_sha)
        self.publish_ref(self.app, "refs/heads/single-tenant-request/" + suffix, public_sha)
        self.ledger.published(
            order, purpose, revision, private_sha=private_sha, public_sha=public_sha
        )

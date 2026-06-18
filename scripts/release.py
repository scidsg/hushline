#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "hushline" / "version.py"
DEFAULT_RELEASE_ALLOWED_SIGNERS = REPO_ROOT / ".github" / "release-allowed-signers"
DEFAULT_PROD_URL = "https://tips.hushline.app/"
SEMVER_PARTS = 3
VERSION_PATTERN = re.compile(r'__version__\s*=\s*"(?P<version>\d+\.\d+\.\d+)"')
LIVE_VERSION_PATTERN = re.compile(r">\s*v(?P<version>\d+\.\d+\.\d+)\s*<")
RELEASE_AUTH_NAMESPACE = "hushline-release"
RELEASE_AUTH_PRINCIPAL = "hushline-release"
MIN_ALLOWED_SIGNER_PARTS = 3
HARDWARE_SSH_KEY_TYPES = frozenset(
    {
        "sk-ecdsa-sha2-nistp256@openssh.com",
        "sk-ssh-ed25519@openssh.com",
    }
)


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ReleaseAuthConfig:
    signing_key: Path | None
    allowed_signers: Path
    principal: str = RELEASE_AUTH_PRINCIPAL
    namespace: str = RELEASE_AUTH_NAMESPACE


Runner = Callable[[Sequence[str], bool, str | None], CommandResult]
Fetcher = Callable[[str], str]


def run_command(
    args: Sequence[str],
    check: bool = True,
    stdin: str | None = None,
) -> CommandResult:
    result = subprocess.run(
        list(args),  # noqa: S603 - Release commands are fixed argv lists built by this helper.
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        input=stdin,
        text=True,
    )
    command_result = CommandResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    if check and result.returncode != 0:
        raise ReleaseError(
            f"Command failed: {' '.join(args)}\n{result.stderr or result.stdout}".rstrip()
        )
    return command_result


def fetch_url(url: str) -> str:
    with urlopen(url, timeout=15) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def read_local_version(version_file: Path | None = None) -> str:
    version_file = version_file or VERSION_FILE
    source = version_file.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if not match:
        raise ReleaseError(f"Could not find __version__ in {version_file}")
    return match.group("version")


def write_local_version(version: str, version_file: Path | None = None) -> None:
    version_file = version_file or VERSION_FILE
    source = version_file.read_text(encoding="utf-8")
    next_source, replacements = VERSION_PATTERN.subn(
        f'__version__ = "{version}"',
        source,
        count=1,
    )
    if replacements != 1:
        raise ReleaseError(f"Could not update __version__ in {version_file}")
    version_file.write_text(next_source, encoding="utf-8")


def extract_live_version(html: str) -> str:
    match = LIVE_VERSION_PATTERN.search(html)
    if not match:
        raise ReleaseError("Could not find live Hush Line version in production HTML")
    return match.group("version")


def next_patch_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != SEMVER_PARTS or not all(part.isdigit() for part in parts):
        raise ReleaseError(f"Invalid semantic version: {version}")
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def ensure_clean_worktree(runner: Runner) -> None:
    status = runner(["git", "status", "--porcelain"], True, None).stdout.strip()
    if status:
        raise ReleaseError("Working tree must be clean before running make release.")


def ensure_release_branch(runner: Runner, expected_branch: str) -> str:
    branch = runner(["git", "branch", "--show-current"], True, None).stdout.strip()
    if branch != expected_branch:
        raise ReleaseError(
            f"make release must run from {expected_branch!r}; current branch is {branch!r}."
        )
    return branch


def ensure_tag_and_release_available(runner: Runner, tag: str) -> None:
    local_tag = runner(["git", "rev-parse", "--verify", f"refs/tags/{tag}"], False, None)
    if local_tag.returncode == 0:
        raise ReleaseError(f"Local tag already exists: {tag}")

    remote_tag = runner(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", tag],
        False,
        None,
    )
    if remote_tag.returncode == 0:
        raise ReleaseError(f"Remote tag already exists: {tag}")
    if remote_tag.returncode not in {2}:
        raise ReleaseError((remote_tag.stderr or remote_tag.stdout).strip())

    existing_release = runner(["gh", "release", "view", tag], False, None)
    if existing_release.returncode == 0:
        raise ReleaseError(f"GitHub release already exists: {tag}")


def _release_path_from_env(name: str, default: Path | None = None) -> Path | None:
    value = os.environ.get(name)
    if value is None:
        return default
    if not value.strip():
        return None
    return Path(value).expanduser()


def _release_bool_from_env(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ReleaseError(f"{name} must be one of: 1, true, yes, on, 0, false, no, off.")


def _validate_release_allowed_signers(
    allowed_signers: Path,
    principal: str = RELEASE_AUTH_PRINCIPAL,
) -> None:
    if not allowed_signers.is_file():
        raise ReleaseError(
            "Release YubiKey allowlist is missing: "
            f"{allowed_signers}. Add the primary and backup YubiKey public keys first."
        )

    entries = [
        line.strip()
        for line in allowed_signers.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not entries:
        raise ReleaseError(
            "Release YubiKey allowlist does not contain any allowed YubiKey public keys."
        )

    for line in entries:
        parts = line.split()
        if len(parts) < MIN_ALLOWED_SIGNER_PARTS:
            raise ReleaseError("Release YubiKey allowlist contains a malformed signer entry.")
        principals, key_type = parts[0], parts[1]
        if principal not in principals.split(","):
            raise ReleaseError(f"Release YubiKey signer entry must use principal {principal!r}.")
        if key_type not in HARDWARE_SSH_KEY_TYPES:
            raise ReleaseError(
                "Release YubiKey allowlist must contain only OpenSSH security-key "
                "public keys, such as sk-ssh-ed25519@openssh.com."
            )


def ensure_release_yubikey_authorized(
    runner: Runner,
    *,
    tag: str,
    branch: str,
    local_version: str,
    config: ReleaseAuthConfig,
) -> None:
    if config.signing_key is None:
        raise ReleaseError(
            "RELEASE_SIGNING_KEY must point to the primary or backup YubiKey SSH identity."
        )
    if not config.signing_key.exists():
        raise ReleaseError(f"Release signing key does not exist: {config.signing_key}")

    _validate_release_allowed_signers(config.allowed_signers, config.principal)

    challenge = "\n".join(
        (
            "hushline-release-authorization-v1",
            f"tag={tag}",
            f"branch={branch}",
            f"local_version={local_version}",
            "",
        )
    )
    with tempfile.TemporaryDirectory(prefix="hushline-release-auth-") as temp_dir:
        challenge_path = Path(temp_dir) / "release-challenge.txt"
        challenge_path.write_text(challenge, encoding="utf-8")
        runner(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(config.signing_key),
                "-n",
                config.namespace,
                str(challenge_path),
            ],
            True,
            None,
        )
        signature_path = Path(f"{challenge_path}.sig")
        if not signature_path.is_file():
            raise ReleaseError("Release YubiKey signing did not create a signature.")
        runner(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(config.allowed_signers),
                "-I",
                config.principal,
                "-n",
                config.namespace,
                "-s",
                str(signature_path),
            ],
            True,
            challenge,
        )


def release_auth_config_from_env() -> ReleaseAuthConfig:
    signing_key = _release_path_from_env("HUSHLINE_RELEASE_SIGNING_KEY")
    allowed_signers = _release_path_from_env(
        "HUSHLINE_RELEASE_ALLOWED_SIGNERS",
        DEFAULT_RELEASE_ALLOWED_SIGNERS,
    )
    if allowed_signers is None:
        raise ReleaseError("HUSHLINE_RELEASE_ALLOWED_SIGNERS must not be empty.")
    return ReleaseAuthConfig(signing_key=signing_key, allowed_signers=allowed_signers)


def release(
    runner: Runner = run_command,
    fetcher: Fetcher = fetch_url,
    *,
    dry_run: bool | None = None,
) -> str:
    prod_url = os.environ.get("HUSHLINE_RELEASE_PROD_URL", DEFAULT_PROD_URL)
    release_branch = os.environ.get("HUSHLINE_RELEASE_BRANCH", "main")
    auth_config = release_auth_config_from_env()
    if dry_run is None:
        dry_run = _release_bool_from_env("HUSHLINE_RELEASE_DRY_RUN")

    ensure_clean_worktree(runner)
    branch = ensure_release_branch(runner, release_branch)

    local_version = read_local_version()
    live_version = extract_live_version(fetcher(prod_url))
    if live_version != local_version:
        raise ReleaseError(
            "Production version does not match local version: "
            f"production v{live_version}, local v{local_version}."
        )

    next_version = next_patch_version(local_version)
    tag = f"v{next_version}"
    ensure_tag_and_release_available(runner, tag)
    ensure_release_yubikey_authorized(
        runner,
        tag=tag,
        branch=branch,
        local_version=local_version,
        config=auth_config,
    )

    if dry_run:
        return tag

    write_local_version(next_version)
    runner(["git", "add", str(VERSION_FILE.relative_to(REPO_ROOT))], True, None)
    runner(["git", "commit", "-m", f"Update version to {tag}"], True, None)
    runner(["git", "tag", tag], True, None)
    runner(["git", "push", "origin", branch], True, None)
    runner(["git", "push", "origin", tag], True, None)
    runner(
        ["gh", "release", "create", tag, "--title", tag, "--generate-notes", "--latest"],
        True,
        None,
    )
    return tag


def main() -> int:
    try:
        dry_run = _release_bool_from_env("HUSHLINE_RELEASE_DRY_RUN")
        tag = release(dry_run=dry_run)
    except ReleaseError as error:
        print(f"release failed: {error}", file=sys.stderr)
        return 1

    if dry_run:
        print(
            f"Dry run passed for Hush Line release {tag}; "
            "no version, tag, push, or GitHub release was created."
        )
    else:
        print(f"Published Hush Line release {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_release_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "hushline_release_script",
        REPO_ROOT / "scripts" / "release.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_live_version_reads_footer_version() -> None:
    release_script = _load_release_module()

    assert (
        release_script.extract_live_version(
            '<footer><a href="https://github.com/scidsg/hushline">v0.7.4</a></footer>'
        )
        == "0.7.4"
    )


def test_next_patch_version_increments_patch_component() -> None:
    release_script = _load_release_module()

    assert release_script.next_patch_version("0.7.4") == "0.7.5"


def test_release_checks_live_version_bumps_commits_tags_pushes_and_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_script = _load_release_module()
    repo_root = tmp_path
    version_file = repo_root / "hushline" / "version.py"
    version_file.parent.mkdir()
    version_file.write_text('__version__ = "0.7.4"\n', encoding="utf-8")
    allowed_signers = repo_root / ".github" / "release-allowed-signers"
    allowed_signers.parent.mkdir()
    allowed_signers.write_text(
        "\n".join(
            (
                "hushline-release sk-ssh-ed25519@openssh.com AAAAC3NzaPrimary primary-yubikey",
                "hushline-release sk-ecdsa-sha2-nistp256@openssh.com "
                "AAAAC3NzaBackup backup-yubikey",
                "",
            )
        ),
        encoding="utf-8",
    )
    signing_key = repo_root / "primary-yubikey"
    signing_key.write_text("private key handle placeholder", encoding="utf-8")
    commands: list[tuple[str, ...]] = []
    verification_challenges: list[str] = []
    fetched_urls: list[str] = []

    monkeypatch.setattr(release_script, "REPO_ROOT", repo_root)
    monkeypatch.setattr(release_script, "VERSION_FILE", version_file)
    monkeypatch.setenv("HUSHLINE_RELEASE_PROD_URL", "https://tips.hushline.app/")
    monkeypatch.setenv("HUSHLINE_RELEASE_ALLOWED_SIGNERS", str(allowed_signers))
    monkeypatch.setenv("HUSHLINE_RELEASE_SIGNING_KEY", str(signing_key))

    def runner(args: Sequence[str], check: bool, stdin: str | None = None) -> object:
        command = tuple(args)
        commands.append(command)
        if command == ("git", "status", "--porcelain"):
            return release_script.CommandResult(0, "")
        if command == ("git", "branch", "--show-current"):
            return release_script.CommandResult(0, "main\n")
        if command == ("git", "rev-parse", "--verify", "refs/tags/v0.7.5"):
            return release_script.CommandResult(1, "", "not found")
        if command == ("git", "ls-remote", "--exit-code", "--tags", "origin", "v0.7.5"):
            return release_script.CommandResult(2, "", "")
        if command == ("gh", "release", "view", "v0.7.5"):
            return release_script.CommandResult(1, "", "not found")
        if command[:3] == ("ssh-keygen", "-Y", "sign"):
            challenge_path = Path(command[-1])
            Path(f"{challenge_path}.sig").write_text("fake signature", encoding="utf-8")
            return release_script.CommandResult(0, "")
        if command[:3] == ("ssh-keygen", "-Y", "verify"):
            assert stdin is not None
            verification_challenges.append(stdin)
            return release_script.CommandResult(0, "Good signature")
        return release_script.CommandResult(0, "")

    def fetcher(url: str) -> str:
        fetched_urls.append(url)
        return '<a href="https://github.com/scidsg/hushline">v0.7.4</a>'

    assert release_script.release(runner=runner, fetcher=fetcher) == "v0.7.5"
    assert version_file.read_text(encoding="utf-8") == '__version__ = "0.7.5"\n'
    assert fetched_urls == ["https://tips.hushline.app/"]
    assert verification_challenges == [
        "hushline-release-authorization-v1\n" "tag=v0.7.5\n" "branch=main\n" "local_version=0.7.4\n"
    ]
    assert commands[:5] == [
        ("git", "status", "--porcelain"),
        ("git", "branch", "--show-current"),
        ("git", "rev-parse", "--verify", "refs/tags/v0.7.5"),
        ("git", "ls-remote", "--exit-code", "--tags", "origin", "v0.7.5"),
        ("gh", "release", "view", "v0.7.5"),
    ]
    assert commands[5][:6] == (
        "ssh-keygen",
        "-Y",
        "sign",
        "-f",
        str(signing_key),
        "-n",
    )
    assert commands[5][6] == "hushline-release"
    assert commands[6][:-1] == (
        "ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(allowed_signers),
        "-I",
        "hushline-release",
        "-n",
        "hushline-release",
        "-s",
    )
    assert commands[7:] == [
        ("git", "add", "hushline/version.py"),
        ("git", "commit", "-m", "Update version to v0.7.5"),
        ("git", "tag", "v0.7.5"),
        ("git", "push", "origin", "main"),
        ("git", "push", "origin", "v0.7.5"),
        ("gh", "release", "create", "v0.7.5", "--title", "v0.7.5", "--generate-notes", "--latest"),
    ]


def test_release_dry_run_checks_authorization_without_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_script = _load_release_module()
    repo_root = tmp_path
    version_file = repo_root / "hushline" / "version.py"
    version_file.parent.mkdir()
    version_file.write_text('__version__ = "0.7.4"\n', encoding="utf-8")
    allowed_signers = repo_root / ".github" / "release-allowed-signers"
    allowed_signers.parent.mkdir()
    allowed_signers.write_text(
        "\n".join(
            (
                "hushline-release sk-ssh-ed25519@openssh.com AAAAC3NzaPrimary primary-yubikey",
                "hushline-release sk-ecdsa-sha2-nistp256@openssh.com "
                "AAAAC3NzaBackup backup-yubikey",
                "",
            )
        ),
        encoding="utf-8",
    )
    signing_key = repo_root / "primary-yubikey"
    signing_key.write_text("private key handle placeholder", encoding="utf-8")
    commands: list[tuple[str, ...]] = []
    verification_challenges: list[str] = []

    monkeypatch.setattr(release_script, "REPO_ROOT", repo_root)
    monkeypatch.setattr(release_script, "VERSION_FILE", version_file)
    monkeypatch.setenv("HUSHLINE_RELEASE_ALLOWED_SIGNERS", str(allowed_signers))
    monkeypatch.setenv("HUSHLINE_RELEASE_SIGNING_KEY", str(signing_key))

    def runner(args: Sequence[str], check: bool, stdin: str | None = None) -> object:
        command = tuple(args)
        commands.append(command)
        if command == ("git", "status", "--porcelain"):
            return release_script.CommandResult(0, "")
        if command == ("git", "branch", "--show-current"):
            return release_script.CommandResult(0, "main\n")
        if command == ("git", "rev-parse", "--verify", "refs/tags/v0.7.5"):
            return release_script.CommandResult(1, "", "not found")
        if command == ("git", "ls-remote", "--exit-code", "--tags", "origin", "v0.7.5"):
            return release_script.CommandResult(2, "", "")
        if command == ("gh", "release", "view", "v0.7.5"):
            return release_script.CommandResult(1, "", "not found")
        if command[:3] == ("ssh-keygen", "-Y", "sign"):
            challenge_path = Path(command[-1])
            Path(f"{challenge_path}.sig").write_text("fake signature", encoding="utf-8")
            return release_script.CommandResult(0, "")
        if command[:3] == ("ssh-keygen", "-Y", "verify"):
            assert stdin is not None
            verification_challenges.append(stdin)
            return release_script.CommandResult(0, "Good signature")
        raise AssertionError(f"unexpected dry-run command: {command}")

    assert (
        release_script.release(
            runner=runner,
            fetcher=lambda _url: '<a href="https://github.com/scidsg/hushline">v0.7.4</a>',
            dry_run=True,
        )
        == "v0.7.5"
    )
    assert version_file.read_text(encoding="utf-8") == '__version__ = "0.7.4"\n'
    assert verification_challenges == [
        "hushline-release-authorization-v1\n" "tag=v0.7.5\n" "branch=main\n" "local_version=0.7.4\n"
    ]
    assert len(commands) == 7
    assert commands[:5] == [
        ("git", "status", "--porcelain"),
        ("git", "branch", "--show-current"),
        ("git", "rev-parse", "--verify", "refs/tags/v0.7.5"),
        ("git", "ls-remote", "--exit-code", "--tags", "origin", "v0.7.5"),
        ("gh", "release", "view", "v0.7.5"),
    ]
    assert commands[5][:6] == (
        "ssh-keygen",
        "-Y",
        "sign",
        "-f",
        str(signing_key),
        "-n",
    )
    assert commands[6][:-1] == (
        "ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(allowed_signers),
        "-I",
        "hushline-release",
        "-n",
        "hushline-release",
        "-s",
    )


def test_release_blocks_when_live_version_does_not_match_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_script = _load_release_module()
    version_file = tmp_path / "hushline" / "version.py"
    version_file.parent.mkdir()
    version_file.write_text('__version__ = "0.7.4"\n', encoding="utf-8")

    monkeypatch.setattr(release_script, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release_script, "VERSION_FILE", version_file)

    def runner(args: Sequence[str], check: bool, stdin: str | None = None) -> object:
        assert stdin is None
        command = tuple(args)
        if command == ("git", "status", "--porcelain"):
            return release_script.CommandResult(0, "")
        if command == ("git", "branch", "--show-current"):
            return release_script.CommandResult(0, "main\n")
        raise AssertionError(f"unexpected command: {command}")

    with pytest.raises(
        release_script.ReleaseError,
        match="Production version does not match local version",
    ):
        release_script.release(
            runner=runner,
            fetcher=lambda _url: '<a href="https://github.com/scidsg/hushline">v0.7.3</a>',
        )

    assert version_file.read_text(encoding="utf-8") == '__version__ = "0.7.4"\n'


def test_release_yubikey_authorization_rejects_software_keys(tmp_path: Path) -> None:
    release_script = _load_release_module()
    allowed_signers = tmp_path / "release-allowed-signers"
    allowed_signers.write_text(
        "hushline-release ssh-ed25519 AAAAC3NzaSoftware software-key\n",
        encoding="utf-8",
    )
    signing_key = tmp_path / "release-yubikey"
    signing_key.write_text("private key handle placeholder", encoding="utf-8")

    def runner(args: Sequence[str], check: bool, stdin: str | None = None) -> object:
        raise AssertionError(f"unexpected command: {tuple(args)}")

    with pytest.raises(
        release_script.ReleaseError,
        match="must contain only OpenSSH security-key public keys",
    ):
        release_script.ensure_release_yubikey_authorized(
            runner,
            tag="v0.7.5",
            branch="main",
            local_version="0.7.4",
            config=release_script.ReleaseAuthConfig(
                signing_key=signing_key,
                allowed_signers=allowed_signers,
            ),
        )


def test_release_yubikey_authorization_requires_signing_key(tmp_path: Path) -> None:
    release_script = _load_release_module()
    allowed_signers = tmp_path / "release-allowed-signers"
    allowed_signers.write_text(
        "hushline-release sk-ssh-ed25519@openssh.com AAAAC3NzaPrimary primary-yubikey\n",
        encoding="utf-8",
    )

    def runner(args: Sequence[str], check: bool, stdin: str | None = None) -> object:
        raise AssertionError(f"unexpected command: {tuple(args)}")

    with pytest.raises(
        release_script.ReleaseError,
        match="RELEASE_SIGNING_KEY must point to the primary or backup YubiKey SSH identity",
    ):
        release_script.ensure_release_yubikey_authorized(
            runner,
            tag="v0.7.5",
            branch="main",
            local_version="0.7.4",
            config=release_script.ReleaseAuthConfig(
                signing_key=None,
                allowed_signers=allowed_signers,
            ),
        )

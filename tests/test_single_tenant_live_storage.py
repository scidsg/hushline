"""The cloud controller must never silently write its ledger to a root disk."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pytest_mock import MockFixture

from scripts import single_tenant_live_storage as storage
from scripts.single_tenant_live_ledger import Ledger


@pytest.fixture()
def linux_root(tmp_path: Path, mocker: MockFixture, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "controller"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("SINGLE_TENANT_CONTROL_STORAGE_PROFILE", "linux-controller-v1")
    mocker.patch.object(storage, "LINUX_ROOT", root)
    mocker.patch.object(storage.platform, "system", return_value="Linux")
    mocker.patch.object(Path, "is_mount", return_value=True)
    return root


def test_linux_layout_requires_explicit_profile(linux_root: Path) -> None:
    assert storage.storage_root() == linux_root
    storage.require_storage_path(linux_root / "ledger.sqlite")


def test_disconnected_volume_refuses_ledger_creation(linux_root: Path, mocker: MockFixture) -> None:
    path = linux_root / "ledger.sqlite"
    mocker.patch.object(Path, "is_mount", return_value=False)
    with pytest.raises(ValueError, match="no fallback"):
        Ledger.create(
            path, Fernet.generate_key(), storage_guard=lambda: storage.require_storage_path(path)
        )
    assert not path.exists()


def test_mount_loss_stops_existing_ledger_transactions(
    linux_root: Path, mocker: MockFixture
) -> None:
    path = linux_root / "ledger.sqlite"
    ledger = Ledger.create(
        path, Fernet.generate_key(), storage_guard=lambda: storage.require_storage_path(path)
    )
    before = path.read_bytes()
    mocker.patch.object(Path, "is_mount", return_value=False)
    with pytest.raises(ValueError, match="no fallback"):
        ledger.heartbeat(now=1000)
    assert path.read_bytes() == before


def test_linux_directory_must_be_private(linux_root: Path) -> None:
    linux_root.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        storage.storage_root()


def test_linux_directory_must_belong_to_service_user(linux_root: Path, mocker: MockFixture) -> None:
    mocker.patch.object(storage.os, "getuid", return_value=linux_root.stat().st_uid + 1)
    with pytest.raises(ValueError, match="owned"):
        storage.storage_root()


def test_linux_profile_refuses_other_platforms(linux_root: Path, mocker: MockFixture) -> None:
    mocker.patch.object(storage.platform, "system", return_value="Darwin")
    with pytest.raises(ValueError, match="profile"):
        storage.storage_root()


def test_unrecognized_profile_is_not_a_path_override(
    linux_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SINGLE_TENANT_CONTROL_STORAGE_PROFILE", str(linux_root))
    with pytest.raises(ValueError, match="profile"):
        storage.storage_root()


@pytest.mark.parametrize("relative", ["..", "../outside.sqlite", "."])
def test_paths_cannot_escape_or_use_volume_root(linux_root: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="within"):
        storage.require_storage_path(linux_root / relative)


def test_relative_paths_are_rejected(linux_root: Path) -> None:
    with pytest.raises(ValueError, match="within"):
        storage.require_storage_path(Path("ledger.sqlite"))


def test_symlink_escape_is_rejected(linux_root: Path) -> None:
    (linux_root / "escape").symlink_to(linux_root.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="within"):
        storage.require_storage_path(linux_root / "escape/ledger.sqlite")


def test_mount_path_cannot_be_a_symlink(linux_root: Path, mocker: MockFixture) -> None:
    alias = linux_root.parent / "alias"
    alias.symlink_to(linux_root, target_is_directory=True)
    mocker.patch.object(storage, "LINUX_ROOT", alias)
    with pytest.raises(ValueError, match="no fallback"):
        storage.storage_root()


def test_mac_remains_the_default_profile(
    tmp_path: Path, mocker: MockFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SINGLE_TENANT_CONTROL_STORAGE_PROFILE", raising=False)
    mocker.patch.object(storage, "MAC_VOLUME", tmp_path)
    mocker.patch.object(storage, "MAC_ROOT", tmp_path)
    mounted = mocker.patch.object(Path, "is_mount", return_value=True)
    assert storage.storage_root() == tmp_path
    mounted.return_value = False
    with pytest.raises(ValueError, match="no fallback"):
        storage.storage_root()


def test_worker_installs_storage_guard_on_its_ledger(linux_root: Path, mocker: MockFixture) -> None:
    from scripts.single_tenant_live_worker import ledger as open_worker_ledger

    key = Fernet.generate_key()
    path = linux_root / "worker.sqlite"
    Ledger.create(path, key)
    key_path = linux_root.parent / "private-key"
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    store = open_worker_ledger({"ledger_path": str(path), "ledger_key_path": str(key_path)})
    mocker.patch.object(Path, "is_mount", return_value=False)
    with pytest.raises(ValueError, match="no fallback"):
        store.heartbeat(now=1000)


def test_publisher_accepts_only_owned_linux_repository_layout(
    linux_root: Path, mocker: MockFixture
) -> None:
    from scripts.single_tenant_live_publish import PRIVATE_REMOTE, PUBLIC_REMOTE, Publisher

    app, infra, artifacts = (linux_root / name for name in ("app", "infra", "artifacts"))
    for directory in (app, infra, artifacts):
        directory.mkdir(mode=0o700)
    home = linux_root.parent / "service-home"
    (home / ".ssh").mkdir(parents=True, mode=0o700)
    signing_key = home / ".ssh/signing"
    signing_key.write_text("test-only-placeholder")
    signing_key.chmod(0o600)
    mocker.patch.object(Path, "home", return_value=home)

    def trusted_git(path: Path, args: list[str]) -> str:
        if args[:2] == ["remote", "get-url"]:
            return PUBLIC_REMOTE if path == app else PRIVATE_REMOTE
        if args[0] == "rev-parse":
            return "a" * 40
        assert args == ["verify-commit", "a" * 40]
        return ""

    git = mocker.patch.object(Publisher, "git", side_effect=trusted_git)
    store = Ledger.create(linux_root / "publisher.sqlite", Fernet.generate_key())
    Publisher(
        ledger=store,
        app=app,
        infra=infra,
        app_sha="a" * 40,
        infra_sha="a" * 40,
        artifacts=artifacts,
        signing_key=signing_key,
    )
    assert sum(call.args[1][0] == "verify-commit" for call in git.call_args_list) == 2
    outside = linux_root.parent / "outside-repository"
    git.reset_mock()
    with pytest.raises(ValueError, match="within"):
        Publisher(
            ledger=store,
            app=outside,
            infra=infra,
            app_sha="a" * 40,
            infra_sha="a" * 40,
            artifacts=artifacts,
            signing_key=signing_key,
        )
    git.assert_not_called()

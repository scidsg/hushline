"""Explicit approved controller storage layouts, with no local-disk fallback."""

from __future__ import annotations

import os
import platform
from pathlib import Path

MAC_VOLUME = Path("/Volumes/Storage B")
MAC_ROOT = MAC_VOLUME / "hushline-dev/projects"
LINUX_ROOT = Path("/srv/hushline/controller")


def storage_root() -> Path:
    profile = os.environ.get("SINGLE_TENANT_CONTROL_STORAGE_PROFILE", "mac-external-v1")
    if profile == "mac-external-v1":
        mount, root = MAC_VOLUME, MAC_ROOT
    elif profile == "linux-controller-v1" and platform.system() == "Linux":
        mount = root = LINUX_ROOT
    else:
        raise ValueError("An approved controller storage profile is required")
    if (
        mount.is_symlink()
        or root.is_symlink()
        or not mount.is_mount()
        or not root.is_dir()
        or mount.resolve() != mount
        or root.resolve() != root
    ):
        raise ValueError("Approved controller storage is unavailable; no fallback permitted")
    if profile == "linux-controller-v1" and (
        root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077
    ):
        raise ValueError("Linux controller storage must be private and owned by the service user")
    return root


def require_storage_path(path: Path) -> None:
    root = storage_root()
    resolved = path.resolve()
    if not path.is_absolute() or resolved == root or not resolved.is_relative_to(root):
        raise ValueError("Controller data must remain within its approved mounted storage")

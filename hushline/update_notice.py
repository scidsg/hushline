"""Nonblocking, server-only checks for newer stable Hush Line releases."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from flask import Flask, request

from hushline.version import __version__

RELEASE_API = "https://api.github.com/repos/scidsg/hushline/releases/latest"
RELEASE_PAGE = "https://github.com/scidsg/hushline/releases/latest"
CHECK_INTERVAL = 24 * 60 * 60
RETRY_INTERVAL = 60 * 60
MAX_RESPONSE_BYTES = 64 * 1024
_VERSION = re.compile(r"v?(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})")


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    return int(match[1]), int(match[2]), int(match[3])


def fetch_latest_release() -> str | None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: Any, **kwargs: Any) -> None:
            return None

    query = urllib.request.Request(  # noqa: S310 — fixed HTTPS official release endpoint
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "HushLine-update-check"},
    )
    with urllib.request.build_opener(NoRedirect()).open(query, timeout=2) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        return None
    release = json.loads(raw)
    if not isinstance(release, dict):
        return None
    if release.get("draft") is not False or release.get("prerelease") is not False:
        return None
    tag = release.get("tag_name")
    if not isinstance(tag, str) or version_tuple(tag) is None:
        return None
    return tag.removeprefix("v")


class ReleaseCheck:
    def __init__(
        self,
        fetch: Callable[[], str | None] = fetch_latest_release,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._latest: str | None = None
        self._next_check = 0.0
        self._running = False

    def newer_than(self, installed: str) -> str | None:
        current = version_tuple(installed)
        if current is None:
            return None
        with self._lock:
            if not self._running and self._clock() >= self._next_check:
                self._running = True
                try:
                    threading.Thread(target=self._refresh, daemon=True).start()
                except (RuntimeError, OSError):
                    self._running = False
                    self._next_check = self._clock() + RETRY_INTERVAL
            latest = self._latest
        parsed = version_tuple(latest) if latest is not None else None
        return latest if parsed is not None and parsed > current else None

    def _refresh(self) -> None:
        latest = None
        try:
            latest = self._fetch()
            if latest is not None and version_tuple(latest) is None:
                latest = None
        except (OSError, ValueError):
            pass  # Network failures never affect page rendering or log request data.
        finally:
            with self._lock:
                if latest is not None:
                    self._latest = latest
                self._next_check = self._clock() + (
                    CHECK_INTERVAL if latest is not None else RETRY_INTERVAL
                )
                self._running = False


def init_app(app: Flask) -> None:
    check = ReleaseCheck()
    app.extensions["hushline_release_check"] = check

    @app.context_processor
    def update_notice() -> dict[str, str | None]:
        onion = bool(app.config.get("ONION_HOSTNAME")) or str(
            app.config.get("SERVER_NAME") or ""
        ).split(":", 1)[0].lower().endswith(".onion")
        onion = onion or request.host.split(":", 1)[0].lower().endswith(".onion")
        enabled = app.config.get("UPDATE_CHECK_ENABLED", not onion)
        latest = check.newer_than(__version__) if enabled and not app.testing else None
        return {"hushline_update_version": latest, "hushline_release_page": RELEASE_PAGE}

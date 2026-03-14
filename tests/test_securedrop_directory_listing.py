from __future__ import annotations

from pathlib import Path

import pytest

from hushline.model import securedrop_directory_listing as securedrop_listing_module


def test_get_securedrop_directory_listings_returns_empty_tuple_for_missing_seed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path = tmp_path / "missing-securedrop-seed.json"

    securedrop_listing_module.get_securedrop_directory_listings.cache_clear()
    monkeypatch.setattr(securedrop_listing_module, "_seed_path", lambda: missing_path)

    try:
        assert securedrop_listing_module.get_securedrop_directory_listings() == ()
    finally:
        securedrop_listing_module.get_securedrop_directory_listings.cache_clear()


def test_get_securedrop_directory_listings_returns_empty_tuple_for_non_list_seed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_path = tmp_path / "securedrop-seed.json"
    seed_path.write_text('{"id": "not-a-list"}', encoding="utf-8")

    securedrop_listing_module.get_securedrop_directory_listings.cache_clear()
    monkeypatch.setattr(securedrop_listing_module, "_seed_path", lambda: seed_path)

    try:
        assert securedrop_listing_module.get_securedrop_directory_listings() == ()
    finally:
        securedrop_listing_module.get_securedrop_directory_listings.cache_clear()

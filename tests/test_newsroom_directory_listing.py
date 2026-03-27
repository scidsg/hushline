from __future__ import annotations

import json
from pathlib import Path

import pytest

import hushline.model.newsroom_directory_listing as newsroom_listing_module
from hushline.model.newsroom_directory_listing import (
    _build_listing,
    _seed_path,
    get_newsroom_directory_listing,
    get_newsroom_directory_listings,
)


def test_newsroom_directory_listings_returns_empty_tuple_when_seed_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-newsroom-seed.json"
    get_newsroom_directory_listings.cache_clear()
    monkeypatch.setattr(newsroom_listing_module, "_seed_path", lambda: missing_path)

    assert get_newsroom_directory_listings() == ()


def test_newsroom_directory_listings_returns_empty_tuple_for_non_list_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "newsroom-seed.json"
    seed_path.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")
    get_newsroom_directory_listings.cache_clear()
    monkeypatch.setattr(newsroom_listing_module, "_seed_path", lambda: seed_path)

    assert get_newsroom_directory_listings() == ()


def test_get_newsroom_directory_listing_matches_slug_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "newsroom-seed.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "id": "newsroom-sample",
                    "slug": "newsroom~sample-newsroom",
                    "name": "Sample Newsroom",
                    "website": "https://example.org",
                    "description": "Sample",
                    "directory_url": "https://findyournews.org/organization/sample-newsroom/",
                    "tagline": "Sample tagline",
                    "mission": "Sample mission",
                    "about": "Sample about",
                    "countries": ["United States"],
                    "places_covered": ["Chicago"],
                    "languages": ["English"],
                    "topics": ["Accountability"],
                    "reach": "Local",
                    "year_founded": "2020",
                    "source_label": "INN Find Your News directory",
                    "source_url": "https://findyournews.org/organization/sample-newsroom/",
                }
            ]
        ),
        encoding="utf-8",
    )
    get_newsroom_directory_listings.cache_clear()
    monkeypatch.setattr(newsroom_listing_module, "_seed_path", lambda: seed_path)

    listing = get_newsroom_directory_listing("NEWSROOM~SAMPLE-NEWSROOM")

    assert listing is not None
    assert listing.id == "newsroom-sample"


def test_build_newsroom_listing_exposes_geography_properties() -> None:
    listing = _build_listing(
        {
            "id": "newsroom-sample",
            "slug": "newsroom~sample-newsroom",
            "name": "Sample Newsroom",
            "website": "https://example.org",
            "description": "Sample description",
            "directory_url": "https://findyournews.org/organization/sample-newsroom/",
            "tagline": "Investigative nonprofit newsroom",
            "mission": "Mission text",
            "about": "About text",
            "city": "Chicago",
            "country": "United States",
            "subdivision": "IL",
            "countries": ["United States"],
            "places_covered": ["Illinois"],
            "languages": ["English"],
            "topics": ["Corruption"],
            "reach": "Regional",
            "year_founded": "2018",
            "source_label": "INN Find Your News directory",
            "source_url": "https://findyournews.org/organization/sample-newsroom/",
        }
    )

    assert listing.geography.country == "United States"
    assert listing.geography.subdivision == "Illinois"
    assert listing.location == "Chicago, Illinois, United States"
    assert listing.topics == ("Corruption",)


def test_newsroom_seed_path_points_to_committed_dataset() -> None:
    assert _seed_path().name == "newsroom_directory_listings.json"

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hushline.model.globaleaks_directory_listing as globaleaks_listing_module
from hushline.model.globaleaks_directory_listing import (
    GlobaLeaksDirectoryListing,
    _build_listing,
    _seed_path,
    get_globaleaks_directory_listing,
    get_globaleaks_directory_listings,
)


def test_globaleaks_directory_listings_returns_empty_tuple_when_seed_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-globaleaks-seed.json"
    get_globaleaks_directory_listings.cache_clear()
    monkeypatch.setattr(globaleaks_listing_module, "_seed_path", lambda: missing_path)

    assert get_globaleaks_directory_listings() == ()


def test_globaleaks_directory_listings_returns_empty_tuple_for_non_list_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "globaleaks-seed.json"
    seed_path.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")
    get_globaleaks_directory_listings.cache_clear()
    monkeypatch.setattr(globaleaks_listing_module, "_seed_path", lambda: seed_path)

    assert get_globaleaks_directory_listings() == ()


def test_get_globaleaks_directory_listing_matches_slug_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "globaleaks-seed.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "id": "globaleaks-sample",
                    "slug": "globaleaks~sample-newsroom",
                    "name": "Sample Newsroom",
                    "website": "https://example.org",
                    "description": "Sample",
                    "submission_url": "https://submit.example.org",
                    "host": "submit.example.org",
                    "countries": ["Italy"],
                    "languages": ["English"],
                    "source_label": "Automated GlobaLeaks discovery dataset",
                    "source_url": "https://example.org/source",
                }
            ]
        ),
        encoding="utf-8",
    )
    get_globaleaks_directory_listings.cache_clear()
    monkeypatch.setattr(globaleaks_listing_module, "_seed_path", lambda: seed_path)

    listing = get_globaleaks_directory_listing("GLOBALEAKS~SAMPLE-NEWSROOM")

    assert listing is not None
    assert listing.id == "globaleaks-sample"


def test_build_globaleaks_listing_infers_host_from_submission_url() -> None:
    listing = _build_listing(
        {
            "id": "globaleaks-sample",
            "slug": "globaleaks~sample-newsroom",
            "name": "Sample Newsroom",
            "website": "https://example.org",
            "description": "Sample",
            "submission_url": "https://submit.example.org/report",
            "countries": ["Italy"],
            "languages": ["English"],
            "source_label": "Automated GlobaLeaks discovery dataset",
            "source_url": "https://example.org/source",
        }
    )

    assert listing.host == "submit.example.org"


def test_globaleaks_directory_listing_properties_expose_geography_and_onion_detection() -> None:
    listing = GlobaLeaksDirectoryListing(
        id="globaleaks-sample",
        slug="globaleaks~sample-newsroom",
        name="Sample Newsroom",
        website="https://example.org",
        description="Sample",
        submission_url="http://sampleonion1234567890abcdef.onion",
        host="sampleonion1234567890abcdef.onion",
        countries=("Italy",),
        languages=("English",),
        source_label="Automated GlobaLeaks discovery dataset",
        source_url="https://example.org/source",
        city="Rome",
        country="Italy",
    )

    assert listing.geography.country == "Italy"
    assert listing.location == "Rome, Italy"
    assert listing.has_onion_submission is True


def test_globaleaks_seed_path_points_to_committed_dataset() -> None:
    assert _seed_path().name == "globaleaks_instances.json"

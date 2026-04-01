from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from unidecode import unidecode

from hushline.model.directory_listing_geography import (
    DirectoryListingGeography,
    build_directory_geography,
)


@dataclass(frozen=True)
class NewsroomDirectoryListing:
    id: str
    slug: str
    name: str
    website: str
    description: str
    directory_url: str
    tagline: str
    mission: str
    about: str
    countries: tuple[str, ...]
    places_covered: tuple[str, ...]
    languages: tuple[str, ...]
    topics: tuple[str, ...]
    reach: str
    year_founded: str
    source_label: str
    source_url: str
    city: str | None = None
    country: str | None = None
    subdivision: str | None = None
    listing_type: str = "newsroom_directory_listing"
    directory_section: str = "newsroom_directory"
    message_capable: bool = False
    is_automated: bool = True

    @property
    def geography(self) -> DirectoryListingGeography:
        return build_directory_geography(
            countries=self.countries,
            city=self.city,
            country=self.country,
            subdivision=self.subdivision,
        )

    @property
    def location(self) -> str:
        return self.geography.location


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "newsroom_directory_listings.json"


@lru_cache(maxsize=1)
def get_newsroom_directory_listings() -> tuple[NewsroomDirectoryListing, ...]:
    path = _seed_path()
    if not path.exists():
        return ()

    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return ()

    listings = tuple(_build_listing(row) for row in rows if isinstance(row, dict))
    return tuple(sorted(listings, key=lambda listing: (_sort_key(listing.name), listing.id)))


def get_newsroom_directory_listing(slug: str) -> NewsroomDirectoryListing | None:
    slug_casefold = slug.casefold()
    return next(
        (
            listing
            for listing in get_newsroom_directory_listings()
            if listing.slug.casefold() == slug_casefold
        ),
        None,
    )


def _build_listing(row: dict[str, Any]) -> NewsroomDirectoryListing:
    geography = build_directory_geography(
        countries=row.get("countries", []),
        city=row.get("city"),
        country=row.get("country"),
        subdivision=row.get("subdivision"),
    )
    return NewsroomDirectoryListing(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        website=row["website"],
        description=row["description"],
        directory_url=row["directory_url"],
        tagline=row.get("tagline", ""),
        mission=row.get("mission", ""),
        about=row.get("about", ""),
        countries=geography.countries,
        places_covered=tuple(row.get("places_covered", [])),
        languages=tuple(row.get("languages", [])),
        topics=tuple(row.get("topics", [])),
        reach=row.get("reach", ""),
        year_founded=row.get("year_founded", ""),
        source_label=row["source_label"],
        source_url=row["source_url"],
        city=geography.city,
        country=geography.country,
        subdivision=geography.subdivision,
    )

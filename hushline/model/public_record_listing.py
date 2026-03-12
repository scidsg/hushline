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
    build_public_record_geography,
)


@dataclass(frozen=True)
class PublicRecordListing:
    id: str
    slug: str
    name: str
    website: str
    description: str
    city: str
    state: str
    practice_tags: tuple[str, ...]
    source_label: str
    source_url: str | None = None
    country: str | None = None
    subdivision: str | None = None
    listing_type: str = "attorney"
    directory_section: str = "public_record"
    message_capable: bool = False
    is_automated: bool = True

    @property
    def geography(self) -> DirectoryListingGeography:
        return build_public_record_geography(
            city=self.city,
            state=self.state,
            country=self.country,
            subdivision=self.subdivision,
        )

    @property
    def countries(self) -> tuple[str, ...]:
        return self.geography.countries

    @property
    def location(self) -> str:
        return self.geography.location


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "public_record_law_firms.json"


def _legacy_seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "public_record_law_firms_legacy.json"


def _load_seed_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_public_record_listings() -> tuple[PublicRecordListing, ...]:
    strict_rows = _load_seed_rows(_seed_path())
    legacy_rows = _load_seed_rows(_legacy_seed_path())

    merged_listings = [
        *(_build_listing(row, directory_section="public_record") for row in strict_rows),
        *(_build_listing(row, directory_section="legacy_public_record") for row in legacy_rows),
    ]

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    deduplicated_listings: list[PublicRecordListing] = []
    for listing in merged_listings:
        if listing.id in seen_ids or listing.slug in seen_slugs:
            continue
        seen_ids.add(listing.id)
        seen_slugs.add(listing.slug)
        deduplicated_listings.append(listing)

    return tuple(
        sorted(
            deduplicated_listings,
            key=lambda listing: (_sort_key(listing.name), listing.id),
        )
    )


def get_public_record_listing(slug: str) -> PublicRecordListing | None:
    slug_casefold = slug.casefold()
    return next(
        (
            listing
            for listing in get_public_record_listings()
            if listing.slug.casefold() == slug_casefold
        ),
        None,
    )


def _build_listing(
    row: dict[str, Any], *, directory_section: str = "public_record"
) -> PublicRecordListing:
    geography = build_public_record_geography(
        city=row.get("city"),
        state=row.get("state"),
        country=row.get("country"),
        subdivision=row.get("subdivision"),
    )
    return PublicRecordListing(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        website=row["website"],
        description=row["description"],
        city=row["city"],
        state=row["state"],
        practice_tags=tuple(row["practice_tags"]),
        source_label=row["source_label"],
        source_url=row.get("source_url"),
        country=geography.country,
        subdivision=geography.subdivision,
        directory_section=directory_section,
    )

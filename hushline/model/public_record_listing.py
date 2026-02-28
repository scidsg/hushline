from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from unidecode import unidecode


@dataclass(frozen=True)
class PublicRecordListing:
    id: str
    slug: str
    name: str
    website: str
    city: str
    state: str
    practice_tags: tuple[str, ...]
    source_label: str
    source_url: str | None = None
    listing_type: str = "law_firm"
    directory_section: str = "public_record"
    message_capable: bool = False
    is_automated: bool = True

    @property
    def location(self) -> str:
        return f"{self.city}, {self.state}"


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "public_record_law_firms.json"


@lru_cache(maxsize=1)
def get_public_record_listings() -> tuple[PublicRecordListing, ...]:
    rows = json.loads(_seed_path().read_text(encoding="utf-8"))
    listings = tuple(_build_listing(row) for row in rows)
    return tuple(sorted(listings, key=lambda listing: (_sort_key(listing.name), listing.id)))


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


def _build_listing(row: dict[str, Any]) -> PublicRecordListing:
    return PublicRecordListing(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        website=row["website"],
        city=row["city"],
        state=row["state"],
        practice_tags=tuple(row["practice_tags"]),
        source_label=row["source_label"],
        source_url=row.get("source_url"),
    )

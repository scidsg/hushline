from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from unidecode import unidecode


@dataclass(frozen=True)
class GlobaLeaksDirectoryListing:
    id: str
    slug: str
    name: str
    website: str
    description: str
    submission_url: str
    host: str
    countries: tuple[str, ...]
    languages: tuple[str, ...]
    source_label: str
    source_url: str
    listing_type: str = "globaleaks_instance"
    directory_section: str = "globaleaks_directory"
    message_capable: bool = False
    is_automated: bool = True

    @property
    def location(self) -> str:
        if not self.countries:
            return "Unknown"
        return ", ".join(self.countries)

    @property
    def has_onion_submission(self) -> bool:
        values = (self.submission_url, self.website, self.host)
        return any(".onion" in value.casefold() for value in values if value)


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "globaleaks_instances.json"


@lru_cache(maxsize=1)
def get_globaleaks_directory_listings() -> tuple[GlobaLeaksDirectoryListing, ...]:
    path = _seed_path()
    if not path.exists():
        return ()

    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return ()

    listings = tuple(_build_listing(row) for row in rows if isinstance(row, dict))
    return tuple(sorted(listings, key=lambda listing: (_sort_key(listing.name), listing.id)))


def get_globaleaks_directory_listing(slug: str) -> GlobaLeaksDirectoryListing | None:
    slug_casefold = slug.casefold()
    return next(
        (
            listing
            for listing in get_globaleaks_directory_listings()
            if listing.slug.casefold() == slug_casefold
        ),
        None,
    )


def _build_listing(row: dict[str, Any]) -> GlobaLeaksDirectoryListing:
    submission_url = row["submission_url"]
    host = row.get("host", "")
    if not host:
        host = urlparse(submission_url).hostname or ""

    return GlobaLeaksDirectoryListing(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        website=row["website"],
        description=row["description"],
        submission_url=submission_url,
        host=host,
        countries=tuple(row.get("countries", [])),
        languages=tuple(row.get("languages", [])),
        source_label=row["source_label"],
        source_url=row["source_url"],
    )

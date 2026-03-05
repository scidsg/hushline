from __future__ import annotations

import re
import unicodedata
from typing import Mapping, Sequence
from urllib.parse import parse_qsl, urlparse

from unidecode import unidecode

from hushline.public_record_refresh import (
    CHAMBERS_SOURCE_LABEL,
    LEGACY_SELF_REPORTED_SOURCE_LABEL,
    US_STATE_AUTHORITATIVE_SOURCES,
    PublicRecordRow,
)

_DISALLOWED_SOURCE_DOMAINS = frozenset(
    {
        "chambers.com",
        "profiles-portal.chambers.com",
        "chamberssitemap.blob.core.windows.net",
        "ranking-tables.chambers.com",
    }
)
_OHIO_ATTORNEY_PROFILE_FRAGMENT_RE = re.compile(r"^/?\d+/attyinfo/?$", re.IGNORECASE)


def assert_official_source_adapter_rows(state_code: str, rows: Sequence[PublicRecordRow]) -> None:
    source_rule = US_STATE_AUTHORITATIVE_SOURCES[state_code]
    expected_label = source_rule["source_label"]

    assert rows, f"Expected official-source adapter to return rows for state {state_code}"

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    seen_names: set[str] = set()

    for row in rows:
        listing_id = _require_string(row, "id")
        slug = _require_string(row, "slug")
        name = _require_string(row, "name")
        website = _require_string(row, "website")
        source_label = _require_string(row, "source_label")
        source_url = _require_string(row, "source_url")

        assert row["state"] == state_code
        assert source_label == expected_label
        assert source_label not in {
            CHAMBERS_SOURCE_LABEL,
            LEGACY_SELF_REPORTED_SOURCE_LABEL,
        }

        source_host = urlparse(source_url).hostname
        assert source_host is not None
        normalized_source_host = source_host.casefold()

        assert _host_matches_any_domain(
            normalized_source_host,
            source_rule["allowed_domains"],
        )
        assert not _host_matches_any_domain(
            normalized_source_host,
            _DISALLOWED_SOURCE_DOMAINS,
        )
        assert not _has_listing_marker(source_url)
        assert _normalize_url_for_comparison(source_url) != _normalize_url_for_comparison(website)

        normalized_source_no_fragment = _normalize_url_for_comparison(
            urlparse(source_url)._replace(fragment="").geturl()
        )
        normalized_state_source_no_fragment = _normalize_url_for_comparison(
            urlparse(source_rule["source_url"])._replace(fragment="").geturl()
        )

        if not (
            state_code == "OH"
            and _OHIO_ATTORNEY_PROFILE_FRAGMENT_RE.fullmatch(
                (urlparse(source_url).fragment or "").strip()
            )
        ):
            assert normalized_source_no_fragment != normalized_state_source_no_fragment

        assert listing_id not in seen_ids
        seen_ids.add(listing_id)

        assert slug not in seen_slugs
        seen_slugs.add(slug)

        normalized_name = _normalized_name_key(name)
        assert normalized_name not in seen_names
        seen_names.add(normalized_name)


def build_existing_row_for_collision(
    discovered_row: Mapping[str, object],
    *,
    collision: str,
) -> dict[str, str]:
    listing_id = _require_string(discovered_row, "id")
    slug = _require_string(discovered_row, "slug")
    name = _require_string(discovered_row, "name")

    if collision == "id":
        return {
            "id": listing_id,
            "slug": "public-record~existing-collision-id",
            "name": "Existing Collision Id",
        }

    if collision == "slug":
        return {
            "id": "seed-existing-collision-slug",
            "slug": slug,
            "name": "Existing Collision Slug",
        }

    if collision == "name":
        return {
            "id": "seed-existing-collision-name",
            "slug": "public-record~existing-collision-name",
            "name": f"  {name.upper()}  ",
        }

    raise AssertionError(f"Unknown collision type: {collision}")


def _has_listing_marker(source_url: str) -> bool:
    parsed = urlparse(source_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key.casefold() == "listing" for key, _value in query_pairs):
        return True

    fragment = (parsed.fragment or "").strip()
    if not fragment:
        return False

    fragment_fields = [field.strip() for field in fragment.split("&") if field.strip()]
    for field in fragment_fields:
        key = field.split("=", 1)[0].strip().casefold()
        if key == "listing":
            return True

    return False


def _require_string(row: Mapping[str, object], field_name: str) -> str:
    value = row.get(field_name)
    assert isinstance(value, str)
    normalized = unicodedata.normalize("NFKC", value).strip()
    assert normalized
    return normalized


def _normalize_url_for_comparison(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold().rstrip("/")


def _host_matches_any_domain(host: str, domains: frozenset[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _normalized_name_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip()
    return unidecode(normalized).casefold()

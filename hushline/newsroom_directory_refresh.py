from __future__ import annotations

import re
import time
import unicodedata
from html import unescape
from typing import Mapping, Protocol, Sequence, cast
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from unidecode import unidecode

NEWSROOM_DIRECTORY_SOURCE_LABEL = "INN Find Your News directory"
NEWSROOM_DIRECTORY_SOURCE_URL = "https://findyournews.org/explore/"

_NEWSROOM_USER_AGENT = (
    "Mozilla/5.0 (compatible; HushlineNewsroomSync/1.0; +https://github.com/scidsg/hushline)"
)
_FIND_YOUR_NEWS_HOSTS = frozenset({"findyournews.org", "www.findyournews.org"})
_USA = "United States"
_LOCATION_CITY_COUNTRY_PARTS = 2
_LOCATION_CITY_STATE_COUNTRY_PARTS = 3
_USA_ALIASES = frozenset(
    {
        "us",
        "u.s.",
        "usa",
        "u.s.a.",
        "united states",
        "united states of america",
    }
)
_US_SUBDIVISION_NAMES = {
    "AK": "Alaska",
    "AL": "Alabama",
    "AR": "Arkansas",
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DC": "District of Columbia",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "IA": "Iowa",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "MA": "Massachusetts",
    "MD": "Maryland",
    "ME": "Maine",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MO": "Missouri",
    "MS": "Mississippi",
    "MT": "Montana",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "NE": "Nebraska",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NV": "Nevada",
    "NY": "New York",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VA": "Virginia",
    "VT": "Vermont",
    "WA": "Washington",
    "WI": "Wisconsin",
    "WV": "West Virginia",
    "WY": "Wyoming",
}
_US_SUBDIVISION_NAMES_BY_CASEFOLD = {
    subdivision.casefold(): subdivision for subdivision in _US_SUBDIVISION_NAMES.values()
}


class NewsroomDirectoryRefreshError(Exception):
    pass


class _ResponseLike(Protocol):
    text: str

    def raise_for_status(self) -> None: ...


class _SessionLike(Protocol):
    def get(
        self,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str],
    ) -> _ResponseLike: ...


def _should_retry_request_error(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True

    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}

    return False


def _get_with_retries(
    client: _SessionLike,
    *,
    url: str,
    timeout_seconds: float,
    max_attempts: int = 3,
) -> _ResponseLike:
    last_error: requests.RequestException | None = None
    for attempt in range(max_attempts):
        try:
            response = client.get(
                url,
                timeout=timeout_seconds,
                headers={"User-Agent": _NEWSROOM_USER_AGENT},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts - 1 or not _should_retry_request_error(exc):
                raise
            time.sleep(min(0.5 * (attempt + 1), 1.0))

    if last_error is not None:
        raise last_error
    raise NewsroomDirectoryRefreshError(f"Failed to fetch newsroom source URL: {url}")


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _slugify(value: str) -> str:
    normalized = _sort_key(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""

    return re.sub(r"\s+", " ", value).strip()


def _normalize_http_url(
    value: object,
    *,
    field: str,
    required: bool,
) -> str:
    if not isinstance(value, str):
        if required:
            raise NewsroomDirectoryRefreshError(f"Missing required URL field: {field}")
        return ""

    cleaned = value.strip()
    if not cleaned:
        if required:
            raise NewsroomDirectoryRefreshError(f"Missing required URL field: {field}")
        return ""

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        if required:
            raise NewsroomDirectoryRefreshError(
                f"Invalid URL for field {field}: expected absolute http/https URL"
            )
        return ""

    return cleaned


def _normalize_string_list(value: object) -> list[str]:
    raw_values: list[str]
    if isinstance(value, list):
        raw_values = [item for item in value if isinstance(item, str)]
    elif isinstance(value, str):
        separators = value.replace("|", ",").replace(";", ",")
        raw_values = [item.strip() for item in separators.split(",")]
    else:
        return []

    normalized_values: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        cleaned = _normalize_text(raw_value)
        if not cleaned:
            continue
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_values.append(cleaned)
    return normalized_values


def _normalize_country(value: str | None) -> str | None:
    cleaned = _normalize_text(value)
    if not cleaned:
        return None
    if cleaned.casefold() in _USA_ALIASES:
        return _USA
    return cleaned


def _normalize_us_subdivision(value: str | None) -> str | None:
    cleaned = _normalize_text(value)
    if not cleaned:
        return None

    subdivision_code = cleaned.upper()
    if subdivision_code in _US_SUBDIVISION_NAMES:
        return _US_SUBDIVISION_NAMES[subdivision_code]

    return _US_SUBDIVISION_NAMES_BY_CASEFOLD.get(cleaned.casefold(), cleaned)


def _listing_path_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    return path.split("/")[-1]


def _extract_organization_urls(html: str, *, source_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, str(anchor.get("href")))
        normalized_href = _normalize_http_url(href, field="href", required=False)
        if not normalized_href:
            continue

        parsed = urlparse(normalized_href)
        host = (parsed.hostname or "").casefold()
        path = parsed.path.rstrip("/")
        if host not in _FIND_YOUR_NEWS_HOSTS or not path.startswith("/organization/"):
            continue

        canonical_url = f"{parsed.scheme}://{parsed.netloc}{path}/"
        if canonical_url in seen:
            continue

        seen.add(canonical_url)
        urls.append(canonical_url)

    return urls


def _extract_text_blocks(soup: BeautifulSoup) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for block in soup.select("div.text-block"):
        label_element = block.find("h6")
        if label_element is None:
            continue
        label = _normalize_text(label_element.get_text(" ", strip=True)).casefold()
        paragraphs = [
            _normalize_text(paragraph.get_text(" ", strip=True))
            for paragraph in block.find_all("p")
            if _normalize_text(paragraph.get_text(" ", strip=True))
        ]
        if label and paragraphs:
            blocks[label] = "\n\n".join(paragraphs)
    return blocks


def _extract_link_or_text_list(container: Tag) -> list[str]:
    anchors = [
        _normalize_text(anchor.get_text(" ", strip=True))
        for anchor in container.find_all("a")
        if _normalize_text(anchor.get_text(" ", strip=True))
    ]
    if anchors:
        return _normalize_string_list(anchors)

    return _normalize_string_list(unescape(container.get_text(" ", strip=True)))


def _extract_core_details(soup: BeautifulSoup) -> dict[str, object]:
    details: dict[str, object] = {}
    for panel in soup.select("div.panel-content.core-details"):
        for label_element in panel.find_all("h6"):
            label = _normalize_text(label_element.get_text(" ", strip=True)).casefold()
            if not label:
                continue

            value_element = label_element.find_next_sibling()
            while value_element is not None and getattr(value_element, "name", None) == "hr":
                value_element = value_element.find_next_sibling()

            if value_element is None or getattr(value_element, "name", None) != "p":
                continue

            if label in {"places covered", "topics", "languages"}:
                details[label] = _extract_link_or_text_list(value_element)
            else:
                details[label] = _normalize_text(value_element.get_text(" ", strip=True))
    return details


def _parse_location(value: object) -> dict[str, object]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return {
            "location": "",
            "city": None,
            "country": None,
            "subdivision": None,
            "countries": [],
        }

    parts = [_normalize_text(part) for part in cleaned.split(",")]
    normalized_parts = [part for part in parts if part]

    city: str | None = None
    country: str | None = None
    subdivision: str | None = None

    if len(normalized_parts) >= _LOCATION_CITY_STATE_COUNTRY_PARTS:
        city = ", ".join(normalized_parts[:-2])
        subdivision = normalized_parts[-2]
        country = _normalize_country(normalized_parts[-1])
    elif len(normalized_parts) == _LOCATION_CITY_COUNTRY_PARTS:
        city = normalized_parts[0]
        last_part = normalized_parts[1]
        normalized_subdivision = _normalize_us_subdivision(last_part)
        if (
            last_part.upper() in _US_SUBDIVISION_NAMES
            or last_part.casefold() in _US_SUBDIVISION_NAMES_BY_CASEFOLD
        ):
            country = _USA
            subdivision = normalized_subdivision
        else:
            country = _normalize_country(last_part)
    elif len(normalized_parts) == 1:
        country = _normalize_country(normalized_parts[0])

    if country == _USA:
        subdivision = _normalize_us_subdivision(subdivision)

    return {
        "location": cleaned,
        "city": city,
        "country": country,
        "subdivision": subdivision,
        "countries": [country] if country else [],
    }


def _first_non_empty_text(*values: object) -> str:
    for value in values:
        cleaned = _normalize_text(value)
        if cleaned:
            return cleaned
    return ""


def _description_for_listing(*, tagline: str, mission: str, about: str) -> str:
    return (
        _first_non_empty_text(tagline, mission, about)
        or "Nonprofit newsroom listed in the INN Find Your News directory."
    )


def _parse_newsroom_detail_html(
    html: str,
    *,
    detail_url: str,
    source_label: str,
    source_url: str,
) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    hero = soup.select_one("div.hero-organization")
    name = _normalize_text(hero.find("h1").get_text(" ", strip=True) if hero else "")
    if not name:
        raise NewsroomDirectoryRefreshError(f"Missing newsroom name for {detail_url}")

    tagline = _normalize_text(hero.find("h4").get_text(" ", strip=True) if hero else "")
    text_blocks = _extract_text_blocks(soup)
    core_details = _extract_core_details(soup)
    mission = _normalize_text(text_blocks.get("mission"))
    about = _normalize_text(text_blocks.get("about our journalism"))
    location = _parse_location(core_details.get("location"))
    website_anchor = soup.find(id="button-website")
    website = (
        _normalize_http_url(website_anchor.get("href"), field="website", required=False)
        if website_anchor is not None
        else ""
    )

    slug_base = _slugify(_listing_path_slug(detail_url) or name)
    if not slug_base:
        raise NewsroomDirectoryRefreshError(
            f"Newsroom slug normalized to an empty value: {detail_url}"
        )

    return {
        "id": f"newsroom-{slug_base}",
        "slug": f"newsroom~{slug_base}",
        "name": name,
        "website": website,
        "description": _description_for_listing(tagline=tagline, mission=mission, about=about),
        "directory_url": detail_url,
        "tagline": tagline,
        "mission": mission,
        "about": about,
        "location": location["location"],
        "city": location["city"],
        "country": location["country"],
        "subdivision": location["subdivision"],
        "countries": location["countries"],
        "places_covered": _normalize_string_list(core_details.get("places covered", [])),
        "languages": _normalize_string_list(core_details.get("languages", [])),
        "topics": _normalize_string_list(core_details.get("topics", [])),
        "reach": _normalize_text(core_details.get("reach")),
        "year_founded": _normalize_text(core_details.get("year founded")),
        "source_label": source_label,
        "source_url": source_url,
    }


def _normalize_newsroom_row(
    row: Mapping[str, object],
    *,
    source_label: str,
    source_url: str,
) -> dict[str, object]:
    row_id = _first_non_empty_text(row.get("id"))
    if not row_id:
        raise NewsroomDirectoryRefreshError("Missing required newsroom id")

    row_slug = _first_non_empty_text(row.get("slug"))
    if not row_slug:
        raise NewsroomDirectoryRefreshError("Missing required newsroom slug")

    name = _first_non_empty_text(row.get("name"))
    if not name:
        raise NewsroomDirectoryRefreshError("Missing required newsroom name")

    normalized_country = _normalize_country(_first_non_empty_text(row.get("country"))) or None
    normalized_subdivision = _first_non_empty_text(row.get("subdivision")) or None
    if normalized_country == _USA:
        normalized_subdivision = _normalize_us_subdivision(normalized_subdivision)

    countries = _normalize_string_list(row.get("countries"))
    if normalized_country and normalized_country not in countries:
        countries = [normalized_country]

    return {
        "id": row_id,
        "slug": row_slug,
        "name": name,
        "website": _normalize_http_url(row.get("website"), field="website", required=False),
        "description": _description_for_listing(
            tagline=_first_non_empty_text(row.get("tagline")),
            mission=_first_non_empty_text(row.get("mission")),
            about=_first_non_empty_text(row.get("about")),
        )
        if not _first_non_empty_text(row.get("description"))
        else _first_non_empty_text(row.get("description")),
        "directory_url": _normalize_http_url(
            row.get("directory_url"),
            field="directory_url",
            required=True,
        ),
        "tagline": _first_non_empty_text(row.get("tagline")),
        "mission": _first_non_empty_text(row.get("mission")),
        "about": _first_non_empty_text(row.get("about")),
        "location": _first_non_empty_text(row.get("location")),
        "city": _first_non_empty_text(row.get("city")) or None,
        "country": normalized_country,
        "subdivision": normalized_subdivision,
        "countries": countries,
        "places_covered": _normalize_string_list(row.get("places_covered")),
        "languages": _normalize_string_list(row.get("languages")),
        "topics": _normalize_string_list(row.get("topics")),
        "reach": _first_non_empty_text(row.get("reach")),
        "year_founded": _first_non_empty_text(row.get("year_founded")),
        "source_label": _first_non_empty_text(row.get("source_label")) or source_label,
        "source_url": _normalize_http_url(
            row.get("source_url"),
            field="source_url",
            required=False,
        )
        or source_url,
    }


def fetch_newsroom_directory_rows(
    *,
    source_url: str = NEWSROOM_DIRECTORY_SOURCE_URL,
    timeout_seconds: float = 30.0,
    session: _SessionLike | None = None,
) -> list[dict[str, object]]:
    client = session or cast(_SessionLike, requests.Session())

    try:
        response = _get_with_retries(
            client,
            url=source_url,
            timeout_seconds=timeout_seconds,
        )
        detail_urls = _extract_organization_urls(response.text, source_url=source_url)
        if not detail_urls:
            raise NewsroomDirectoryRefreshError(
                "No newsroom listings were discovered from the public Explore page"
            )

        rows: list[dict[str, object]] = []
        for detail_url in detail_urls:
            detail_response = _get_with_retries(
                client,
                url=detail_url,
                timeout_seconds=timeout_seconds,
            )
            rows.append(
                _parse_newsroom_detail_html(
                    detail_response.text,
                    detail_url=detail_url,
                    source_label=NEWSROOM_DIRECTORY_SOURCE_LABEL,
                    source_url=detail_url,
                )
            )
    except requests.RequestException as exc:
        raise NewsroomDirectoryRefreshError(
            f"Failed to fetch INN Find Your News listings: {exc}"
        ) from exc

    return rows


def refresh_newsroom_directory_rows(
    raw_rows: Sequence[Mapping[str, object]],
    *,
    source_label: str = NEWSROOM_DIRECTORY_SOURCE_LABEL,
    source_url: str = NEWSROOM_DIRECTORY_SOURCE_URL,
) -> list[dict[str, object]]:
    rows = [
        _normalize_newsroom_row(row, source_label=source_label, source_url=source_url)
        for row in raw_rows
    ]

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for row in rows:
        row_id = row["id"]
        if not isinstance(row_id, str):
            raise NewsroomDirectoryRefreshError("Normalized row id must be a string")
        if row_id in seen_ids:
            raise NewsroomDirectoryRefreshError(f"Duplicate newsroom listing id: {row_id}")
        seen_ids.add(row_id)

        row_slug = row["slug"]
        if not isinstance(row_slug, str):
            raise NewsroomDirectoryRefreshError("Normalized row slug must be a string")
        if row_slug in seen_slugs:
            raise NewsroomDirectoryRefreshError(f"Duplicate newsroom listing slug: {row_slug}")
        seen_slugs.add(row_slug)

    return sorted(rows, key=lambda row: (_sort_key(str(row["name"])), str(row["id"])))


def render_newsroom_refresh_summary(
    *,
    source_url: str,
    total_count: int,
    added_count: int,
    removed_count: int,
    updated_count: int,
) -> str:
    lines = [
        "## Newsroom Directory Refresh Summary",
        "",
        f"- Source: {source_url}",
        f"- Total newsrooms: {total_count}",
        f"- Added newsrooms: {added_count}",
        f"- Removed newsrooms: {removed_count}",
        f"- Updated newsrooms: {updated_count}",
    ]
    return "\n".join(lines) + "\n"

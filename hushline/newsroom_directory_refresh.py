from __future__ import annotations

import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from html import unescape
from typing import Mapping, Protocol, Sequence, cast
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from unidecode import unidecode

NEWSROOM_DIRECTORY_SOURCE_LABEL = "INN Find Your News directory"
NEWSROOM_DIRECTORY_SOURCE_URL = "https://findyournews.org/explore/"
EUROPEAN_NEWSROOM_DIRECTORY_SOURCE_LABEL = "Directory of European Journalism Networks"
EUROPEAN_NEWSROOM_DIRECTORY_SOURCE_URL = "https://journalismdirectory.org/search-networks/"

_NEWSROOM_USER_AGENT = (
    "Mozilla/5.0 (compatible; HushlineNewsroomSync/1.0; +https://github.com/scidsg/hushline)"
)
_FIND_YOUR_NEWS_HOSTS = frozenset({"findyournews.org", "www.findyournews.org"})
_EUROPEAN_DIRECTORY_HOSTS = frozenset({"journalismdirectory.org", "www.journalismdirectory.org"})
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


@dataclass(frozen=True)
class NewsroomDirectorySource:
    label: str
    browse_url: str
    listing_hosts: frozenset[str]
    listing_path_prefix: str
    browse_path_prefixes: tuple[str, ...] = ()


NEWSROOM_DIRECTORY_SOURCES = (
    NewsroomDirectorySource(
        label=NEWSROOM_DIRECTORY_SOURCE_LABEL,
        browse_url=NEWSROOM_DIRECTORY_SOURCE_URL,
        listing_hosts=_FIND_YOUR_NEWS_HOSTS,
        listing_path_prefix="/organization/",
        browse_path_prefixes=("/explore/",),
    ),
    NewsroomDirectorySource(
        label=EUROPEAN_NEWSROOM_DIRECTORY_SOURCE_LABEL,
        browse_url=EUROPEAN_NEWSROOM_DIRECTORY_SOURCE_URL,
        listing_hosts=_EUROPEAN_DIRECTORY_HOSTS,
        listing_path_prefix="/network/",
        browse_path_prefixes=(
            "/search-networks/",
            "/network-focus/",
            "/network-size/",
        ),
    ),
)


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


def _canonicalize_public_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    if path != "/":
        path = f"{path}/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


def _path_matches_public_prefixes(path: str, prefixes: Sequence[str]) -> bool:
    normalized_path = path.rstrip("/") or "/"
    for prefix in prefixes:
        normalized_prefix = prefix.rstrip("/") or "/"
        if normalized_path == normalized_prefix or normalized_path.startswith(
            f"{normalized_prefix}/"
        ):
            return True
    return False


def _extract_listing_urls(
    html: str,
    *,
    source_url: str,
    allowed_hosts: frozenset[str],
    listing_path_prefix: str,
) -> list[str]:
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
        if host not in allowed_hosts or not path.startswith(listing_path_prefix):
            continue

        canonical_url = f"{parsed.scheme}://{parsed.netloc}{path}/"
        if canonical_url in seen:
            continue

        seen.add(canonical_url)
        urls.append(canonical_url)

    return urls


def _extract_organization_urls(html: str, *, source_url: str) -> list[str]:
    return _extract_listing_urls(
        html,
        source_url=source_url,
        allowed_hosts=_FIND_YOUR_NEWS_HOSTS,
        listing_path_prefix="/organization/",
    )


def _extract_european_network_urls(html: str, *, source_url: str) -> list[str]:
    return _extract_listing_urls(
        html,
        source_url=source_url,
        allowed_hosts=_EUROPEAN_DIRECTORY_HOSTS,
        listing_path_prefix="/network/",
    )


def _extract_source_browse_page_urls(
    source: NewsroomDirectorySource,
    html: str,
    *,
    source_url: str,
) -> list[str]:
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
        path = parsed.path.rstrip("/") or "/"
        if host not in source.listing_hosts or path.startswith(source.listing_path_prefix):
            continue

        if not _path_matches_public_prefixes(path, source.browse_path_prefixes):
            continue

        canonical_url = _canonicalize_public_url(normalized_href)
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


def _description_for_listing(
    *,
    tagline: str,
    mission: str,
    about: str,
    fallback_description: str,
) -> str:
    return _first_non_empty_text(tagline, mission, about) or fallback_description


def _parse_newsroom_detail_html(
    html: str,
    *,
    detail_url: str,
    source_label: str,
    source_url: str,
) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    hero = soup.select_one("div.hero-organization")
    heading = hero.find("h1") if hero else None
    name = _normalize_text(heading.get_text(" ", strip=True) if heading is not None else "")
    if not name:
        raise NewsroomDirectoryRefreshError(f"Missing newsroom name for {detail_url}")

    tagline_element = hero.find("h4") if hero else None
    tagline = _normalize_text(
        tagline_element.get_text(" ", strip=True) if tagline_element is not None else ""
    )
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
        "description": _description_for_listing(
            tagline=tagline,
            mission=mission,
            about=about,
            fallback_description="Newsroom listing imported from a public journalism directory.",
        ),
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


def _find_heading(
    soup: BeautifulSoup,
    heading_text: str,
    *,
    tag_names: tuple[str, ...] = ("h2", "h3"),
) -> Tag | None:
    target = heading_text.casefold()
    for heading in soup.find_all(tag_names):
        if _normalize_text(heading.get_text(" ", strip=True)).casefold() == target:
            return heading
    return None


def _extract_section_paragraph_text(soup: BeautifulSoup, heading_text: str) -> str:
    heading = _find_heading(soup, heading_text)
    if heading is None:
        return ""

    paragraphs: list[str] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3"}:
            break
        if isinstance(sibling, Tag) and sibling.name == "p":
            text = _normalize_text(sibling.get_text(" ", strip=True))
            if text:
                paragraphs.append(text)

    return "\n\n".join(paragraphs)


def _extract_heading_list(soup: BeautifulSoup, heading_text: str) -> list[str]:
    heading = _find_heading(soup, heading_text)
    if heading is None:
        return []

    list_element = heading.find_next_sibling("ul")
    if list_element is None:
        return []

    return _normalize_string_list(
        [
            _normalize_text(item.get_text(" ", strip=True))
            for item in list_element.find_all("li")
            if _normalize_text(item.get_text(" ", strip=True))
        ]
    )


def _extract_colon_details(container: Tag) -> dict[str, str]:
    details: dict[str, str] = {}
    current_key = ""
    current_value_parts: list[str] = []

    def commit_current_key() -> None:
        nonlocal current_key, current_value_parts
        if current_key:
            value = _normalize_text(" ".join(current_value_parts))
            if value:
                details[current_key] = value
        current_key = ""
        current_value_parts = []

    for child in container.children:
        if isinstance(child, NavigableString):
            text = _normalize_text(str(child))
            if text:
                current_value_parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        if child.name == "strong":
            commit_current_key()
            current_key = (
                _normalize_text(child.get_text(" ", strip=True)).removesuffix(":").casefold()
            )
            continue

        if child.name == "br":
            continue

        text = _normalize_text(child.get_text(" ", strip=True))
        if text:
            current_value_parts.append(text)

    commit_current_key()
    return details


def _extract_contact_website(soup: BeautifulSoup) -> str:
    contact_heading = _find_heading(soup, "Contact", tag_names=("h2",))
    if contact_heading is None:
        return ""

    for sibling in contact_heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3"}:
            break
        if not isinstance(sibling, Tag):
            continue

        website_anchor = sibling.find("a", href=True)
        if website_anchor is None:
            continue

        return _normalize_http_url(website_anchor.get("href"), field="website", required=False)

    return ""


def _parse_european_network_detail_html(
    html: str,
    *,
    detail_url: str,
    source_label: str,
    source_url: str,
) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    name = _normalize_text(
        soup.find("h1").get_text(" ", strip=True) if soup.find("h1") is not None else ""
    )
    if not name:
        raise NewsroomDirectoryRefreshError(f"Missing newsroom name for {detail_url}")

    description = ""
    heading = soup.find("h1")
    if isinstance(heading, Tag):
        summary_paragraph = heading.find_next_sibling("p")
        if summary_paragraph is not None:
            description = _normalize_text(summary_paragraph.get_text(" ", strip=True))

    about = _extract_section_paragraph_text(soup, "About the network")
    mission = _extract_section_paragraph_text(soup, "Projects")
    website = _extract_contact_website(soup)

    network_details_heading = _find_heading(soup, "Network details")
    network_detail_values = (
        _extract_colon_details(network_details_heading.find_next_sibling("p"))
        if network_details_heading is not None
        and network_details_heading.find_next_sibling("p") is not None
        else {}
    )
    countries = _normalize_string_list(_extract_heading_list(soup, "Countries"))
    country = countries[0] if len(countries) == 1 else None

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
        "description": _description_for_listing(
            tagline="",
            mission=description,
            about=about,
            fallback_description="Journalism network listing imported from a public directory.",
        ),
        "directory_url": detail_url,
        "tagline": "",
        "mission": mission,
        "about": about,
        "location": "",
        "city": None,
        "country": country,
        "subdivision": None,
        "countries": countries,
        "places_covered": [],
        "languages": [],
        "topics": _extract_heading_list(soup, "Subjects"),
        "reach": _normalize_text(network_detail_values.get("geographical focus")),
        "year_founded": _normalize_text(network_detail_values.get("founded")),
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
            fallback_description="Newsroom listing imported from a public journalism directory.",
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


def _parse_source_detail_html(
    source: NewsroomDirectorySource,
    html: str,
    *,
    detail_url: str,
) -> dict[str, object]:
    if source.browse_url == EUROPEAN_NEWSROOM_DIRECTORY_SOURCE_URL:
        return _parse_european_network_detail_html(
            html,
            detail_url=detail_url,
            source_label=source.label,
            source_url=source.browse_url,
        )

    return _parse_newsroom_detail_html(
        html,
        detail_url=detail_url,
        source_label=source.label,
        source_url=source.browse_url,
    )


def _extract_source_listing_urls(source: NewsroomDirectorySource, html: str) -> list[str]:
    return _extract_listing_urls(
        html,
        source_url=source.browse_url,
        allowed_hosts=source.listing_hosts,
        listing_path_prefix=source.listing_path_prefix,
    )


def _fetch_rows_for_source(
    source: NewsroomDirectorySource,
    *,
    client: _SessionLike,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    try:
        detail_urls: list[str] = []
        seen_detail_urls: set[str] = set()
        pending_browse_urls = deque([_canonicalize_public_url(source.browse_url)])
        seen_browse_urls: set[str] = set()

        while pending_browse_urls:
            browse_url = pending_browse_urls.popleft()
            if browse_url in seen_browse_urls:
                continue

            seen_browse_urls.add(browse_url)
            response = _get_with_retries(
                client,
                url=browse_url,
                timeout_seconds=timeout_seconds,
            )

            for detail_url in _extract_source_listing_urls(source, response.text):
                if detail_url in seen_detail_urls:
                    continue
                seen_detail_urls.add(detail_url)
                detail_urls.append(detail_url)

            for discovered_browse_url in _extract_source_browse_page_urls(
                source,
                response.text,
                source_url=browse_url,
            ):
                if discovered_browse_url in seen_browse_urls:
                    continue
                pending_browse_urls.append(discovered_browse_url)

        if not detail_urls:
            raise NewsroomDirectoryRefreshError(
                f"No newsroom listings were discovered from {source.label}"
            )

        rows: list[dict[str, object]] = []
        for detail_url in detail_urls:
            detail_response = _get_with_retries(
                client,
                url=detail_url,
                timeout_seconds=timeout_seconds,
            )
            rows.append(
                _parse_source_detail_html(
                    source,
                    detail_response.text,
                    detail_url=detail_url,
                )
            )

        if not rows:  # pragma: no cover
            raise NewsroomDirectoryRefreshError(f"No newsroom rows were parsed from {source.label}")
        return rows
    except requests.RequestException as exc:
        raise NewsroomDirectoryRefreshError(
            f"Failed to fetch {source.label} listings: {exc}"
        ) from exc


def fetch_newsroom_directory_rows(
    *,
    timeout_seconds: float = 30.0,
    session: _SessionLike | None = None,
) -> list[dict[str, object]]:
    client = session or cast(_SessionLike, requests.Session())
    rows: list[dict[str, object]] = []
    for source in NEWSROOM_DIRECTORY_SOURCES:
        rows.extend(_fetch_rows_for_source(source, client=client, timeout_seconds=timeout_seconds))
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
    source_urls: Sequence[str],
    total_count: int,
    added_count: int,
    removed_count: int,
    updated_count: int,
) -> str:
    lines = [
        "## Newsroom Directory Refresh Summary",
        "",
        f"- Sources: {', '.join(source_urls)}",
        f"- Total newsrooms: {total_count}",
        f"- Added newsrooms: {added_count}",
        f"- Removed newsrooms: {removed_count}",
        f"- Updated newsrooms: {updated_count}",
    ]
    return "\n".join(lines) + "\n"

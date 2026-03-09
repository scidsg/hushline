from __future__ import annotations

import re
import unicodedata
from typing import Mapping, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

GLOBALEAKS_SOURCE_LABEL = "GlobaLeaks use case page"
GLOBALEAKS_SOURCE_URL = "https://www.globaleaks.org/usecases/"
GLOBALEAKS_USECASE_PAGES: tuple[dict[str, str], ...] = (
    {
        "source_label": "GlobaLeaks anti-corruption use case page",
        "source_url": "https://www.globaleaks.org/usecases/anti-corruption/",
    },
    {
        "source_label": "GlobaLeaks investigative journalism use case page",
        "source_url": "https://www.globaleaks.org/usecases/investigative-journalism/",
    },
)

_GLOBALEAKS_USER_AGENT = (
    "Mozilla/5.0 (compatible; HushlineGlobaLeaksSync/1.0; " "+https://github.com/scidsg/hushline)"
)
_DISCOVERY_EXCLUDED_HOSTS = {
    "globaleaks.org",
    "www.globaleaks.org",
    "docs.globaleaks.org",
    "forum.globaleaks.org",
    "community.globaleaks.org",
    "github.com",
    "www.github.com",
    "transifex.com",
    "www.transifex.com",
    "torproject.org",
    "www.torproject.org",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "www.facebook.com",
    "youtube.com",
    "www.youtube.com",
}
_DISCOVERY_KEYWORDS = (
    "leak",
    "whistle",
    "source",
    "secure",
    "submit",
    "tip",
    "report",
    "denunc",
    "segnal",
    "signal",
    "anticorru",
    "transparen",
    "bianco",
)


class GlobaLeaksDirectoryRefreshError(Exception):
    pass


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _slugify(value: str) -> str:
    normalized = _sort_key(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _normalize_split_string(value: str) -> list[str]:
    separators = value.replace("|", ",").replace(";", ",")
    return [item.strip() for item in separators.split(",") if item.strip()]


def _normalize_string_list(value: object) -> list[str]:
    raw_values: list[str] = []
    if isinstance(value, list):
        raw_values = [item for item in value if isinstance(item, str)]
    elif isinstance(value, str):
        raw_values = _normalize_split_string(value)
    else:
        return []

    normalized_values: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_values:
        cleaned = raw_item.strip()
        if not cleaned:
            continue
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_values.append(cleaned)
    return normalized_values


def _get_nested_value(row: Mapping[str, object], dotted_key: str) -> object:
    if dotted_key in row:
        return row[dotted_key]

    current: object = row
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _first_non_empty_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return ""


def _normalize_http_url(
    value: object,
    *,
    field: str,
    required: bool,
) -> str:
    if not isinstance(value, str):
        if required:
            raise GlobaLeaksDirectoryRefreshError(f"Missing required URL field: {field}")
        return ""

    cleaned = value.strip()
    if not cleaned:
        if required:
            raise GlobaLeaksDirectoryRefreshError(f"Missing required URL field: {field}")
        return ""

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        if required:
            raise GlobaLeaksDirectoryRefreshError(
                f"Invalid URL for field {field}: expected absolute http/https URL"
            )
        return ""

    return cleaned


def _candidate_hosts(row: Mapping[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("host", "hostname", "server_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    for key in ("hostnames", "domains"):
        values.extend(_normalize_string_list(row.get(key)))

    for key in ("ssl.cert.subject.cn", "http.host", "ip_str"):
        value = _get_nested_value(row, key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    cleaned_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        parsed = urlparse(value)
        hostname = parsed.hostname or value
        normalized = hostname.strip().lower().strip(".")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned_values.append(normalized)
    return cleaned_values


def _infer_scheme(row: Mapping[str, object]) -> str:
    port = row.get("port")
    if isinstance(port, str) and port.isdigit():
        port = int(port)
    if isinstance(port, int) and port in {443, 8443}:
        return "https"

    module = _first_non_empty_string(_get_nested_value(row, "_shodan.module"), row.get("module"))
    if module.startswith("https"):
        return "https"

    if _get_nested_value(row, "ssl.cert.subject.cn"):
        return "https"

    return "http"


def _choose_submission_url(row: Mapping[str, object]) -> str:
    for key in ("submission_url", "url"):
        value = row.get(key)
        if value in {None, ""}:
            continue
        return _normalize_http_url(value, field=key, required=True)

    website = row.get("website")
    if website not in {None, ""}:
        normalized_website = _normalize_http_url(website, field="website", required=False)
        if normalized_website:
            return normalized_website

    http_location = _get_nested_value(row, "http.location")
    normalized_http_location = _normalize_http_url(
        http_location,
        field="http.location",
        required=False,
    )
    if normalized_http_location:
        return normalized_http_location

    candidate_hosts = _candidate_hosts(row)
    if not candidate_hosts:
        raise GlobaLeaksDirectoryRefreshError(
            "GlobaLeaks row is missing a usable submission URL or host"
        )

    host = candidate_hosts[0]
    return f"{_infer_scheme(row)}://{host}/"


def _choose_host(row: Mapping[str, object], submission_url: str) -> str:
    parsed_host = urlparse(submission_url).hostname or ""
    if parsed_host:
        return parsed_host

    candidate_hosts = _candidate_hosts(row)
    if candidate_hosts:
        return candidate_hosts[0]

    raise GlobaLeaksDirectoryRefreshError("GlobaLeaks row is missing a usable host")


def _choose_name(row: Mapping[str, object], host: str) -> str:
    name = _first_non_empty_string(
        row.get("name"),
        row.get("organization"),
        row.get("title"),
        _get_nested_value(row, "http.title"),
        _get_nested_value(row, "ssl.cert.subject.cn"),
    )
    return name or host


def _choose_description(row: Mapping[str, object]) -> str:
    description = _first_non_empty_string(row.get("description"), _get_nested_value(row, "summary"))
    if description:
        return description
    return "GlobaLeaks instance listed on the GlobaLeaks use case pages."


def _choose_countries(row: Mapping[str, object]) -> list[str]:
    countries = _normalize_string_list(row.get("countries"))
    if countries:
        return countries

    country = _first_non_empty_string(
        row.get("country_name"),
        _get_nested_value(row, "location.country_name"),
        row.get("country"),
    )
    return [country] if country else []


def _choose_languages(row: Mapping[str, object]) -> list[str]:
    languages = _normalize_string_list(row.get("languages"))
    if languages:
        return languages

    language = _first_non_empty_string(
        row.get("language"),
        _get_nested_value(row, "http.html_lang"),
        _get_nested_value(row, "http.html_language"),
    )
    return [language] if language else []


def _normalize_globaleaks_row(
    row: Mapping[str, object],
    *,
    source_label: str,
    source_url: str,
) -> dict[str, object]:
    submission_url = _choose_submission_url(row)
    host = _choose_host(row, submission_url)
    name = _choose_name(row, host)
    slug_base = _slugify(host)
    if not slug_base:
        raise GlobaLeaksDirectoryRefreshError("GlobaLeaks slug normalized to an empty value")

    website = (
        _normalize_http_url(row.get("website"), field="website", required=False) or submission_url
    )
    normalized_source_label = _first_non_empty_string(row.get("source_label")) or source_label
    normalized_source_url = (
        _normalize_http_url(row.get("source_url"), field="source_url", required=False) or source_url
    )

    return {
        "id": f"globaleaks-{slug_base}",
        "slug": f"globaleaks~{slug_base}",
        "name": name,
        "website": website,
        "description": _choose_description(row),
        "submission_url": submission_url,
        "host": host,
        "countries": _choose_countries(row),
        "languages": _choose_languages(row),
        "source_label": normalized_source_label,
        "source_url": normalized_source_url,
    }


def refresh_globaleaks_directory_rows(
    raw_rows: Sequence[Mapping[str, object]],
    *,
    source_label: str = GLOBALEAKS_SOURCE_LABEL,
    source_url: str = GLOBALEAKS_SOURCE_URL,
) -> list[dict[str, object]]:
    rows = [
        _normalize_globaleaks_row(
            row,
            source_label=source_label,
            source_url=source_url,
        )
        for row in raw_rows
    ]

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for row in rows:
        row_id = row["id"]
        if not isinstance(row_id, str):
            raise GlobaLeaksDirectoryRefreshError("Normalized row id must be a string")
        if row_id in seen_ids:
            raise GlobaLeaksDirectoryRefreshError(f"Duplicate GlobaLeaks listing id: {row_id}")
        seen_ids.add(row_id)

        row_slug = row["slug"]
        if not isinstance(row_slug, str):
            raise GlobaLeaksDirectoryRefreshError("Normalized row slug must be a string")
        if row_slug in seen_slugs:
            raise GlobaLeaksDirectoryRefreshError(f"Duplicate GlobaLeaks listing slug: {row_slug}")
        seen_slugs.add(row_slug)

    return sorted(rows, key=lambda row: (_sort_key(str(row["name"])), str(row["id"])))


def _known_row_hosts(row: Mapping[str, object]) -> set[str]:
    hosts = set(_candidate_hosts(row))
    for key in ("website", "submission_url"):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        hostname = urlparse(value).hostname
        if hostname:
            hosts.add(hostname.strip().lower().strip("."))
    return hosts


def _index_known_rows_by_host(
    known_rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for row in known_rows:
        materialized_row = dict(row)
        for host in _known_row_hosts(materialized_row):
            indexed.setdefault(host, materialized_row)
    return indexed


def _looks_like_globaleaks_candidate(host: str, url: str) -> bool:
    candidate_text = f"{host} {urlparse(url).path}".casefold()
    return any(keyword in candidate_text for keyword in _DISCOVERY_KEYWORDS)


def _extract_discovery_links(
    html: str,
    *,
    source_url: str,
    known_hosts: set[str],
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    source_host = (urlparse(source_url).hostname or "").casefold()
    discovered: list[dict[str, str]] = []
    seen_hosts: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = _normalize_http_url(anchor.get("href"), field="href", required=False)
        if not href:
            continue

        host = (urlparse(href).hostname or "").casefold().strip(".")
        if not host or host == source_host or host in _DISCOVERY_EXCLUDED_HOSTS:
            continue
        if host in seen_hosts:
            continue
        if host not in known_hosts and not _looks_like_globaleaks_candidate(host, href):
            continue

        seen_hosts.add(host)
        discovered.append(
            {
                "name": anchor.get_text(" ", strip=True) or host,
                "url": href,
                "host": host,
            }
        )

    return discovered


def fetch_globaleaks_directory_rows(
    *,
    known_rows: Sequence[Mapping[str, object]] = (),
    source_pages: Sequence[Mapping[str, str]] = GLOBALEAKS_USECASE_PAGES,
    timeout_seconds: float = 30.0,
    session: requests.Session | None = None,
) -> list[dict[str, object]]:
    client = session or requests.Session()
    known_by_host = _index_known_rows_by_host(known_rows)
    discovered_rows: list[dict[str, object]] = []
    seen_hosts: set[str] = set()

    try:
        for source_page in source_pages:
            source_label = _first_non_empty_string(source_page.get("source_label"))
            source_url = _normalize_http_url(
                source_page.get("source_url"),
                field="source_url",
                required=True,
            )
            response = client.get(
                source_url,
                timeout=timeout_seconds,
                headers={"User-Agent": _GLOBALEAKS_USER_AGENT},
            )
            response.raise_for_status()
            links = _extract_discovery_links(
                response.text,
                source_url=source_url,
                known_hosts=set(known_by_host),
            )
            for link in links:
                host = link["host"]
                if host in seen_hosts:
                    continue
                seen_hosts.add(host)

                existing_row = known_by_host.get(host)
                if existing_row is not None:
                    row = dict(existing_row)
                    row["source_label"] = source_label
                    row["source_url"] = source_url
                    discovered_rows.append(row)
                    continue

                discovered_rows.append(
                    {
                        "name": link["name"],
                        "website": link["url"],
                        "submission_url": link["url"],
                        "host": host,
                        "source_label": source_label,
                        "source_url": source_url,
                    }
                )
    except requests.RequestException as exc:
        raise GlobaLeaksDirectoryRefreshError(
            f"Failed to fetch GlobaLeaks discovery pages: {exc}"
        ) from exc

    if not discovered_rows:
        raise GlobaLeaksDirectoryRefreshError(
            "No GlobaLeaks listings were discovered from the configured source pages"
        )

    return discovered_rows


def render_globaleaks_refresh_summary(
    *,
    source_url: str,
    total_count: int,
    added_count: int,
    removed_count: int,
    updated_count: int,
) -> str:
    lines = [
        "## GlobaLeaks Directory Refresh Summary",
        "",
        f"- Source: {source_url}",
        f"- Total instances: {total_count}",
        f"- Added instances: {added_count}",
        f"- Removed instances: {removed_count}",
        f"- Updated instances: {updated_count}",
    ]
    return "\n".join(lines) + "\n"

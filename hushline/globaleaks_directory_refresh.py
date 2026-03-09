from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

from unidecode import unidecode

GLOBALEAKS_SOURCE_LABEL = "Automated GlobaLeaks discovery dataset"
GLOBALEAKS_SOURCE_URL = "https://www.shodan.io/"


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
    return "GlobaLeaks instance discovered from an automated dataset."


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
        "source_label": source_label,
        "source_url": source_url,
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


def load_globaleaks_source_rows(path: Path) -> list[dict[str, object]]:
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise GlobaLeaksDirectoryRefreshError(f"Input file is empty: {path}")

    if path.suffix.lower() == ".csv":
        return _load_csv_rows(raw_text)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return _load_json_lines_rows(raw_text, path)

    if isinstance(parsed, list):
        if not all(isinstance(row, dict) for row in parsed):
            raise GlobaLeaksDirectoryRefreshError(
                "GlobaLeaks input array must contain only JSON objects"
            )
        return [dict(row) for row in parsed]

    if isinstance(parsed, dict):
        matches = parsed.get("matches")
        if isinstance(matches, list) and all(isinstance(row, dict) for row in matches):
            return [dict(row) for row in matches]

    raise GlobaLeaksDirectoryRefreshError(
        "GlobaLeaks input must be a JSON array, JSON object with 'matches', CSV, or JSONL"
    )


def _load_csv_rows(raw_text: str) -> list[dict[str, object]]:
    reader = csv.DictReader(raw_text.splitlines())
    rows = [{key: value for key, value in row.items() if key is not None} for row in reader]
    if not rows:
        raise GlobaLeaksDirectoryRefreshError("GlobaLeaks CSV input is empty")
    return rows


def _load_json_lines_rows(raw_text: str, path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, line in enumerate(raw_text.splitlines(), start=1):
        cleaned = line.strip()
        if not cleaned:
            continue
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise GlobaLeaksDirectoryRefreshError(
                f"Invalid JSONL object at line {index}: {path}"
            ) from exc
        if not isinstance(parsed, dict):
            raise GlobaLeaksDirectoryRefreshError(
                f"JSONL input must contain only JSON objects: line {index}"
            )
        rows.append(dict(parsed))
    if not rows:
        raise GlobaLeaksDirectoryRefreshError(f"No JSON objects found in JSONL input: {path}")
    return rows


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

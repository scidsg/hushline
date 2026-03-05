from __future__ import annotations

import re
import unicodedata
from typing import Mapping, Sequence

import requests
from unidecode import unidecode

SECUREDROP_DIRECTORY_API_URL = "https://securedrop.org/api/v1/directory/"
SECUREDROP_SOURCE_LABEL = "SecureDrop directory"
SECUREDROP_SOURCE_URL = SECUREDROP_DIRECTORY_API_URL

_SECUREDROP_USER_AGENT = (
    "Mozilla/5.0 (compatible; HushlineSecureDropSync/1.0; " "+https://github.com/scidsg/hushline)"
)


class SecureDropDirectoryRefreshError(Exception):
    pass


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _slugify(value: str) -> str:
    normalized = _sort_key(value)
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, str):
            continue
        cleaned = raw_item.strip()
        if not cleaned:
            continue
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized_values.append(cleaned)
    return normalized_values


def _get_required_str(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SecureDropDirectoryRefreshError(f"Missing required string field: {field}")
    return value.strip()


def _choose_website(row: Mapping[str, object]) -> str:
    for field in ("organization_url", "landing_page_url", "directory_url"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise SecureDropDirectoryRefreshError(
        "SecureDrop row is missing organization/landing/directory URL"
    )


def _normalize_securedrop_row(row: Mapping[str, object]) -> dict[str, object]:
    name = _get_required_str(row, "title")
    remote_slug = _get_required_str(row, "slug")
    directory_url = _get_required_str(row, "directory_url")
    onion_address = _get_required_str(row, "onion_address")
    normalized_slug = _slugify(remote_slug)
    if not normalized_slug:
        raise SecureDropDirectoryRefreshError("SecureDrop slug normalized to an empty value")

    description = ""
    raw_description = row.get("organization_description")
    if isinstance(raw_description, str):
        description = raw_description.strip()
    if not description:
        description = "SecureDrop instance listed in the SecureDrop directory."

    onion_name = ""
    raw_onion_name = row.get("onion_name")
    if isinstance(raw_onion_name, str):
        onion_name = raw_onion_name.strip()

    landing_page_url = ""
    raw_landing_page_url = row.get("landing_page_url")
    if isinstance(raw_landing_page_url, str):
        landing_page_url = raw_landing_page_url.strip()

    return {
        "id": f"securedrop-{normalized_slug}",
        "slug": f"securedrop~{normalized_slug}",
        "name": name,
        "website": _choose_website(row),
        "description": description,
        "directory_url": directory_url,
        "landing_page_url": landing_page_url,
        "onion_address": onion_address,
        "onion_name": onion_name,
        "countries": _normalize_string_list(row.get("countries")),
        "languages": _normalize_string_list(row.get("languages")),
        "topics": _normalize_string_list(row.get("topics")),
        "source_label": SECUREDROP_SOURCE_LABEL,
        "source_url": SECUREDROP_SOURCE_URL,
    }


def refresh_securedrop_directory_rows(
    raw_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows = [_normalize_securedrop_row(row) for row in raw_rows]

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for row in rows:
        row_id = row["id"]
        if not isinstance(row_id, str):
            raise SecureDropDirectoryRefreshError("Normalized row id must be a string")
        if row_id in seen_ids:
            raise SecureDropDirectoryRefreshError(f"Duplicate SecureDrop listing id: {row_id}")
        seen_ids.add(row_id)

        row_slug = row["slug"]
        if not isinstance(row_slug, str):
            raise SecureDropDirectoryRefreshError("Normalized row slug must be a string")
        if row_slug in seen_slugs:
            raise SecureDropDirectoryRefreshError(f"Duplicate SecureDrop listing slug: {row_slug}")
        seen_slugs.add(row_slug)

    return sorted(rows, key=lambda row: (_sort_key(str(row["name"])), str(row["id"])))


def fetch_securedrop_directory_rows(
    *,
    api_url: str = SECUREDROP_DIRECTORY_API_URL,
    timeout_seconds: float = 30.0,
    session: requests.Session | None = None,
) -> list[dict[str, object]]:
    client = session or requests.Session()
    response = client.get(
        api_url,
        timeout=timeout_seconds,
        headers={"User-Agent": _SECUREDROP_USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise SecureDropDirectoryRefreshError("SecureDrop API payload must be a JSON array")
    if not all(isinstance(item, dict) for item in payload):
        raise SecureDropDirectoryRefreshError(
            "SecureDrop API payload must contain only JSON objects"
        )
    return [dict(item) for item in payload]


def render_securedrop_refresh_summary(
    *,
    source_url: str,
    total_count: int,
    added_count: int,
    removed_count: int,
    updated_count: int,
) -> str:
    lines = [
        "## SecureDrop Directory Refresh Summary",
        "",
        f"- Source: {source_url}",
        f"- Total instances: {total_count}",
        f"- Added instances: {added_count}",
        f"- Removed instances: {removed_count}",
        f"- Updated instances: {updated_count}",
    ]
    return "\n".join(lines) + "\n"

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, TypedDict

import requests
from unidecode import unidecode

LISTING_URL_FIELDS: tuple[str, str] = ("website", "source_url")

DEFAULT_REGION_STATE_MAP: dict[str, frozenset[str]] = {
    "US": frozenset({"DC", "NY", "PA", "CA", "MD", "WA", "MA"}),
    "EU": frozenset(
        {
            "Austria",
            "Belgium",
            "Finland",
            "France",
            "Germany",
            "Italy",
            "Luxembourg",
            "Netherlands",
            "Portugal",
            "Spain",
            "Sweden",
        },
    ),
    "APAC": frozenset({"Australia", "India", "Japan", "Singapore"}),
}

DEFAULT_REGION_TARGETS: dict[str, int] = {"US": 20, "EU": 20, "APAC": 19}

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_BROKEN_STATUS_CODES = frozenset({404, 410})
_HTTP_SERVER_ERROR_MIN_STATUS = 500
_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_MAX_ATTEMPTS = 3
_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_PUBLIC_RECORD_SLUG_PREFIX = "public-record~"


class PublicRecordRow(TypedDict):
    id: str
    slug: str
    name: str
    website: str
    description: str
    city: str
    state: str
    practice_tags: list[str]
    source_label: str
    source_url: str | None


@dataclass(frozen=True)
class LinkCheckResult:
    ok: bool
    reason: str | None = None


@dataclass(frozen=True)
class LinkValidationFailure:
    listing_id: str
    listing_name: str
    field: str
    url: str
    reason: str


@dataclass(frozen=True)
class PublicRecordRefreshResult:
    rows: list[PublicRecordRow]
    region_counts: dict[str, int]
    checked_url_count: int
    link_failures: list[LinkValidationFailure]
    dropped_record_ids: list[str]


class PublicRecordRefreshError(RuntimeError):
    pass


@dataclass(frozen=True)
class _NormalizedListing:
    id: str
    slug: str
    name: str
    website: str
    description: str
    city: str
    state: str
    practice_tags: tuple[str, ...]
    source_label: str
    source_url: str | None
    region: str


LinkChecker = Callable[[str], LinkCheckResult]


def refresh_public_record_rows(  # noqa: PLR0913
    raw_rows: Sequence[Mapping[str, object]],
    *,
    selected_regions: Sequence[str] | None = None,
    region_state_map: Mapping[str, frozenset[str]] = DEFAULT_REGION_STATE_MAP,
    region_targets: Mapping[str, int] | None = DEFAULT_REGION_TARGETS,
    link_checker: LinkChecker | None = None,
    drop_failed_links: bool = False,
) -> PublicRecordRefreshResult:
    regions = tuple(selected_regions or DEFAULT_REGION_TARGETS.keys())
    _validate_regions(regions, region_state_map)

    rows = tuple(_normalize_row(raw_row, region_state_map) for raw_row in raw_rows)
    _validate_unique_ids_and_slugs(rows)
    region_scoped_rows = tuple(row for row in rows if row.region in regions)
    selected_rows = _apply_region_targets(region_scoped_rows, regions, region_targets)
    linked = _validate_links(selected_rows, link_checker, drop_failed_links)

    return PublicRecordRefreshResult(
        rows=[_to_output_row(row) for row in linked.rows],
        region_counts=_count_regions(linked.rows, regions),
        checked_url_count=linked.checked_url_count,
        link_failures=linked.failures,
        dropped_record_ids=linked.dropped_record_ids,
    )


def build_requests_link_checker(
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
    session: requests.Session | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> LinkChecker:
    if max_attempts < 1:
        raise PublicRecordRefreshError("--max-attempts must be >= 1")
    if timeout_seconds <= 0:
        raise PublicRecordRefreshError("--timeout-seconds must be > 0")

    request_session = session or requests.Session()
    request_session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; HushlinePublicRecordRefresh/1.0; "
                "+https://github.com/scidsg/hushline)"
            )
        }
    )

    def check_url(url: str) -> LinkCheckResult:
        last_error: requests.RequestException | None = None
        last_status_code: int | None = None

        for attempt in range(1, max_attempts + 1):
            response: requests.Response | None = None
            try:
                response = request_session.get(
                    url,
                    allow_redirects=True,
                    timeout=timeout_seconds,
                    stream=True,
                )
                last_status_code = response.status_code
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    break
            except requests.RequestException as exc:
                last_error = exc
            finally:
                if response is not None:
                    response.close()

            if attempt < max_attempts:
                sleep_fn(float(attempt))

        if last_status_code is not None and (
            last_status_code >= _HTTP_SERVER_ERROR_MIN_STATUS
            or last_status_code in _BROKEN_STATUS_CODES
        ):
            return LinkCheckResult(ok=False, reason=f"HTTP {last_status_code}")
        if last_error is not None and last_status_code is None:
            return LinkCheckResult(ok=False, reason=str(last_error))
        return LinkCheckResult(ok=True)

    return check_url


def render_refresh_summary(result: PublicRecordRefreshResult, *, regions: Sequence[str]) -> str:
    lines = [
        "## Public Record Refresh Summary",
        "",
        f"- Output records: {len(result.rows)}",
        f"- Unique URLs checked: {result.checked_url_count}",
        f"- Link failures detected: {len(result.link_failures)}",
        f"- Records dropped: {len(result.dropped_record_ids)}",
        "- Regional counts:",
    ]
    lines.extend([f"  - {region}: {result.region_counts.get(region, 0)}" for region in regions])

    if result.dropped_record_ids:
        lines.append("- Dropped IDs:")
        lines.extend([f"  - `{record_id}`" for record_id in result.dropped_record_ids])

    if result.link_failures:
        lines.append("- Link failures:")
        lines.extend(
            [
                (
                    f"  - `{failure.listing_id}` `{failure.field}` "
                    f"({failure.reason}): {failure.url}"
                )
                for failure in result.link_failures
            ]
        )

    return "\n".join(lines) + "\n"


def _validate_regions(
    regions: Sequence[str],
    region_state_map: Mapping[str, frozenset[str]],
) -> None:
    unknown_regions = sorted({region for region in regions if region not in region_state_map})
    if unknown_regions:
        raise PublicRecordRefreshError(f"Unknown regions requested: {', '.join(unknown_regions)}")


def _normalize_row(
    raw_row: Mapping[str, object],
    region_state_map: Mapping[str, frozenset[str]],
) -> _NormalizedListing:
    name = _required_string(raw_row, "name")
    state = _required_string(raw_row, "state")

    listing_id = _optional_string(raw_row.get("id")) or f"seed-{_slug_base(name)}"
    slug = _optional_string(raw_row.get("slug")) or (
        f"{_PUBLIC_RECORD_SLUG_PREFIX}{_slug_base(name)}"
    )
    if not slug.startswith(_PUBLIC_RECORD_SLUG_PREFIX):
        raise PublicRecordRefreshError(
            f"Listing slug must start with '{_PUBLIC_RECORD_SLUG_PREFIX}': {slug}",
        )

    region = _region_for_state(state, region_state_map)
    practice_tags = _normalize_practice_tags(raw_row.get("practice_tags"))

    return _NormalizedListing(
        id=listing_id,
        slug=slug,
        name=name,
        website=_required_string(raw_row, "website"),
        description=_required_string(raw_row, "description"),
        city=_required_string(raw_row, "city"),
        state=state,
        practice_tags=practice_tags,
        source_label=_required_string(raw_row, "source_label"),
        source_url=_optional_string(raw_row.get("source_url")),
        region=region,
    )


def _validate_unique_ids_and_slugs(rows: Sequence[_NormalizedListing]) -> None:
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for row in rows:
        if row.id in seen_ids:
            raise PublicRecordRefreshError(f"Duplicate listing id detected: {row.id}")
        if row.slug in seen_slugs:
            raise PublicRecordRefreshError(f"Duplicate listing slug detected: {row.slug}")
        seen_ids.add(row.id)
        seen_slugs.add(row.slug)


def _apply_region_targets(
    rows: Sequence[_NormalizedListing],
    regions: Sequence[str],
    region_targets: Mapping[str, int] | None,
) -> list[_NormalizedListing]:
    bucketed: dict[str, list[_NormalizedListing]] = {region: [] for region in regions}
    for row in rows:
        bucketed[row.region].append(row)
    for region in regions:
        bucketed[region].sort(key=_listing_sort_key)

    if region_targets is None:
        combined = [row for region in regions for row in bucketed[region]]
        return sorted(combined, key=_listing_sort_key)

    selected: list[_NormalizedListing] = []
    for region in regions:
        if region not in region_targets:
            raise PublicRecordRefreshError(f"Missing region target for {region}")

        target = region_targets[region]
        if target < 0:
            raise PublicRecordRefreshError(f"Region target must be >= 0 for {region}")

        candidates = bucketed[region]
        if len(candidates) < target:
            raise PublicRecordRefreshError(
                f"Region {region} has {len(candidates)} listings, below target {target}",
            )
        selected.extend(candidates)

    return sorted(selected, key=_listing_sort_key)


@dataclass(frozen=True)
class _LinkValidationResult:
    rows: list[_NormalizedListing]
    checked_url_count: int
    failures: list[LinkValidationFailure]
    dropped_record_ids: list[str]


def _validate_links(
    rows: Sequence[_NormalizedListing],
    link_checker: LinkChecker | None,
    drop_failed_links: bool,
) -> _LinkValidationResult:
    if link_checker is None:
        return _LinkValidationResult(
            rows=list(rows),
            checked_url_count=0,
            failures=[],
            dropped_record_ids=[],
        )

    url_cache: dict[str, LinkCheckResult] = {}
    checked_url_count = 0
    failures: list[LinkValidationFailure] = []
    failed_record_ids: set[str] = set()

    for row in rows:
        for field in LISTING_URL_FIELDS:
            field_value = getattr(row, field)
            if not field_value:
                continue

            check_result = url_cache.get(field_value)
            if check_result is None:
                check_result = link_checker(field_value)
                url_cache[field_value] = check_result
                checked_url_count += 1

            if not check_result.ok:
                failures.append(
                    LinkValidationFailure(
                        listing_id=row.id,
                        listing_name=row.name,
                        field=field,
                        url=field_value,
                        reason=check_result.reason or "unknown link validation failure",
                    )
                )
                failed_record_ids.add(row.id)

    if not drop_failed_links:
        return _LinkValidationResult(
            rows=list(rows),
            checked_url_count=checked_url_count,
            failures=failures,
            dropped_record_ids=[],
        )

    kept_rows = [row for row in rows if row.id not in failed_record_ids]
    return _LinkValidationResult(
        rows=kept_rows,
        checked_url_count=checked_url_count,
        failures=failures,
        dropped_record_ids=sorted(failed_record_ids),
    )


def _count_regions(rows: Sequence[_NormalizedListing], regions: Sequence[str]) -> dict[str, int]:
    region_counts = {region: 0 for region in regions}
    for row in rows:
        region_counts[row.region] += 1
    return region_counts


def _to_output_row(row: _NormalizedListing) -> PublicRecordRow:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "website": row.website,
        "description": row.description,
        "city": row.city,
        "state": row.state,
        "practice_tags": list(row.practice_tags),
        "source_label": row.source_label,
        "source_url": row.source_url,
    }


def _region_for_state(
    state: str,
    region_state_map: Mapping[str, frozenset[str]],
) -> str:
    for region, states in region_state_map.items():
        if state in states:
            return region
    raise PublicRecordRefreshError(f"State/country '{state}' does not map to any configured region")


def _normalize_practice_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PublicRecordRefreshError("practice_tags must be a list")

    tags: list[str] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, str):
            raise PublicRecordRefreshError("practice_tags entries must be strings")
        normalized = _normalize_string(entry)
        if not normalized:
            continue
        if normalized in seen:
            continue
        tags.append(normalized)
        seen.add(normalized)

    if not tags:
        raise PublicRecordRefreshError("practice_tags must contain at least one non-empty tag")
    return tuple(tags)


def _required_string(raw_row: Mapping[str, object], field_name: str) -> str:
    if field_name not in raw_row:
        raise PublicRecordRefreshError(f"Missing required field: {field_name}")

    field_value = raw_row[field_name]
    if not isinstance(field_value, str):
        raise PublicRecordRefreshError(f"Field '{field_name}' must be a string")

    normalized = _normalize_string(field_value)
    if not normalized:
        raise PublicRecordRefreshError(f"Field '{field_name}' cannot be empty")
    return normalized


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PublicRecordRefreshError("Optional string field must be a string or null")
    normalized = _normalize_string(value)
    return normalized or None


def _normalize_string(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _listing_sort_key(row: _NormalizedListing) -> tuple[str, str, str]:
    return (_sort_key(row.id), _sort_key(row.slug), _sort_key(row.name))


def _sort_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    return unidecode(normalized).casefold()


def _slug_base(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    transliterated = unidecode(normalized).casefold()
    slug_base = _SLUG_SANITIZE_RE.sub("-", transliterated).strip("-")
    if not slug_base:
        raise PublicRecordRefreshError(f"Unable to derive slug from value: {value!r}")
    return slug_base

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, TypedDict

import requests
from unidecode import unidecode

LISTING_URL_FIELDS: tuple[str, str] = ("website", "source_url")

CHAMBERS_PUBLICATION_GROUP_BY_REGION: dict[str, int] = {
    "US": 5,
    "EU": 7,
    "APAC": 8,
}

CHAMBERS_SOURCE_LABEL = "Chambers and Partners ranked law firm profile"

_CHAMBERS_INDEX_URL_TEMPLATE = (
    "https://chamberssitemap.blob.core.windows.net/site-json/organisations/ranked/{group_id}"
)
_CHAMBERS_PROFILE_BASICS_URL_TEMPLATE = (
    "https://profiles-portal.chambers.com/api/organisations/{organisation_id}/profile-basics"
    "?groupId={group_id}"
)
_CHAMBERS_RANKED_OFFICES_URL_TEMPLATE = (
    "https://profiles-portal.chambers.com/api/organisations/{organisation_id}/ranked-offices"
    "?groupId={group_id}"
)
_CHAMBERS_RANKED_DEPARTMENTS_URL_TEMPLATE = (
    "https://ranking-tables.chambers.com/api/organisations/{organisation_id}/ranked-departments"
    "?groupId={group_id}"
)

_CHAMBERS_ORGANISATION_TYPE_LAW_FIRM = 1

_DEFAULT_DISCOVERED_PRACTICE_TAGS: tuple[str, ...] = (
    "Whistleblowing",
    "Investigations",
    "Employment",
)

_DEFAULT_CHAMBERS_MAX_NEW_PER_REGION = 10

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

_US_REGION_TO_STATE_CODE: dict[str, str] = {
    "california": "CA",
    "district of columbia": "DC",
    "maryland": "MD",
    "massachusetts": "MA",
    "new york": "NY",
    "pennsylvania": "PA",
    "washington": "WA",
}

_US_COUNTRY_ALIASES = frozenset({"united states", "united states of america", "usa", "us"})

_COUNTRY_ALIASES: dict[str, str] = {
    "republic of singapore": "Singapore",
    "the netherlands": "Netherlands",
    "u.s.a.": "USA",
    "united states of america": "USA",
}

_PRACTICE_KEYWORD_TAG_MAP: tuple[tuple[str, str], ...] = (
    ("whistle", "Whistleblowing"),
    ("investigat", "Investigations"),
    ("white collar", "White Collar"),
    ("employment", "Employment"),
    ("labor", "Employment"),
    ("compliance", "Compliance"),
    ("regulator", "Regulatory"),
    ("fraud", "Fraud"),
    ("litigation", "Litigation"),
    ("disput", "Disputes"),
)

_HTTP_OK_STATUS = 200
_DISCOVERED_TAG_LIMIT = 3
_TWO_TAG_COUNT = 2


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


@dataclass(frozen=True)
class ChambersDiscoveryResult:
    rows: list[PublicRecordRow]
    scanned_count_by_region: dict[str, int]
    added_count_by_region: dict[str, int]


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


def discover_chambers_public_record_rows(  # noqa: PLR0913
    existing_rows: Sequence[Mapping[str, object]],
    *,
    selected_regions: Sequence[str] | None = None,
    region_state_map: Mapping[str, frozenset[str]] = DEFAULT_REGION_STATE_MAP,
    publication_group_by_region: Mapping[str, int] = CHAMBERS_PUBLICATION_GROUP_BY_REGION,
    max_new_per_region: int = _DEFAULT_CHAMBERS_MAX_NEW_PER_REGION,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> ChambersDiscoveryResult:
    if timeout_seconds <= 0:
        raise PublicRecordRefreshError("Discovery timeout_seconds must be > 0")
    if max_new_per_region < 0:
        raise PublicRecordRefreshError("max_new_per_region must be >= 0")

    regions = tuple(selected_regions or DEFAULT_REGION_TARGETS.keys())
    _validate_regions(regions, region_state_map)

    request_session = session or requests.Session()
    request_session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; HushlinePublicRecordDiscovery/1.0; "
                "+https://github.com/scidsg/hushline)"
            )
        }
    )

    existing_name_keys: set[str] = set()
    existing_slug_bases: set[str] = set()
    for row in existing_rows:
        raw_name = row.get("name")
        if not isinstance(raw_name, str):
            continue
        name = _normalize_string(raw_name)
        if not name:
            continue
        existing_name_keys.add(_sort_key(name))
        try:
            existing_slug_bases.add(_slug_base(name))
        except PublicRecordRefreshError:
            continue

    discovered_rows: list[PublicRecordRow] = []
    scanned_count_by_region: dict[str, int] = {region: 0 for region in regions}
    added_count_by_region: dict[str, int] = {region: 0 for region in regions}

    for region in regions:
        if max_new_per_region == 0:
            continue

        group_id = publication_group_by_region.get(region)
        if group_id is None:
            raise PublicRecordRefreshError(
                f"Missing Chambers publication group for region: {region}",
            )

        index_url = _CHAMBERS_INDEX_URL_TEMPLATE.format(group_id=group_id)
        index_payload = _fetch_json_payload(
            request_session,
            index_url,
            timeout_seconds=timeout_seconds,
        )
        entries = _parse_chambers_index_entries(index_payload, default_group_id=group_id)

        for entry in entries:
            if added_count_by_region[region] >= max_new_per_region:
                break
            scanned_count_by_region[region] += 1

            name_key = _sort_key(entry.name)
            try:
                slug_base = _slug_base(entry.name)
            except PublicRecordRefreshError:
                continue
            if name_key in existing_name_keys or slug_base in existing_slug_bases:
                continue

            profile_url = _CHAMBERS_PROFILE_BASICS_URL_TEMPLATE.format(
                organisation_id=entry.organisation_id,
                group_id=entry.group_id,
            )
            profile_payload = _fetch_json_payload(
                request_session,
                profile_url,
                timeout_seconds=timeout_seconds,
            )
            if not isinstance(profile_payload, dict):
                continue

            if (
                _coerce_int(profile_payload.get("organisationTypeId"))
                != _CHAMBERS_ORGANISATION_TYPE_LAW_FIRM
            ):
                continue

            offices_url = _CHAMBERS_RANKED_OFFICES_URL_TEMPLATE.format(
                organisation_id=entry.organisation_id,
                group_id=entry.group_id,
            )
            offices_payload = _fetch_json_payload(
                request_session,
                offices_url,
                timeout_seconds=timeout_seconds,
            )
            if not isinstance(offices_payload, dict):
                continue

            location = _pick_discovered_location(
                offices_payload,
                region=region,
                allowed_states=region_state_map[region],
            )
            if location is None:
                continue

            website = _normalize_discovered_website(profile_payload.get("webLink"))
            if website is None:
                website = _normalize_discovered_website(
                    _first_office_field(offices_payload, "webLink")
                )
            if website is None:
                continue

            city, state = location
            practice_tags = _discover_practice_tags(
                request_session,
                organisation_id=entry.organisation_id,
                group_id=entry.group_id,
                timeout_seconds=timeout_seconds,
            )

            discovered_rows.append(
                {
                    "id": f"seed-{slug_base}",
                    "slug": f"{_PUBLIC_RECORD_SLUG_PREFIX}{slug_base}",
                    "name": entry.name,
                    "website": website,
                    "description": _discovered_description(city, state, practice_tags),
                    "city": city,
                    "state": state,
                    "practice_tags": list(practice_tags),
                    "source_label": CHAMBERS_SOURCE_LABEL,
                    "source_url": profile_url,
                }
            )

            existing_name_keys.add(name_key)
            existing_slug_bases.add(slug_base)
            added_count_by_region[region] += 1

    return ChambersDiscoveryResult(
        rows=discovered_rows,
        scanned_count_by_region=scanned_count_by_region,
        added_count_by_region=added_count_by_region,
    )


@dataclass(frozen=True)
class _ChambersIndexEntry:
    organisation_id: int
    name: str
    group_id: int


def _parse_chambers_index_entries(
    payload: object,
    *,
    default_group_id: int,
) -> list[_ChambersIndexEntry]:
    if not isinstance(payload, list):
        return []

    entries: list[_ChambersIndexEntry] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        organisation_id = _coerce_int(item.get("oid"))
        name = _normalize_discovered_text(item.get("on"))
        if organisation_id is None or name is None:
            continue
        group_id = _coerce_int(item.get("ptgid")) or default_group_id
        entries.append(
            _ChambersIndexEntry(
                organisation_id=organisation_id,
                name=name,
                group_id=group_id,
            )
        )

    entries.sort(key=lambda entry: (_sort_key(entry.name), entry.organisation_id))
    return entries


def _fetch_json_payload(
    session: requests.Session,
    url: str,
    *,
    timeout_seconds: float,
) -> object | None:
    response: requests.Response | None = None
    try:
        response = session.get(
            url,
            allow_redirects=True,
            timeout=timeout_seconds,
            stream=True,
        )
        if response.status_code != _HTTP_OK_STATUS:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None
    finally:
        if response is not None:
            response.close()


def _normalize_discovered_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize_string(value)
    return normalized or None


def _normalize_discovered_website(value: object) -> str | None:
    raw = _normalize_discovered_text(value)
    if raw is None:
        return None
    if raw.casefold().startswith(("http://", "https://")):
        return raw
    if raw.casefold().startswith("www."):
        return f"https://{raw}"
    return f"https://{raw}"


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.isdigit():
            return int(trimmed)
    return None


def _pick_discovered_location(
    ranked_offices_payload: Mapping[str, object],
    *,
    region: str,
    allowed_states: frozenset[str],
) -> tuple[str, str] | None:
    office_candidates = list(_iter_office_candidates(ranked_offices_payload))
    if not office_candidates:
        return None

    matches: list[tuple[str, str]] = []
    for office in office_candidates:
        country = _canonical_country(office.get("country"))
        town = _normalize_discovered_text(office.get("town"))
        if region == "US":
            if country is None or country.casefold() not in _US_COUNTRY_ALIASES:
                continue
            state_code = _us_state_code_for_office(office)
            if state_code is None or state_code not in allowed_states:
                continue
            matches.append((state_code, town or state_code))
            continue

        if country is None:
            continue
        if country not in allowed_states:
            continue
        matches.append((country, town or country))

    if not matches:
        return None

    matches.sort(key=lambda match: (_sort_key(match[0]), _sort_key(match[1])))
    state, city = matches[0]
    return city, state


def _iter_office_candidates(
    ranked_offices_payload: Mapping[str, object],
) -> Sequence[Mapping[str, object]]:
    offices: list[Mapping[str, object]] = []

    head_office = ranked_offices_payload.get("headOffice")
    if isinstance(head_office, dict):
        offices.append({str(key): value for key, value in head_office.items()})

    locations = ranked_offices_payload.get("locations")
    if not isinstance(locations, list):
        return offices

    for location in locations:
        if not isinstance(location, dict):
            continue
        location_country = location.get("country")
        location_offices = location.get("offices")
        if not isinstance(location_offices, list):
            continue
        for office in location_offices:
            if not isinstance(office, dict):
                continue
            normalized = {str(key): value for key, value in office.items()}
            if normalized.get("country") in (None, "") and location_country is not None:
                normalized["country"] = location_country
            offices.append(normalized)

    return offices


def _canonical_country(value: object) -> str | None:
    country = _normalize_discovered_text(value)
    if country is None:
        return None
    alias = _COUNTRY_ALIASES.get(country.casefold())
    if alias is not None:
        return alias
    if country.casefold() in _US_COUNTRY_ALIASES:
        return "USA"
    return country


def _us_state_code_for_office(office: Mapping[str, object]) -> str | None:
    region = _normalize_discovered_text(office.get("region"))
    if region is not None:
        region_upper = region.upper()
        if region_upper in _US_REGION_TO_STATE_CODE.values():
            return region_upper
        region_code = _US_REGION_TO_STATE_CODE.get(region.casefold())
        if region_code is not None:
            return region_code

    address = _normalize_discovered_text(office.get("address"))
    if address is None:
        return None
    match = re.search(r"\b(DC|NY|PA|CA|MD|WA|MA)\b", address.upper())
    if match is None:
        return None
    return match.group(1)


def _first_office_field(
    ranked_offices_payload: Mapping[str, object],
    field_name: str,
) -> object:
    for office in _iter_office_candidates(ranked_offices_payload):
        if field_name in office:
            return office[field_name]
    return None


def _discover_practice_tags(
    session: requests.Session,
    *,
    organisation_id: int,
    group_id: int,
    timeout_seconds: float,
) -> tuple[str, ...]:
    ranked_departments_url = _CHAMBERS_RANKED_DEPARTMENTS_URL_TEMPLATE.format(
        organisation_id=organisation_id,
        group_id=group_id,
    )
    payload = _fetch_json_payload(
        session,
        ranked_departments_url,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(payload, list):
        return _DEFAULT_DISCOVERED_PRACTICE_TAGS

    tags: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate_names = [item.get("practiceAreaName"), item.get("displayName")]
        for candidate in candidate_names:
            value = _normalize_discovered_text(candidate)
            if value is None:
                continue
            normalized = value.casefold()
            for keyword, tag in _PRACTICE_KEYWORD_TAG_MAP:
                if keyword in normalized and tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
                    if len(tags) >= _DISCOVERED_TAG_LIMIT:
                        return tuple(tags)

    if not tags:
        return _DEFAULT_DISCOVERED_PRACTICE_TAGS
    return tuple(tags)


def _discovered_description(city: str, state: str, practice_tags: Sequence[str]) -> str:
    tags = [tag for tag in practice_tags if _normalize_discovered_text(tag)]
    if tags:
        if len(tags) == 1:
            tag_phrase = tags[0]
        elif len(tags) == _TWO_TAG_COUNT:
            tag_phrase = f"{tags[0]} and {tags[1]}"
        else:
            tag_phrase = f"{tags[0]}, {tags[1]}, and {tags[2]}"
        return (
            f"A Chambers-ranked law firm with a public profile in {city}, {state}, "
            f"covering {tag_phrase} matters."
        )
    return f"A Chambers-ranked law firm with a public profile in {city}, {state}."


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

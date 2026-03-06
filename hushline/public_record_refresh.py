from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence, TypedDict
from urllib.parse import parse_qsl, urlparse

import requests
from unidecode import unidecode

LISTING_URL_FIELDS: tuple[str, str] = ("website", "source_url")

CHAMBERS_PUBLICATION_GROUP_BY_REGION: dict[str, int] = {
    "US": 5,
    "EU": 7,
    "APAC": 8,
}

CHAMBERS_SOURCE_LABEL = "Chambers and Partners ranked law firm profile"
LEGACY_SELF_REPORTED_SOURCE_LABEL = "Seed dataset from official firm website"
CHAMBERS_GROUP_SLUG_BY_ID: dict[int, str] = {
    5: "usa",
    7: "europe",
    8: "asia-pacific",
}

_CHAMBERS_INDEX_URL_TEMPLATE = (
    "https://chamberssitemap.blob.core.windows.net/site-json/organisations/ranked/{group_id}"
)
_CHAMBERS_PUBLIC_PROFILE_URL_TEMPLATE = (
    "https://chambers.com/law-firm/{slug_base}-{group_slug}-{group_id}:{organisation_id}"
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

US_STATE_CODES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    },
)


class USStateAuthoritativeSource(TypedDict):
    source_label: str
    source_url: str
    allowed_domains: frozenset[str]


US_STATE_AUTHORITATIVE_SOURCES: dict[str, USStateAuthoritativeSource] = {
    "AL": {
        "source_label": "Alabama State Bar public directory",
        "source_url": "https://www.alabar.org/",
        "allowed_domains": frozenset({"alabar.org"}),
    },
    "AK": {
        "source_label": "Alaska Bar Association public directory",
        "source_url": "https://alaskabar.org/",
        "allowed_domains": frozenset({"alaskabar.org"}),
    },
    "AZ": {
        "source_label": "State Bar of Arizona public directory",
        "source_url": "https://www.azbar.org/",
        "allowed_domains": frozenset({"azbar.org"}),
    },
    "AR": {
        "source_label": "Arkansas Bar Association public directory",
        "source_url": "https://www.arkbar.com/",
        "allowed_domains": frozenset({"arkbar.com"}),
    },
    "CA": {
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/LicenseeSearch/QuickSearch",
        "allowed_domains": frozenset({"calbar.ca.gov"}),
    },
    "CO": {
        "source_label": "Colorado Bar Association public directory",
        "source_url": "https://www.cobar.org/",
        "allowed_domains": frozenset({"cobar.org"}),
    },
    "CT": {
        "source_label": "Connecticut Bar Association public directory",
        "source_url": "https://www.ctbar.org/",
        "allowed_domains": frozenset({"ctbar.org"}),
    },
    "DE": {
        "source_label": "Delaware Courts attorney regulation records",
        "source_url": "https://courts.delaware.gov/odc/",
        "allowed_domains": frozenset({"courts.delaware.gov"}),
    },
    "FL": {
        "source_label": "The Florida Bar public directory",
        "source_url": "https://www.floridabar.org/directories/find-mbr/",
        "allowed_domains": frozenset({"floridabar.org"}),
    },
    "GA": {
        "source_label": "State Bar of Georgia public directory",
        "source_url": "https://www.gabar.org/",
        "allowed_domains": frozenset({"gabar.org"}),
    },
    "HI": {
        "source_label": "Hawaii State Bar Association public directory",
        "source_url": "https://hsba.org/",
        "allowed_domains": frozenset({"hsba.org"}),
    },
    "ID": {
        "source_label": "Idaho State Bar public directory",
        "source_url": "https://isb.idaho.gov/lawyer-referral-service/",
        "allowed_domains": frozenset({"isb.idaho.gov"}),
    },
    "IL": {
        "source_label": "Illinois ARDC attorney registration records",
        "source_url": "https://www.iardc.org/Lawyer/Search",
        "allowed_domains": frozenset({"iardc.org"}),
    },
    "IN": {
        "source_label": "Indiana State Bar public directory",
        "source_url": "https://www.inbar.org/page/for-the-public",
        "allowed_domains": frozenset({"inbar.org"}),
    },
    "IA": {
        "source_label": "Iowa State Bar Association public directory",
        "source_url": "https://www.iowabar.org/?pg=Find-A-LawyerHP",
        "allowed_domains": frozenset({"iowabar.org"}),
    },
    "KS": {
        "source_label": "Kansas Judicial Branch attorney records",
        "source_url": "https://www.kscourts.gov/Attorneys/Attorney-Registration",
        "allowed_domains": frozenset({"kscourts.gov"}),
    },
    "KY": {
        "source_label": "Kentucky Bar Association public directory",
        "source_url": "https://www.kybar.org/",
        "allowed_domains": frozenset({"kybar.org"}),
    },
    "LA": {
        "source_label": "Louisiana Attorney Disciplinary Board attorney records",
        "source_url": "https://www.ladb.org/",
        "allowed_domains": frozenset({"ladb.org"}),
    },
    "ME": {
        "source_label": "Maine Board of Overseers of the Bar public directory",
        "source_url": "https://www.mainebar.org/member-directory/",
        "allowed_domains": frozenset({"mainebar.org"}),
    },
    "MD": {
        "source_label": "Maryland Courts attorney discipline records",
        "source_url": "https://www.courts.state.md.us/attygrievance/sanctions",
        "allowed_domains": frozenset({"courts.state.md.us"}),
    },
    "MA": {
        "source_label": "Massachusetts BBO attorney records",
        "source_url": "https://www.massbbo.org/",
        "allowed_domains": frozenset({"massbbo.org"}),
    },
    "MI": {
        "source_label": "State Bar of Michigan public directory",
        "source_url": "https://www.michbar.org/memberdirectory",
        "allowed_domains": frozenset({"michbar.org"}),
    },
    "MN": {
        "source_label": "Minnesota Courts attorney records",
        "source_url": "https://lprb.mncourts.gov/",
        "allowed_domains": frozenset({"mncourts.gov"}),
    },
    "MS": {
        "source_label": "The Mississippi Bar public directory",
        "source_url": "https://www.msbar.org/for-the-public/find-an-attorney/",
        "allowed_domains": frozenset({"msbar.org"}),
    },
    "MO": {
        "source_label": "The Missouri Bar public directory",
        "source_url": "https://mobar.org/site/content/Public/Find_a_Lawyer.aspx",
        "allowed_domains": frozenset({"mobar.org"}),
    },
    "MT": {
        "source_label": "State Bar of Montana public directory",
        "source_url": "https://www.montanabar.org/members/member_directory.asp",
        "allowed_domains": frozenset({"montanabar.org"}),
    },
    "NE": {
        "source_label": "Nebraska Judicial Branch attorney directory",
        "source_url": "https://supremecourt.nebraska.gov/",
        "allowed_domains": frozenset({"supremecourt.nebraska.gov"}),
    },
    "NV": {
        "source_label": "State Bar of Nevada public directory",
        "source_url": "https://nvbar.org/for-the-public/find-a-lawyer/",
        "allowed_domains": frozenset({"nvbar.org"}),
    },
    "NH": {
        "source_label": "New Hampshire Bar Association public directory",
        "source_url": "https://www.nhbar.org/",
        "allowed_domains": frozenset({"nhbar.org"}),
    },
    "NJ": {
        "source_label": "New Jersey Courts attorney directory",
        "source_url": "https://portal.njcourts.gov/webe4/AttorneySearch/",
        "allowed_domains": frozenset({"njcourts.gov"}),
    },
    "NM": {
        "source_label": "State Bar of New Mexico public directory",
        "source_url": "https://www.sbnm.org/cvweb/cgi-bin/utilities.dll/openpage?wrp=membersearch.htm",
        "allowed_domains": frozenset({"sbnm.org"}),
    },
    "NY": {
        "source_label": "New York Courts attorney directory",
        "source_url": "https://iapps.courts.state.ny.us/attorneyservices/search?0",
        "allowed_domains": frozenset({"courts.state.ny.us"}),
    },
    "NC": {
        "source_label": "North Carolina State Bar public directory",
        "source_url": "https://portal.ncbar.gov/verification/search.aspx",
        "allowed_domains": frozenset({"ncbar.gov"}),
    },
    "ND": {
        "source_label": "State Bar Association of North Dakota public directory",
        "source_url": "https://www.sband.org/page/LawyerSearch",
        "allowed_domains": frozenset({"sband.org"}),
    },
    "OH": {
        "source_label": "Supreme Court of Ohio attorney directory",
        "source_url": "https://www.supremecourt.ohio.gov/AttorneySearch/#/home",
        "allowed_domains": frozenset({"supremecourt.ohio.gov"}),
    },
    "OK": {
        "source_label": "Oklahoma Bar Association public directory",
        "source_url": "https://ams.okbar.org/eweb/startpage.aspx?site=FAL",
        "allowed_domains": frozenset({"okbar.org"}),
    },
    "OR": {
        "source_label": "Oregon State Bar public directory",
        "source_url": "https://www.osbar.org/members/membersearch_display.asp",
        "allowed_domains": frozenset({"osbar.org"}),
    },
    "PA": {
        "source_label": "Pennsylvania Disciplinary Board attorney directory",
        "source_url": "https://www.padisciplinaryboard.org/for-the-public/find-attorney",
        "allowed_domains": frozenset({"padisciplinaryboard.org"}),
    },
    "RI": {
        "source_label": "Rhode Island Judiciary attorney records",
        "source_url": "https://www.courts.ri.gov/",
        "allowed_domains": frozenset({"courts.ri.gov"}),
    },
    "SC": {
        "source_label": "South Carolina Bar public directory",
        "source_url": "https://www.scbar.org/public/get-legal-help/find-lawyer-or-mediator/find-a-lawyer/",
        "allowed_domains": frozenset({"scbar.org"}),
    },
    "SD": {
        "source_label": "State Bar of South Dakota public directory",
        "source_url": "https://www.statebarofsouthdakota.com/",
        "allowed_domains": frozenset({"statebarofsouthdakota.com"}),
    },
    "TN": {
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/",
        "allowed_domains": frozenset({"tbpr.org"}),
    },
    "TX": {
        "source_label": "State Bar of Texas public directory",
        "source_url": "https://www.texasbar.com/AM/Template.cfm?Section=Find_A_Lawyer",
        "allowed_domains": frozenset({"texasbar.com"}),
    },
    "UT": {
        "source_label": "Utah Courts public legal directory",
        "source_url": "https://www.utcourts.gov/",
        "allowed_domains": frozenset({"utcourts.gov"}),
    },
    "VT": {
        "source_label": "Vermont Bar Association public directory",
        "source_url": "https://www.vtbar.org/find-a-lawyer/",
        "allowed_domains": frozenset({"vtbar.org"}),
    },
    "VA": {
        "source_label": "Virginia State Bar public directory",
        "source_url": "https://www.vsb.org/Site/Site/legal-help/vlrs.aspx",
        "allowed_domains": frozenset({"vsb.org"}),
    },
    "WA": {
        "source_label": "Washington State Bar Association legal directory",
        "source_url": "https://www.mywsba.org/PersonifyEbusiness/LegalDirectory.aspx",
        "allowed_domains": frozenset({"mywsba.org", "wsba.org"}),
    },
    "WV": {
        "source_label": "West Virginia State Bar public directory",
        "source_url": "https://wvbar.org/",
        "allowed_domains": frozenset({"wvbar.org"}),
    },
    "WI": {
        "source_label": "State Bar of Wisconsin public directory",
        "source_url": "https://www.wisbar.org/",
        "allowed_domains": frozenset({"wisbar.org"}),
    },
    "WY": {
        "source_label": "Wyoming State Bar public directory",
        "source_url": "https://www.wyomingbar.org/",
        "allowed_domains": frozenset({"wyomingbar.org"}),
    },
}

DEFAULT_REGION_STATE_MAP: dict[str, frozenset[str]] = {
    "US": US_STATE_CODES,
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

DEFAULT_REGION_TARGETS: dict[str, int] = {"US": 0, "EU": 0, "APAC": 0}

_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_BROKEN_STATUS_CODES = frozenset({404, 410})
_HTTP_SERVER_ERROR_MIN_STATUS = 500
_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_MAX_ATTEMPTS = 3
_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_PUBLIC_RECORD_SLUG_PREFIX = "public-record~"
_CHAMBERS_PROFILE_BASICS_SOURCE_URL_RE = re.compile(
    r"^https?://profiles-portal\.chambers\.com/api/organisations/"
    r"(?P<organisation_id>\d+)/profile-basics\?groupId=(?P<group_id>\d+)$",
)
_OHIO_ATTORNEY_PROFILE_FRAGMENT_RE = re.compile(r"^/?\d+/attyinfo/?$", re.IGNORECASE)

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


@dataclass(frozen=True)
class OfficialStateDiscoveryResult:
    rows: list[PublicRecordRow]
    added_count_by_state: dict[str, int]
    unsupported_states: tuple[str, ...]


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
OfficialStateDiscoveryAdapter = Callable[..., list[PublicRecordRow]]


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


_CALIFORNIA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-jeffrey-farley-keller",
        "slug": "public-record~jeffrey-farley-keller",
        "name": "Jeffrey Farley Keller",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/148005",
    },
    {
        "id": "seed-eric-andrew-grover",
        "slug": "public-record~eric-andrew-grover",
        "name": "Eric Andrew Grover",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/136080",
    },
    {
        "id": "seed-kathleen-ruth-scanlan",
        "slug": "public-record~kathleen-ruth-scanlan",
        "name": "Kathleen Ruth Scanlan",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/197529",
    },
    {
        "id": "seed-sarah-renee-holloway",
        "slug": "public-record~sarah-renee-holloway",
        "name": "Sarah Renee Holloway",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/254134",
    },
    {
        "id": "seed-elizabeth-aida-acevedo",
        "slug": "public-record~elizabeth-aida-acevedo",
        "name": "Elizabeth Aida Acevedo",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/227347",
    },
    {
        "id": "seed-robert-william-spencer",
        "slug": "public-record~robert-william-spencer",
        "name": "Robert William Spencer",
        "website": "https://www.kellergrover.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/238491",
    },
    {
        "id": "seed-cara-whittaker-van-dorn",
        "slug": "public-record~cara-whittaker-van-dorn",
        "name": "Cara Whittaker Van Dorn",
        "website": "https://sanfordheisler.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "La Jolla",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/321669",
    },
    {
        "id": "seed-christine-m-salazar",
        "slug": "public-record~christine-m-salazar",
        "name": "Christine M Salazar",
        "website": "https://sanfordheisler.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "Palo Alto",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/330468",
    },
    {
        "id": "seed-daniel-noel",
        "slug": "public-record~daniel-noel",
        "name": "Daniel Noel",
        "website": "https://constantinecannon.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of California "
            "attorney records."
        ),
        "city": "San Francisco",
        "state": "CA",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "State Bar of California attorney profile",
        "source_url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/339078",
    },
)


_ALASKA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-jon-marc-petersen",
        "slug": "public-record~jon-marc-petersen",
        "name": "Jon-Marc Petersen",
        "website": "https://www.denalilaw.com/",
        "description": (
            "Whistleblower attorney listing sourced from Alaska Bar Association "
            "public directory."
        ),
        "city": "Wasilla",
        "state": "AK",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "Alaska Bar Association public directory",
        "source_url": (
            "https://member.alaskabar.org/cv5/cgi-bin/memberdll.dll/Info"
            "?CUSTOMERCD=8744&WRP=Customer_Profile.htm"
        ),
    },
)


_ALABAMA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-marc-james-ayers",
        "slug": "public-record~marc-james-ayers",
        "name": "Marc James Ayers",
        "website": "https://www.bradley.com/",
        "description": (
            "Whistleblower attorney listing sourced from Alabama State Bar public " "directory."
        ),
        "city": "Birmingham",
        "state": "AL",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "Alabama State Bar public directory",
        "source_url": "https://members.alabar.org/Member_Portal/Member_Portal/Sections/AP.aspx",
    },
)


_ARKANSAS_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-kristin-l-pawlik",
        "slug": "public-record~kristin-l-pawlik",
        "name": "Kristin L. Pawlik",
        "website": "https://www.arkattorneys.com/",
        "description": (
            "Whistleblower attorney listing sourced from Arkansas Bar Association "
            "public directory."
        ),
        "city": "Fayetteville",
        "state": "AR",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "Arkansas Bar Association public directory",
        "source_url": (
            "https://www.arkbar.com/network/members/profile"
            "?UserKey=10e2c501-bea8-4749-913c-0d6e319cdff6"
        ),
    },
)


_ARIZONA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-anthony-cali",
        "slug": "public-record~anthony-cali",
        "name": "Anthony Cali",
        "website": "https://www.stinson.com/",
        "description": (
            "Whistleblower attorney listing sourced from State Bar of Arizona public " "directory."
        ),
        "city": "Phoenix",
        "state": "AZ",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "State Bar of Arizona public directory",
        "source_url": (
            "https://www.azbar.org/for-the-public/find-a-lawyer-results/" "?m=Anthony-Cali-177781"
        ),
    },
)


_COLORADO_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-rachel-brock",
        "slug": "public-record~rachel-brock",
        "name": "Rachel Brock",
        "website": "https://www.durangofamilylaw.com/",
        "description": (
            "Whistleblower attorney listing sourced from Colorado Bar Association "
            "public directory."
        ),
        "city": "Durango",
        "state": "CO",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "Colorado Bar Association public directory",
        "source_url": (
            "https://community.cobar.org/profile/contributions/"
            "contributions-achievements"
            "?UserKey=330f70ad-afc9-44f0-b8b1-6b55108bc275"
        ),
    },
)


_WASHINGTON_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-barbara-mahoney",
        "slug": "public-record~barbara-mahoney",
        "name": "Barbara Mahoney",
        "website": "https://www.hbsslaw.com/",
        "description": (
            "Whistleblower attorney listing sourced from Washington State Bar "
            "Association legal directory."
        ),
        "city": "Seattle",
        "state": "WA",
        "practice_tags": ["Whistleblowing", "Employment", "Consumer"],
        "source_label": "Washington State Bar Association legal directory",
        "source_url": "https://www.mywsba.org/PersonifyEbusiness/Default.aspx?TabID=1538&Usr_ID=31845",
    },
)


_ILLINOIS_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-adam-j-levitt",
        "slug": "public-record~adam-j-levitt",
        "name": "Adam J. Levitt",
        "website": "https://dicellolevitt.com/",
        "description": (
            "Whistleblower attorney listing sourced from Illinois ARDC attorney "
            "registration records."
        ),
        "city": "Chicago",
        "state": "IL",
        "practice_tags": ["Whistleblowing", "Investigations", "Consumer"],
        "source_label": "Illinois ARDC attorney registration records",
        "source_url": (
            "https://www.iardc.org/Lawyer/PrintableDetails/"
            "a1420f47-ab64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
        ),
    },
    {
        "id": "seed-daniel-richard-ferri",
        "slug": "public-record~daniel-richard-ferri",
        "name": "Daniel Richard Ferri",
        "website": "https://dicellolevitt.com/",
        "description": (
            "Whistleblower attorney listing sourced from Illinois ARDC attorney "
            "registration records."
        ),
        "city": "Chicago",
        "state": "IL",
        "practice_tags": ["Whistleblowing", "Investigations", "Consumer"],
        "source_label": "Illinois ARDC attorney registration records",
        "source_url": (
            "https://www.iardc.org/Lawyer/PrintableDetails/"
            "4b9c1c91-a964-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
        ),
    },
    {
        "id": "seed-douglas-michael-werman",
        "slug": "public-record~douglas-michael-werman",
        "name": "Douglas Michael Werman",
        "website": "https://flsalaw.com/",
        "description": (
            "Whistleblower attorney listing sourced from Illinois ARDC attorney "
            "registration records."
        ),
        "city": "Chicago",
        "state": "IL",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Illinois ARDC attorney registration records",
        "source_url": (
            "https://www.iardc.org/Lawyer/PrintableDetails/"
            "00034ffd-aa64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
        ),
    },
    {
        "id": "seed-amy-elisabeth-keller",
        "slug": "public-record~amy-elisabeth-keller",
        "name": "Amy Elisabeth Keller",
        "website": "https://dicellolevitt.com/",
        "description": (
            "Whistleblower attorney listing sourced from Illinois ARDC attorney "
            "registration records."
        ),
        "city": "Chicago",
        "state": "IL",
        "practice_tags": ["Whistleblowing", "Investigations", "Consumer"],
        "source_label": "Illinois ARDC attorney registration records",
        "source_url": (
            "https://www.iardc.org/Lawyer/PrintableDetails/"
            "f22e492e-aa64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
        ),
    },
)


_OHIO_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-alissa-jacqueline-sammarco",
        "slug": "public-record~alissa-jacqueline-sammarco",
        "name": "Alissa Jacqueline Sammarco",
        "website": "https://www.sammarcolegal.com/",
        "description": (
            "Whistleblower attorney listing sourced from Supreme Court of Ohio "
            "attorney directory."
        ),
        "city": "Cincinnati",
        "state": "OH",
        "practice_tags": ["Whistleblowing", "Investigations", "Litigation"],
        "source_label": "Supreme Court of Ohio attorney directory",
        "source_url": "https://www.supremecourt.ohio.gov/AttorneySearch/#/77563/attyinfo",
    },
)


_TENNESSEE_OFFICIAL_PUBLIC_RECORD_SEED_ROWS: tuple[PublicRecordRow, ...] = (
    {
        "id": "seed-kevin-hunter-sharp",
        "slug": "public-record~kevin-hunter-sharp",
        "name": "Kevin Hunter Sharp",
        "website": "https://sanfordheisler.com/team/judge-kevin-sharp/",
        "description": (
            "Whistleblower attorney listing sourced from Tennessee Board of "
            "Professional Responsibility attorney records."
        ),
        "city": "Nashville",
        "state": "TN",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/attorneys/016287",
    },
    {
        "id": "seed-jonathan-patrick-tepe",
        "slug": "public-record~jonathan-patrick-tepe",
        "name": "Jonathan Patrick Tepe",
        "website": "https://sanfordheisler.com/team/jonathan-tepe/",
        "description": (
            "Whistleblower attorney listing sourced from Tennessee Board of "
            "Professional Responsibility attorney records."
        ),
        "city": "Nashville",
        "state": "TN",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/attorneys/037266",
    },
    {
        "id": "seed-michael-joseph-lockman",
        "slug": "public-record~michael-joseph-lockman",
        "name": "Michael Joseph Lockman",
        "website": "https://sanfordheisler.com/team/michael-lockman/",
        "description": (
            "Whistleblower attorney listing sourced from Tennessee Board of "
            "Professional Responsibility attorney records."
        ),
        "city": "Nashville",
        "state": "TN",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/attorneys/039797",
    },
    {
        "id": "seed-kasi-lynn-wautlet",
        "slug": "public-record~kasi-lynn-wautlet",
        "name": "Kasi Lynn Wautlet",
        "website": "https://sanfordheisler.com/team/kasi-wautlet/",
        "description": (
            "Whistleblower attorney listing sourced from Tennessee Board of "
            "Professional Responsibility attorney records."
        ),
        "city": "Nashville",
        "state": "TN",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/attorneys/038688",
    },
    {
        "id": "seed-david-bragg-mcnamee",
        "slug": "public-record~david-bragg-mcnamee",
        "name": "David Bragg McNamee",
        "website": "https://sanfordheisler.com/team/david-mcnamee/",
        "description": (
            "Whistleblower attorney listing sourced from Tennessee Board of "
            "Professional Responsibility attorney records."
        ),
        "city": "Nashville",
        "state": "TN",
        "practice_tags": ["Whistleblowing", "Employment", "Litigation"],
        "source_label": "Tennessee Board of Professional Responsibility attorney records",
        "source_url": "https://www.tbpr.org/attorneys/038124",
    },
)


def _discover_seed_rows(
    *,
    seed_rows: Sequence[PublicRecordRow],
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
) -> list[PublicRecordRow]:
    if max_new_per_state == 0:
        return []

    existing_ids: set[str] = set()
    existing_slugs: set[str] = set()
    existing_name_keys: set[str] = set()
    for row in existing_rows:
        row_id = _optional_string(row.get("id"))
        row_slug = _optional_string(row.get("slug"))
        row_name = _optional_string(row.get("name"))
        if row_id is not None:
            existing_ids.add(row_id)
        if row_slug is not None:
            existing_slugs.add(row_slug)
        if row_name is not None:
            normalized = _normalize_string(row_name)
            if normalized:
                existing_name_keys.add(_sort_key(normalized))

    discovered_rows: list[PublicRecordRow] = []
    for seed_row in seed_rows:
        if len(discovered_rows) >= max_new_per_state:
            break

        if seed_row["id"] in existing_ids:
            continue
        if seed_row["slug"] in existing_slugs:
            continue
        if _sort_key(seed_row["name"]) in existing_name_keys:
            continue

        discovered_rows.append(seed_row)

    return discovered_rows


def _discover_noop_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del existing_rows, max_new_per_state, timeout_seconds, session
    return []


def _discover_california_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_CALIFORNIA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_alaska_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_ALASKA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_alabama_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_ALABAMA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_arkansas_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_ARKANSAS_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_arizona_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_ARIZONA_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_colorado_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_COLORADO_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_washington_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_WASHINGTON_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_illinois_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_ILLINOIS_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_ohio_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_OHIO_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


def _discover_tennessee_official_public_record_rows(
    *,
    existing_rows: Sequence[Mapping[str, object]],
    max_new_per_state: int,
    timeout_seconds: float,
    session: requests.Session | None,
) -> list[PublicRecordRow]:
    del timeout_seconds, session
    return _discover_seed_rows(
        seed_rows=_TENNESSEE_OFFICIAL_PUBLIC_RECORD_SEED_ROWS,
        existing_rows=existing_rows,
        max_new_per_state=max_new_per_state,
    )


_OFFICIAL_US_STATE_DISCOVERY_ADAPTER_OVERRIDES: dict[str, OfficialStateDiscoveryAdapter] = {
    "AK": _discover_alaska_official_public_record_rows,
    "AL": _discover_alabama_official_public_record_rows,
    "AR": _discover_arkansas_official_public_record_rows,
    "AZ": _discover_arizona_official_public_record_rows,
    "CA": _discover_california_official_public_record_rows,
    "CO": _discover_colorado_official_public_record_rows,
    "IL": _discover_illinois_official_public_record_rows,
    "OH": _discover_ohio_official_public_record_rows,
    "TN": _discover_tennessee_official_public_record_rows,
    "WA": _discover_washington_official_public_record_rows,
}

OFFICIAL_US_STATE_DISCOVERY_ADAPTERS: dict[str, OfficialStateDiscoveryAdapter] = {
    state_code: _OFFICIAL_US_STATE_DISCOVERY_ADAPTER_OVERRIDES.get(
        state_code, _discover_noop_official_public_record_rows
    )
    for state_code in sorted(US_STATE_CODES)
}


def discover_official_us_state_public_record_rows(  # noqa: PLR0913
    existing_rows: Sequence[Mapping[str, object]],
    *,
    selected_regions: Sequence[str] | None = None,
    region_state_map: Mapping[str, frozenset[str]] = DEFAULT_REGION_STATE_MAP,
    max_new_per_state: int = _DEFAULT_CHAMBERS_MAX_NEW_PER_REGION,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
    strict_state_adapter_coverage: bool = False,
) -> OfficialStateDiscoveryResult:
    if timeout_seconds <= 0:
        raise PublicRecordRefreshError("Discovery timeout_seconds must be > 0")
    if max_new_per_state < 0:
        raise PublicRecordRefreshError("max_new_per_state must be >= 0")

    regions = tuple(selected_regions or DEFAULT_REGION_TARGETS.keys())
    _validate_regions(regions, region_state_map)

    if "US" not in regions:
        return OfficialStateDiscoveryResult(
            rows=[],
            added_count_by_state={},
            unsupported_states=(),
        )

    requested_us_states = tuple(
        sorted(state for state in region_state_map["US"] if state in US_STATE_CODES),
    )
    unsupported_states = tuple(
        state for state in requested_us_states if state not in OFFICIAL_US_STATE_DISCOVERY_ADAPTERS
    )
    if strict_state_adapter_coverage and unsupported_states:
        raise PublicRecordRefreshError(
            "Official-source discovery adapters are missing for states: "
            + ", ".join(unsupported_states),
        )

    rows: list[PublicRecordRow] = []
    added_count_by_state: dict[str, int] = {}
    for state_code in requested_us_states:
        adapter = OFFICIAL_US_STATE_DISCOVERY_ADAPTERS.get(state_code)
        if adapter is None:
            continue
        discovered_rows = adapter(
            existing_rows=existing_rows,
            max_new_per_state=max_new_per_state,
            timeout_seconds=timeout_seconds,
            session=session,
        )
        added_count_by_state[state_code] = len(discovered_rows)
        rows.extend(discovered_rows)

    return OfficialStateDiscoveryResult(
        rows=rows,
        added_count_by_state=added_count_by_state,
        unsupported_states=unsupported_states,
    )


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
    raise PublicRecordRefreshError(
        "Chambers discovery is disabled. Only official public sources (for example "
        "government and state bar records) are allowed.",
    )

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
            source_url = (
                _chambers_public_profile_url(
                    name=entry.name,
                    organisation_id=entry.organisation_id,
                    group_id=entry.group_id,
                )
                or profile_url
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
                    "source_url": source_url,
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
    website = _required_string(raw_row, "website")
    source_label = _required_string(raw_row, "source_label")

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

    source_url = _canonicalize_source_url(
        name=name,
        source_label=source_label,
        source_url=_optional_string(raw_row.get("source_url")),
    )
    _validate_authoritative_source(
        name=name,
        state=state,
        website=website,
        source_label=source_label,
        source_url=source_url,
    )

    return _NormalizedListing(
        id=listing_id,
        slug=slug,
        name=name,
        website=website,
        description=_required_string(raw_row, "description"),
        city=_required_string(raw_row, "city"),
        state=state,
        practice_tags=practice_tags,
        source_label=source_label,
        source_url=source_url,
        region=region,
    )


def _canonicalize_source_url(
    *,
    name: str,
    source_label: str,
    source_url: str | None,
) -> str | None:
    if source_url is None:
        return None
    if source_label != CHAMBERS_SOURCE_LABEL:
        return source_url
    return (
        _chambers_public_profile_url_from_source_url(
            name=name,
            source_url=source_url,
        )
        or source_url
    )


def _has_listing_query_parameter(source_url: str) -> bool:
    parsed = urlparse(source_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    return any(key.casefold() == "listing" for key, _value in query_pairs)


def _has_listing_fragment_parameter(source_url: str) -> bool:
    fragment = (urlparse(source_url).fragment or "").strip()
    if not fragment:
        return False
    fragment_fields = [field.strip() for field in fragment.split("&") if field.strip()]
    for field in fragment_fields:
        key = field.split("=", 1)[0].strip().casefold()
        if key == "listing":
            return True
    return False


def _strip_url_fragment(source_url: str) -> str:
    return urlparse(source_url)._replace(fragment="").geturl()


def _is_ohio_attorney_profile_source_url(source_url: str) -> bool:
    parsed = urlparse(source_url)
    normalized_path = _normalize_url_for_comparison(parsed.path or "")
    if normalized_path != "/attorneysearch":
        return False
    fragment = (parsed.fragment or "").strip()
    return bool(_OHIO_ATTORNEY_PROFILE_FRAGMENT_RE.fullmatch(fragment))


def _validate_authoritative_source(
    *,
    name: str,
    state: str,
    website: str,
    source_label: str,
    source_url: str | None,
) -> None:
    if source_label == CHAMBERS_SOURCE_LABEL:
        raise PublicRecordRefreshError(
            f"Listing '{name}' uses Chambers as a source; "
            "only official public sources are allowed."
        )

    if source_label == LEGACY_SELF_REPORTED_SOURCE_LABEL:
        raise PublicRecordRefreshError(
            f"Listing '{name}' uses a deprecated self-reported source label; "
            "set source_label/source_url to an authoritative public record source."
        )

    if source_url is None:
        if state.strip().upper() in US_STATE_CODES:
            raise PublicRecordRefreshError(
                f"Listing '{name}' is missing source_url for U.S. state '{state.strip().upper()}'.",
            )
        return

    if _is_chambers_source_url(source_url):
        raise PublicRecordRefreshError(
            f"Listing '{name}' uses a Chambers URL; " "only official public sources are allowed."
        )

    if _is_chambers_search_url(source_url):
        raise PublicRecordRefreshError(
            f"Listing '{name}' uses a Chambers search URL; "
            "source_url must point to a specific source record."
        )

    if _normalize_url_for_comparison(source_url) == _normalize_url_for_comparison(website):
        raise PublicRecordRefreshError(
            f"Listing '{name}' has source_url matching website; "
            "source_url must reference the external source of record."
        )

    _validate_us_state_source_policy(
        name=name,
        state=state,
        source_label=source_label,
        source_url=source_url,
    )


def _validate_us_state_source_policy(
    *,
    name: str,
    state: str,
    source_label: str,
    source_url: str,
) -> None:
    state_code = state.strip().upper()
    if state_code not in US_STATE_CODES:
        return

    source_rule = US_STATE_AUTHORITATIVE_SOURCES.get(state_code)
    if source_rule is None:
        raise PublicRecordRefreshError(
            f"Listing '{name}' is missing an authoritative source rule for state '{state_code}'.",
        )

    expected_label = source_rule["source_label"]
    if source_label != expected_label:
        raise PublicRecordRefreshError(
            f"Listing '{name}' has source_label '{source_label}' but "
            f"state '{state_code}' requires '{expected_label}'.",
        )

    source_host = _url_host(source_url)
    if source_host is None:
        raise PublicRecordRefreshError(
            f"Listing '{name}' has an invalid source_url hostname: {source_url}",
        )

    if not _host_matches_any_domain(source_host, source_rule["allowed_domains"]):
        allowed_domains = ", ".join(sorted(source_rule["allowed_domains"]))
        raise PublicRecordRefreshError(
            f"Listing '{name}' source_url host '{source_host}' is not allowed for "
            f"state '{state_code}'. Allowed domains: {allowed_domains}",
        )

    if _has_listing_query_parameter(source_url) or _has_listing_fragment_parameter(source_url):
        raise PublicRecordRefreshError(
            f"Listing '{name}' source_url includes a synthetic listing marker; "
            "source_url must be the exact public record URL."
        )

    if state_code == "OH" and _is_ohio_attorney_profile_source_url(source_url):
        return

    normalized_source_url = _normalize_url_for_comparison(_strip_url_fragment(source_url))
    normalized_state_source = _normalize_url_for_comparison(
        _strip_url_fragment(source_rule["source_url"])
    )
    if normalized_source_url == normalized_state_source:
        raise PublicRecordRefreshError(
            f"Listing '{name}' source_url points to a generic state source page; "
            "source_url must link directly to the specific public record."
        )


def _normalize_url_for_comparison(value: str) -> str:
    return _normalize_string(value).casefold().rstrip("/")


def _url_host(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname is None:
        return None
    return hostname.casefold()


def _host_matches_any_domain(host: str, allowed_domains: frozenset[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def _is_chambers_search_url(source_url: str) -> bool:
    host = _url_host(source_url)
    if host is None:
        return False
    parsed = urlparse(source_url)
    path = (parsed.path or "").casefold()
    return _host_matches_any_domain(host, frozenset({"chambers.com"})) and path.startswith(
        "/search",
    )


def _is_chambers_source_url(source_url: str) -> bool:
    host = _url_host(source_url)
    if host is None:
        return False
    return _host_matches_any_domain(
        host,
        frozenset(
            {
                "chambers.com",
                "profiles-portal.chambers.com",
                "chamberssitemap.blob.core.windows.net",
                "ranking-tables.chambers.com",
            },
        ),
    )


def _chambers_public_profile_url(
    *,
    name: str,
    organisation_id: int,
    group_id: int,
) -> str | None:
    group_slug = CHAMBERS_GROUP_SLUG_BY_ID.get(group_id)
    if group_slug is None:
        return None
    slug_base = _slug_base(name)
    return _CHAMBERS_PUBLIC_PROFILE_URL_TEMPLATE.format(
        slug_base=slug_base,
        group_slug=group_slug,
        group_id=group_id,
        organisation_id=organisation_id,
    )


def _chambers_public_profile_url_from_source_url(
    *,
    name: str,
    source_url: str,
) -> str | None:
    match = _CHAMBERS_PROFILE_BASICS_SOURCE_URL_RE.match(source_url)
    if match is None:
        return None
    organisation_id = int(match.group("organisation_id"))
    group_id = int(match.group("group_id"))
    return _chambers_public_profile_url(
        name=name,
        organisation_id=organisation_id,
        group_id=group_id,
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

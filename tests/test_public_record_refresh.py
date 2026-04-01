from __future__ import annotations

import re
from typing import Any, Mapping, Sequence, cast

import pytest
import requests

from hushline import public_record_refresh
from hushline.public_record_refresh import (
    DEFAULT_REGION_STATE_MAP,
    OFFICIAL_US_STATE_DISCOVERY_ADAPTERS,
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    LinkCheckResult,
    LinkValidationFailure,
    OfficialStateDiscoveryResult,
    PublicRecordRefreshError,
    PublicRecordRefreshResult,
    _apply_region_targets,
    _chambers_public_profile_url,
    _chambers_public_profile_url_from_source_url,
    _ChambersIndexEntry,
    _discovered_description,
    _fetch_json_payload,
    _normalize_practice_tags,
    _NormalizedListing,
    _optional_string,
    _parse_chambers_index_entries,
    _required_string,
    _slug_base,
    _validate_regions,
    build_requests_link_checker,
    discover_chambers_public_record_rows,
    discover_official_us_state_public_record_rows,
    refresh_public_record_rows,
    render_refresh_summary,
)
from tests.public_record_adapter_harness import (
    assert_official_source_adapter_rows,
    build_existing_row_for_collision,
)

_IMPLEMENTED_OFFICIAL_SOURCE_STATES: tuple[str, ...] = tuple(
    state_code
    for state_code, adapter in sorted(OFFICIAL_US_STATE_DISCOVERY_ADAPTERS.items())
    if adapter.__name__ != "_discover_noop_official_public_record_rows"
)

_BATCH_ONE_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "AK",
        "seed-jon-marc-petersen",
        "public-record~jon-marc-petersen",
        "Jon-Marc Petersen",
        "Alaska Bar Association public directory",
        (
            "https://member.alaskabar.org/cv5/cgi-bin/memberdll.dll/Info"
            "?CUSTOMERCD=8744&WRP=Customer_Profile.htm"
        ),
    ),
    (
        "AL",
        "seed-marc-james-ayers",
        "public-record~marc-james-ayers",
        "Marc James Ayers",
        "Alabama State Bar public directory",
        "https://members.alabar.org/Member_Portal/Member_Portal/Sections/AP.aspx",
    ),
    (
        "AR",
        "seed-kristin-l-pawlik",
        "public-record~kristin-l-pawlik",
        "Kristin L. Pawlik",
        "Arkansas Bar Association public directory",
        "https://www.arkbar.com/?pg=board-of-trustees",
    ),
    (
        "AZ",
        "seed-anthony-cali",
        "public-record~anthony-cali",
        "Anthony Cali",
        "State Bar of Arizona public directory",
        (
            "https://www.azbar.org/for-legal-professionals/practice-tools-management/"
            "member-directory/?m=Anthony-Cali-177781"
        ),
    ),
    (
        "CO",
        "seed-rachel-brock",
        "public-record~rachel-brock",
        "Rachel Brock",
        "Colorado Bar Association public directory",
        (
            "https://community.cobar.org/profile/contributions/"
            "contributions-achievements"
            "?UserKey=330f70ad-afc9-44f0-b8b1-6b55108bc275"
        ),
    ),
)

_BATCH_ONE_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_ONE_STATE_SEEDS
)

_BATCH_TWO_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "CT",
        "seed-eric-r-brown",
        "public-record~eric-r-brown",
        "Eric R. Brown",
        "Connecticut Bar Association public directory",
        ("https://members.ctbar.org/member/thelaborlawyer"),
    ),
    (
        "DE",
        "seed-richard-l-abbott",
        "public-record~richard-l-abbott",
        "Richard L. Abbott",
        "Delaware Courts published opinion",
        ("https://courts.delaware.gov/Opinions/Download.aspx?id=342050"),
    ),
    (
        "FL",
        "seed-jerry-ray-poole-jr",
        "public-record~jerry-ray-poole-jr",
        "Jerry Ray Poole, Jr.",
        "The Florida Bar public directory",
        ("https://www.floridabar.org/directories/find-mbr/profile/?num=123000"),
    ),
    (
        "GA",
        "seed-todd-h-stanton",
        "public-record~todd-h-stanton",
        "Todd H. Stanton",
        "State Bar of Georgia speaker profile",
        ("https://icle.gabar.org/speaker/todd-stanton-1261014"),
    ),
    (
        "HI",
        "seed-eric-seitz",
        "public-record~eric-seitz",
        "Eric Seitz",
        "Hawaii State Bar Association attorney recognition record",
        ("https://hsba.org/HSBA_2020/About_Us/Living_Legend_Lawyers_.aspx"),
    ),
)

_BATCH_TWO_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_TWO_STATE_SEEDS
)

_BATCH_THREE_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "IA",
        "seed-roxanne-barton-conlin",
        "public-record~roxanne-barton-conlin",
        "Roxanne Barton Conlin",
        "Iowa State Bar Association jury verdict record",
        (
            "https://services.iowabar.org/IB/JuryVerdicts.nsf/"
            "b96238336212630c85258ca1000240fd/"
            "e71fe5f6f6d3242d872589900011edc5!OpenDocument"
        ),
    ),
    (
        "ID",
        "seed-trudy-hanson-fouser",
        "public-record~trudy-hanson-fouser",
        "Trudy Hanson Fouser",
        "Idaho State Bar attorney profile",
        "https://isb.idaho.gov/blog/trudy-hanson-fouser/",
    ),
    (
        "IN",
        "seed-georgianna-quinn-tutwiler",
        "public-record~georgianna-quinn-tutwiler",
        "Georgianna Quinn Tutwiler",
        "Indiana State Bar public directory",
        "https://www.inbar.org/members/?id=30400364",
    ),
    (
        "KS",
        "seed-michael-f-brady",
        "public-record~michael-f-brady",
        "Michael F. Brady",
        "Kansas Judicial Branch published opinion",
        (
            "https://kscourts.gov/Cases-Decisions/Decisions/Published/"
            "Brown-v-Ford-Storage-and-Moving-Co-Inc"
        ),
    ),
    (
        "KY",
        "seed-andrew-clarke-weeks",
        "public-record~andrew-clarke-weeks",
        "Andrew Clarke Weeks",
        "Kentucky Bar Association public directory",
        "https://www.kybar.org/members/?id=42347567",
    ),
)

_BATCH_THREE_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_THREE_STATE_SEEDS
)

_BATCH_FOUR_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "LA",
        "seed-gregory-james-sauzer",
        "public-record~gregory-james-sauzer",
        "Gregory James Sauzer",
        "Louisiana Attorney Disciplinary Board attorney records",
        "https://www.ladb.org/DR/Document.cfm?docket=24-DB-014",
    ),
    (
        "MA",
        "seed-hillary-j-massey",
        "public-record~hillary-j-massey",
        "Hillary J. Massey",
        "Massachusetts BBO attorney records",
        "https://bbopublic.massbbo.org/web/f/SJC_WellBeing_Cmte_Report.pdf",
    ),
    (
        "MD",
        "seed-sean-w-baker",
        "public-record~sean-w-baker",
        "Sean W. Baker",
        "Maryland Courts attorney discipline records",
        "https://www.courts.state.md.us/attygrievance/sanctions07",
    ),
    (
        "ME",
        "seed-daniel-b-eccher",
        "public-record~daniel-b-eccher",
        "Daniel B. Eccher",
        "Maine Board of Overseers of the Bar public directory",
        "https://mebarconnect.mainebar.org/people/daniel-eccher",
    ),
    (
        "MI",
        "seed-gerard-v-mantese",
        "public-record~gerard-v-mantese",
        "Gerard V. Mantese",
        "State Bar of Michigan public directory",
        (
            "https://connect.michbar.org/laborlaw/home/council/section-members/"
            "-in-directory/directorysearchresults/?UserKey="
            "7af6ed96-c3cf-4f2d-b5f6-8effee281468"
        ),
    ),
)

_BATCH_FOUR_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_FOUR_STATE_SEEDS
)


_BATCH_FIVE_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "MN",
        "seed-landon-j-ascheman",
        "public-record~landon-j-ascheman",
        "Landon J. Ascheman",
        "Minnesota Courts attorney records",
        "https://mncourts.gov/help-topics/Legal-Paraprofessional-Program/standing-committee",
    ),
    (
        "MO",
        "seed-jerina-d-phillips",
        "public-record~jerina-d-phillips",
        "Jerina D. Phillips",
        "The Missouri Bar public directory",
        "https://news.mobar.org/jerina-d-phillips-receives-2025-diversity-champion-award/",
    ),
    (
        "MS",
        "seed-joel-frank-dillard",
        "public-record~joel-frank-dillard",
        "Joel Frank Dillard",
        "The Mississippi Bar public directory",
        "https://www.msbar.org/inside-the-bar/sections/labor-employment-law/",
    ),
    (
        "MT",
        "seed-tanis-m-holm",
        "public-record~tanis-m-holm",
        "Tanis M. Holm",
        "State Bar of Montana public directory",
        "https://www.montanabar.org/About-Us/Sections-and-Committees",
    ),
    (
        "NC",
        "seed-kevin-g-williams",
        "public-record~kevin-g-williams",
        "Kevin G. Williams",
        "North Carolina State Bar public directory",
        "https://www.ncbar.gov/for-lawyers/directories/leadership/state-bar-officers/",
    ),
)

_BATCH_FIVE_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_FIVE_STATE_SEEDS
)


_BATCH_SIX_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "ND",
        "seed-nathan-c-severson",
        "public-record~nathan-c-severson",
        "Nathan C. Severson",
        "North Dakota Court System attorney directory",
        "https://www.ndcourts.gov/lawyers/06402",
    ),
    (
        "NE",
        "seed-heidi-a-guttau",
        "public-record~heidi-a-guttau",
        "Heidi A. Guttau",
        "Nebraska Judicial Branch case record",
        (
            "https://supremecourt.nebraska.gov/courts/supreme-court/"
            "supreme-court-call/city-omaha-v-professional-firefighters-"
            "association-omaha"
        ),
    ),
    (
        "NH",
        "seed-heather-m-burns",
        "public-record~heather-m-burns",
        "Heather M. Burns",
        "New Hampshire Bar Association CLE speaker profile",
        ("https://member.nhbar.org/calendar/event/34th-annual-labor-and-" "employment-law-update"),
    ),
    (
        "NJ",
        "seed-rubin-m-sinins",
        "public-record~rubin-m-sinins",
        "Rubin M. Sinins",
        "NJ Courts attorney certification records",
        (
            "https://www.njcourts.gov/notices/order-board-attorney-"
            "certification-new-chair-and-vice-chair-designations-certification"
        ),
    ),
    (
        "NM",
        "seed-elizabeth-a-heaphy",
        "public-record~elizabeth-a-heaphy",
        "Elizabeth A. Heaphy",
        "State Bar of New Mexico public directory",
        (
            "https://www.sbnm.org/cvweb/cgi-bin/Utilities.dll?View="
            "INMEMBERDETAILS&RECORDNO=1&CUSTOMERNO=11321"
        ),
    ),
)

_BATCH_SIX_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_SIX_STATE_SEEDS
)


_BATCH_SEVEN_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "NV",
        "seed-luke-w-molleck",
        "public-record~luke-w-molleck",
        "Luke W. Molleck",
        "State Bar of Nevada public directory",
        (
            "https://nvbar.org/for-lawyers/bar-service-opportunities/join-a-section/"
            "labor-and-employment-law-section/"
        ),
    ),
    (
        "NY",
        "seed-gary-j-malone",
        "public-record~gary-j-malone",
        "Gary J. Malone",
        "New York Courts attorney directory",
        "https://decisions.courts.state.ny.us/ad3/Decisions/2023/CV-22-1940.pdf",
    ),
    (
        "OK",
        "seed-charles-greenough",
        "public-record~charles-greenough",
        "Charles Greenough",
        "Oklahoma Bar Association public directory",
        (
            "https://ams.okbar.org/eweb/DynamicPage.aspx?Action=Add&DoNotSave=yes&"
            "ObjectKeyFrom=1A83491A-9853-4C87-86A4-F7D95601C2E2&ParentDataObject="
            "Invoice+Detail&ParentObject=CentralizedOrderEntry&WebCode="
            "ProdDetailAdd&ivd_cst_key=00000000-0000-0000-0000-000000000000&"
            "ivd_cst_ship_key=00000000-0000-0000-0000-000000000000&ivd_formkey="
            "69202792-63d7-4ba2-bf4e-a0da41270555&ivd_prc_prd_key="
            "F5FDCC21-BBDF-4D41-944F-5351AD775A80"
        ),
    ),
    (
        "OR",
        "seed-andrew-toney-noland",
        "public-record~andrew-toney-noland",
        "Andrew Toney-Noland",
        "Oregon State Bar public directory",
        "https://www.osbar.org/sections/labor.html",
    ),
    (
        "PA",
        "seed-shanon-jude-carson",
        "public-record~shanon-jude-carson",
        "Shanon Jude Carson",
        "Pennsylvania Disciplinary Board attorney directory",
        "https://www.padisciplinaryboard.org/for-the-public/find-attorney/attorney-detail/85957",
    ),
)

_BATCH_SEVEN_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_SEVEN_STATE_SEEDS
)


_BATCH_EIGHT_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "RI",
        "seed-mark-b-decof",
        "public-record~mark-b-decof",
        "Mark B. Decof",
        "Rhode Island Judiciary attorney records",
        (
            "https://www.courts.ri.gov/attorney-resources/Pages/"
            "Board-of-Bar-Examiners-default.aspx"
        ),
    ),
    (
        "SC",
        "seed-j-hagood-tighe",
        "public-record~j-hagood-tighe",
        "J. Hagood Tighe",
        "South Carolina Bar public directory",
        (
            "https://www.scbar.org/for-lawyers/networking/sections/"
            "employment-and-labor-law-section/"
        ),
    ),
    (
        "SD",
        "seed-patrick-g-goetzinger",
        "public-record~patrick-g-goetzinger",
        "Patrick G. Goetzinger",
        "State Bar of South Dakota public directory",
        "https://www.statebarofsouthdakota.com/project-rural-practice/",
    ),
    (
        "TX",
        "seed-mark-anthony-sanchez",
        "public-record~mark-anthony-sanchez",
        "Mark Anthony Sanchez",
        "State Bar of Texas public directory",
        (
            "https://www.texasbar.com/AM/Template.cfm?ContactID=157597&template="
            "%2FCustomsource%2FMemberDirectory%2FMemberDirectoryDetail.cfm"
        ),
    ),
    (
        "UT",
        "seed-lara-a-swensen",
        "public-record~lara-a-swensen",
        "Lara A. Swensen",
        "Utah Courts public legal directory",
        (
            "https://www.utcourts.gov/en/about/administration/committees/"
            "ethics-advisory-committee.html"
        ),
    ),
)

_BATCH_EIGHT_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_EIGHT_STATE_SEEDS
)


_BATCH_NINE_STATE_SEEDS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "VA",
        "seed-frederick-h-schutt",
        "public-record~frederick-h-schutt",
        "Frederick H. Schutt",
        "Virginia State Bar public directory",
        "https://virginialawyer.vsb.org/articles/professional-notices?article_id=5100257&i=859839",
    ),
    (
        "VT",
        "seed-jeremy-s-grant",
        "public-record~jeremy-s-grant",
        "Jeremy S. Grant",
        "Vermont Bar Association public directory",
        "https://www.vtbar.org/2025-annual-meeting-in-review/",
    ),
    (
        "WI",
        "seed-jennifer-s-mirus",
        "public-record~jennifer-s-mirus",
        "Jennifer S. Mirus",
        "State Bar of Wisconsin public directory",
        (
            "https://www.wisbar.org/NewsPublications/WisconsinLawyer/"
            "WisconsinLawyerPDFs/97/01/20_24.pdf"
        ),
    ),
    (
        "WV",
        "seed-todd-bailess",
        "public-record~todd-bailess",
        "Todd Bailess",
        "West Virginia State Bar public directory",
        "https://wvbar.org/wp-content/uploads/2024/04/24-25-Active-List-UPDATED.pdf",
    ),
    (
        "WY",
        "seed-scott-e-kolpitcke",
        "public-record~scott-e-kolpitcke",
        "Scott E. Kolpitcke",
        "Wyoming State Bar public directory",
        "https://www.wyomingbar.org/about-us/bar-leadership/",
    ),
)

_BATCH_NINE_EXISTING_COLLISION_CASES: tuple[tuple[str, str, str, str], ...] = tuple(
    (state_code, seed_id, seed_slug, seed_name)
    for state_code, seed_id, seed_slug, seed_name, _, _ in _BATCH_NINE_STATE_SEEDS
)


def _row(  # noqa: PLR0913
    *,
    id_value: str | None,
    slug: str | None,
    name: str,
    state: str,
    website: str,
    source_url: str | None = None,
) -> public_record_refresh.PublicRecordRow:
    source_slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    state_code = state.strip().upper()
    state_source = US_STATE_AUTHORITATIVE_SOURCES.get(state_code)
    default_source_label = (
        state_source["source_label"]
        if state_source is not None
        else "Authoritative public record source"
    )
    default_source_url = (
        state_source["source_url"]
        if state_source is not None
        else f"https://records.example/{source_slug}"
    )
    if state_source is not None and state_code in US_STATE_CODES:
        if state_code == "CA":
            default_source_url = "https://apps.calbar.ca.gov/attorney/Licensee/Detail/350631"
        else:
            query_sep = "&" if "?" in default_source_url else "?"
            default_source_url = f"{default_source_url}{query_sep}record={source_slug}"

    row: dict[str, object] = {
        "name": name,
        "website": website,
        "description": f"{name} description",
        "city": "New York",
        "state": state,
        "practice_tags": ["Whistleblowing", "Investigations"],
        "source_label": default_source_label,
        "source_url": source_url or default_source_url,
    }
    if id_value is not None:
        row["id"] = id_value
    if slug is not None:
        row["slug"] = slug
    return cast(public_record_refresh.PublicRecordRow, row)


def _discover_rows_for_state(
    *,
    state_code: str,
    existing_rows: Sequence[Mapping[str, object]],
) -> OfficialStateDiscoveryResult:
    return discover_official_us_state_public_record_rows(
        existing_rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )


def _normalized_listing(
    *,
    listing_id: str,
    slug: str,
    name: str,
    region: str,
) -> _NormalizedListing:
    return _NormalizedListing(
        id=listing_id,
        slug=slug,
        name=name,
        website="https://example.test",
        description=f"{name} description",
        city="City",
        state=region,
        practice_tags=("Whistleblowing",),
        source_label="Authoritative source",
        source_url="https://records.example/source",
        region=region,
    )


def test_default_us_region_state_map_includes_all_50_states() -> None:
    expected = frozenset(
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

    assert expected == US_STATE_CODES
    assert DEFAULT_REGION_STATE_MAP["US"] == expected
    assert set(US_STATE_AUTHORITATIVE_SOURCES) == set(expected)


def test_refresh_public_record_rows_is_deterministic_and_schema_compatible() -> None:
    rows = [
        _row(
            id_value="seed-zed",
            slug="public-record~zed",
            name="Zed Firm",
            state="NY",
            website="https://zed.example",
        ),
        _row(
            id_value="seed-alpha",
            slug="public-record~alpha",
            name="Alpha Firm",
            state="NY",
            website="https://alpha.example",
        ),
    ]

    result_a = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
    )
    result_b = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
    )

    assert result_a.rows == result_b.rows
    assert [row["id"] for row in result_a.rows] == ["seed-alpha", "seed-zed"]
    assert list(result_a.rows[0]) == [
        "id",
        "slug",
        "name",
        "website",
        "description",
        "city",
        "state",
        "practice_tags",
        "source_label",
        "source_url",
    ]


def test_refresh_public_record_rows_preserves_existing_identifiers() -> None:
    rows = [
        _row(
            id_value="seed-preserved",
            slug="public-record~preserved",
            name="Preserved Firm",
            state="NY",
            website="https://preserved.example",
        ),
        _row(
            id_value=None,
            slug=None,
            name="Generated Firm",
            state="NY",
            website="https://generated.example",
        ),
    ]

    result = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
    )

    preserved = next(row for row in result.rows if row["name"] == "Preserved Firm")
    generated = next(row for row in result.rows if row["name"] == "Generated Firm")

    assert preserved["id"] == "seed-preserved"
    assert preserved["slug"] == "public-record~preserved"
    assert generated["id"] == "seed-generated-firm"
    assert generated["slug"] == "public-record~generated-firm"


def test_refresh_public_record_rows_rejects_duplicate_id_or_slug() -> None:
    duplicate_id_rows = [
        _row(
            id_value="seed-duplicate",
            slug="public-record~duplicate-a",
            name="Duplicate A",
            state="NY",
            website="https://duplicate-a.example",
        ),
        _row(
            id_value="seed-duplicate",
            slug="public-record~duplicate-b",
            name="Duplicate B",
            state="NY",
            website="https://duplicate-b.example",
        ),
    ]
    with pytest.raises(PublicRecordRefreshError, match="Duplicate listing id"):
        refresh_public_record_rows(
            duplicate_id_rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 2},
        )

    duplicate_slug_rows = [
        _row(
            id_value="seed-duplicate-a",
            slug="public-record~duplicate",
            name="Duplicate A",
            state="NY",
            website="https://duplicate-a.example",
        ),
        _row(
            id_value="seed-duplicate-b",
            slug="public-record~duplicate",
            name="Duplicate B",
            state="NY",
            website="https://duplicate-b.example",
        ),
    ]
    with pytest.raises(PublicRecordRefreshError, match="Duplicate listing slug"):
        refresh_public_record_rows(
            duplicate_slug_rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 2},
        )


def test_refresh_public_record_rows_enforces_region_targets() -> None:
    rows = [
        _row(
            id_value="seed-us-1",
            slug="public-record~us-1",
            name="US One",
            state="NY",
            website="https://us-one.example",
        ),
        _row(
            id_value="seed-eu-1",
            slug="public-record~eu-1",
            name="EU One",
            state="Germany",
            website="https://eu-one.example",
        ),
    ]

    with pytest.raises(PublicRecordRefreshError, match="below target"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"}), "EU": frozenset({"Germany"})},
            region_targets={"US": 2},
        )

    result = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"}), "EU": frozenset({"Germany"})},
        region_targets={"US": 1},
    )
    assert [row["id"] for row in result.rows] == ["seed-us-1"]
    assert result.region_counts == {"US": 1}


def test_refresh_public_record_rows_keeps_rows_above_region_targets() -> None:
    rows = [
        _row(
            id_value="seed-us-1",
            slug="public-record~us-1",
            name="US One",
            state="NY",
            website="https://us-one.example",
        ),
        _row(
            id_value="seed-us-2",
            slug="public-record~us-2",
            name="US Two",
            state="NY",
            website="https://us-two.example",
        ),
        _row(
            id_value="seed-us-3",
            slug="public-record~us-3",
            name="US Three",
            state="NY",
            website="https://us-three.example",
        ),
    ]

    result = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 1},
    )

    assert [row["id"] for row in result.rows] == ["seed-us-1", "seed-us-2", "seed-us-3"]
    assert result.region_counts == {"US": 3}


def test_refresh_public_record_rows_flags_and_drops_link_failures() -> None:
    rows = [
        _row(
            id_value="seed-healthy",
            slug="public-record~healthy",
            name="Healthy Firm",
            state="NY",
            website="https://healthy.example",
        ),
        _row(
            id_value="seed-broken",
            slug="public-record~broken",
            name="Broken Firm",
            state="NY",
            website="https://broken.example",
        ),
    ]
    checked_urls: list[str] = []

    def checker(url: str) -> LinkCheckResult:
        checked_urls.append(url)
        return LinkCheckResult(
            ok=url != "https://broken.example",
            reason="HTTP 404",
            definitive_failure=url == "https://broken.example",
        )

    flagged = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
        link_checker=checker,
        drop_failed_links=False,
    )
    assert len(flagged.rows) == 2
    assert len(flagged.link_failures) == 1
    assert flagged.dropped_record_ids == []
    assert flagged.checked_url_count == 4

    dropped = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
        link_checker=checker,
        drop_failed_links=True,
    )
    assert [row["id"] for row in dropped.rows] == ["seed-healthy"]
    assert dropped.dropped_record_ids == ["seed-broken"]
    assert dropped.checked_url_count == 4
    assert checked_urls


def test_refresh_public_record_rows_keeps_rows_on_transient_link_failures() -> None:
    rows = [
        _row(
            id_value="seed-healthy",
            slug="public-record~healthy",
            name="Healthy Firm",
            state="NY",
            website="https://healthy.example",
        ),
        _row(
            id_value="seed-transient",
            slug="public-record~transient",
            name="Transient Firm",
            state="NY",
            website="https://transient.example",
        ),
    ]

    def checker(url: str) -> LinkCheckResult:
        if url == "https://transient.example":
            return LinkCheckResult(ok=False, reason="HTTP 503")
        return LinkCheckResult(ok=True)

    result = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
        region_targets={"US": 2},
        link_checker=checker,
        drop_failed_links=True,
    )

    assert [row["id"] for row in result.rows] == ["seed-healthy", "seed-transient"]
    assert len(result.link_failures) == 1
    assert result.link_failures[0].listing_id == "seed-transient"
    assert result.dropped_record_ids == []


def test_refresh_public_record_rows_rejects_legacy_self_reported_source_label() -> None:
    rows = [
        _row(
            id_value="seed-legacy",
            slug="public-record~legacy",
            name="Legacy Firm",
            state="NY",
            website="https://legacy.example",
        )
    ]
    rows[0]["source_label"] = "Seed dataset from official firm website"
    rows[0]["source_url"] = "https://legacy.example"

    with pytest.raises(PublicRecordRefreshError, match="deprecated self-reported source label"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_source_matching_website() -> None:
    rows = [
        _row(
            id_value="seed-self-reference",
            slug="public-record~self-reference",
            name="Self Reference Firm",
            state="NY",
            website="https://self-reference.example/",
            source_url="https://self-reference.example",
        )
    ]

    with pytest.raises(PublicRecordRefreshError, match="source_url matching website"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_missing_us_source_url() -> None:
    rows = [
        _row(
            id_value="seed-missing-source-url",
            slug="public-record~missing-source-url",
            name="Missing Source URL Firm",
            state="NY",
            website="https://missing-source-url.example/",
            source_url="https://iapps.courts.state.ny.us/attorneyservices/search?0",
        )
    ]
    rows[0]["source_url"] = None

    with pytest.raises(PublicRecordRefreshError, match="is missing source_url for U.S. state"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_cross_state_source_policy() -> None:
    rows = [
        _row(
            id_value="seed-cross-state-source",
            slug="public-record~cross-state-source",
            name="Cross State Source Firm",
            state="NY",
            website="https://cross-state-source.example/",
            source_url="https://apps.calbar.ca.gov/attorney/Licensee/Detail/350631",
        )
    ]
    rows[0]["source_label"] = "State Bar of California attorney profile"

    with pytest.raises(PublicRecordRefreshError, match="state 'NY' requires"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_generic_us_source_url() -> None:
    rows = [
        _row(
            id_value="seed-ny-generic-source",
            slug="public-record~ny-generic-source",
            name="NY Generic Source Firm",
            state="NY",
            website="https://ny-generic-source.example/",
            source_url="https://iapps.courts.state.ny.us/attorneyservices/search?0",
        )
    ]

    with pytest.raises(PublicRecordRefreshError, match="generic state source page"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_allows_ohio_record_fragment_source_url() -> None:
    rows = [
        _row(
            id_value="seed-ohio-record-source",
            slug="public-record~ohio-record-source",
            name="Ohio Record Source Firm",
            state="OH",
            website="https://ohio-record-source.example/",
            source_url="https://www.supremecourt.ohio.gov/AttorneySearch/#/77563/attyinfo",
        )
    ]

    result = refresh_public_record_rows(
        rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"OH"})},
        region_targets={"US": 1},
    )
    assert len(result.rows) == 1


def test_refresh_public_record_rows_rejects_ohio_generic_home_fragment_source_url() -> None:
    rows = [
        _row(
            id_value="seed-ohio-generic-home-source",
            slug="public-record~ohio-generic-home-source",
            name="Ohio Generic Home Source Firm",
            state="OH",
            website="https://ohio-generic-home-source.example/",
            source_url="https://www.supremecourt.ohio.gov/AttorneySearch/#/home",
        )
    ]

    with pytest.raises(PublicRecordRefreshError, match="generic state source page"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"OH"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_synthetic_listing_marker() -> None:
    rows = [
        _row(
            id_value="seed-ny-synthetic-marker",
            slug="public-record~ny-synthetic-marker",
            name="NY Synthetic Marker Firm",
            state="NY",
            website="https://ny-synthetic-marker.example/",
            source_url=(
                "https://iapps.courts.state.ny.us/attorneyservices/search?0="
                "#listing=ny-synthetic-marker-firm"
            ),
        )
    ]

    with pytest.raises(PublicRecordRefreshError, match="synthetic listing marker"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_chambers_search_source_url() -> None:
    rows = [
        _row(
            id_value="seed-search",
            slug="public-record~search",
            name="Search Source Firm",
            state="NY",
            website="https://search-source.example",
            source_url="https://chambers.com/search?query=Search+Source+Firm",
        )
    ]
    rows[0]["source_label"] = "Chambers and Partners law firm search"

    with pytest.raises(PublicRecordRefreshError, match="uses a Chambers URL"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_rejects_chambers_source_url() -> None:
    rows = [
        _row(
            id_value="seed-cohen",
            slug="public-record~cohen",
            name="Cohen Milstein Sellers & Toll PLLC",
            state="NY",
            website="https://www.cohenmilstein.com/",
            source_url="https://chambers.com/law-firm/cohen-milstein-sellers-toll-pllc-usa-5:67329",
        )
    ]
    rows[0]["source_label"] = "Chambers and Partners ranked law firm profile"

    with pytest.raises(PublicRecordRefreshError, match="uses Chambers as a source"):
        refresh_public_record_rows(
            rows,
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
            region_targets={"US": 1},
        )


def test_refresh_public_record_rows_allows_non_chambers_hosts_with_chambers_substrings() -> None:
    rows = [
        _row(
            id_value="seed-substring-safe",
            slug="public-record~substring-safe",
            name="Substring Safe Firm",
            state="Germany",
            website="https://substring-safe.example",
            source_url=(
                "https://records.example/entry"
                "?mirror=profiles-portal.chambers.com"
                "&index=chamberssitemap.blob.core.windows.net"
            ),
        )
    ]

    result = refresh_public_record_rows(
        rows,
        selected_regions=["EU"],
        region_state_map={"EU": frozenset({"Germany"})},
        region_targets={"EU": 1},
    )
    assert len(result.rows) == 1


def test_build_requests_link_checker_retries_then_succeeds() -> None:
    class _FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def close(self) -> None:
            return None

    class _FakeSession:
        def __init__(self, status_codes: list[int]) -> None:
            self._status_codes = status_codes
            self._index = 0
            self.headers: dict[str, str] = {}

        def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
            status_code = self._status_codes[min(self._index, len(self._status_codes) - 1)]
            self._index += 1
            return _FakeResponse(status_code)

    fake_session = _FakeSession([503, 200])
    sleep_calls: list[float] = []
    checker = build_requests_link_checker(
        session=fake_session,  # type: ignore[arg-type]
        max_attempts=2,
        sleep_fn=sleep_calls.append,
    )

    result = checker("https://retry.example")
    assert result.ok is True
    assert fake_session._index == 2
    assert sleep_calls == [1.0]


def test_build_requests_link_checker_marks_404_as_definitive_failure() -> None:
    class _FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def close(self) -> None:
            return None

    class _FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
            return _FakeResponse(404)

    checker = build_requests_link_checker(
        session=_FakeSession(),  # type: ignore[arg-type]
        max_attempts=1,
        sleep_fn=lambda _seconds: None,
    )

    result = checker("https://missing.example")

    assert result.ok is False
    assert result.reason == "HTTP 404"
    assert result.definitive_failure is True


def test_build_requests_link_checker_rejects_invalid_arguments() -> None:
    with pytest.raises(PublicRecordRefreshError, match="--max-attempts must be >= 1"):
        build_requests_link_checker(max_attempts=0)

    with pytest.raises(PublicRecordRefreshError, match="--timeout-seconds must be > 0"):
        build_requests_link_checker(timeout_seconds=0)


def test_build_requests_link_checker_returns_last_server_error_after_retries() -> None:
    class _FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def close(self) -> None:
            return None

    class _FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
            return _FakeResponse(500)

    checker = build_requests_link_checker(
        session=_FakeSession(),  # type: ignore[arg-type]
        max_attempts=1,
        sleep_fn=lambda _seconds: None,
    )

    result = checker("https://retry.example")

    assert result.ok is False
    assert result.reason == "HTTP 500"
    assert result.definitive_failure is False


def test_build_requests_link_checker_returns_last_request_exception_reason() -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, *_args: Any, **_kwargs: Any) -> object:
            raise requests.RequestException("network timeout")

    checker = build_requests_link_checker(
        session=_FakeSession(),  # type: ignore[arg-type]
        max_attempts=1,
        sleep_fn=lambda _seconds: None,
    )

    result = checker("https://retry.example")

    assert result.ok is False
    assert result.reason == "network timeout"
    assert result.definitive_failure is False


def test_render_refresh_summary_includes_dropped_ids_and_link_failures() -> None:
    summary = render_refresh_summary(
        PublicRecordRefreshResult(
            rows=[],
            region_counts={"US": 2, "EU": 0},
            checked_url_count=3,
            link_failures=[
                LinkValidationFailure(
                    listing_id="seed-one",
                    listing_name="Seed One",
                    field="website",
                    url="https://broken.example",
                    reason="HTTP 404",
                )
            ],
            dropped_record_ids=["seed-one"],
        ),
        regions=["US", "EU"],
    )

    assert "## Public Record Refresh Summary" in summary
    assert "- Output records: 0" in summary
    assert "- Regional counts:" in summary
    assert "  - US: 2" in summary
    assert "- Dropped IDs:" in summary
    assert "  - `seed-one`" in summary
    assert "- Link failures:" in summary
    assert "  - `seed-one` `website` (HTTP 404): https://broken.example" in summary


def test_parse_chambers_index_entries_skips_invalid_rows_and_sorts() -> None:
    entries = _parse_chambers_index_entries(
        [
            "not-a-dict",
            {"oid": "2", "on": "Zulu LLP"},
            {"oid": "bad", "on": "Ignored LLP"},
            {"oid": 1, "on": " Alpha LLP ", "ptgid": None},
            {"oid": 3, "on": None},
        ],
        default_group_id=5,
    )

    assert entries == [
        _ChambersIndexEntry(organisation_id=1, name="Alpha LLP", group_id=5),
        _ChambersIndexEntry(organisation_id=2, name="Zulu LLP", group_id=5),
    ]


def test_fetch_json_payload_handles_non_200_and_successful_json() -> None:
    closed: list[int] = []

    class _Response:
        def __init__(self, status_code: int, payload: object) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> object:
            return self._payload

        def close(self) -> None:
            closed.append(self.status_code)

    class _Session:
        def __init__(self) -> None:
            self._responses = iter(
                [
                    _Response(503, {"ignored": True}),
                    _Response(200, {"ok": True}),
                ]
            )

        def get(self, *_args: Any, **_kwargs: Any) -> _Response:
            return next(self._responses)

    session = cast(requests.Session, _Session())

    assert _fetch_json_payload(session, "https://example.test/one", timeout_seconds=5) is None
    assert _fetch_json_payload(session, "https://example.test/two", timeout_seconds=5) == {
        "ok": True
    }
    assert closed == [503, 200]


def test_discovered_description_handles_tag_list_shapes() -> None:
    assert _discovered_description("Paris", "France", []) == (
        "A Chambers-ranked law firm with a public profile in Paris, France."
    )
    assert _discovered_description("Paris", "France", ["Whistleblowing"]) == (
        "A Chambers-ranked law firm with a public profile in Paris, France, "
        "covering Whistleblowing matters."
    )
    assert _discovered_description("Paris", "France", ["Whistleblowing", "Employment"]) == (
        "A Chambers-ranked law firm with a public profile in Paris, France, "
        "covering Whistleblowing and Employment matters."
    )
    assert _discovered_description(
        "Paris",
        "France",
        ["Whistleblowing", "Employment", "Investigations"],
    ) == (
        "A Chambers-ranked law firm with a public profile in Paris, France, "
        "covering Whistleblowing, Employment, and Investigations matters."
    )


def test_validate_regions_rejects_unknown_region() -> None:
    with pytest.raises(PublicRecordRefreshError, match="Unknown regions requested: LATAM"):
        _validate_regions(["US", "LATAM"], {"US": frozenset({"CA"})})


def test_chambers_public_profile_url_helpers_cover_supported_and_invalid_inputs() -> None:
    assert _chambers_public_profile_url(name="Alpha LLP", organisation_id=7, group_id=999) is None
    assert (
        _chambers_public_profile_url(
            name="Alpha LLP",
            organisation_id=7,
            group_id=5,
        )
        == "https://chambers.com/law-firm/alpha-llp-usa-5:7"
    )
    assert (
        _chambers_public_profile_url_from_source_url(
            name="Alpha LLP",
            source_url="https://profiles-portal.chambers.com/api/organisations/7/profile-basics?groupId=5",
        )
        == "https://chambers.com/law-firm/alpha-llp-usa-5:7"
    )
    assert (
        _chambers_public_profile_url_from_source_url(
            name="Alpha LLP",
            source_url="https://example.test/not-chambers",
        )
        is None
    )


def test_apply_region_targets_handles_none_and_invalid_target_configurations() -> None:
    normalized_rows = [
        _normalized_listing(
            listing_id="seed-us",
            slug="public-record~us",
            name="US Firm",
            region="US",
        ),
        _normalized_listing(
            listing_id="seed-eu",
            slug="public-record~eu",
            name="EU Firm",
            region="EU",
        ),
    ]

    assert _apply_region_targets(normalized_rows, ["EU", "US"], None) == [
        _normalized_listing(
            listing_id="seed-eu",
            slug="public-record~eu",
            name="EU Firm",
            region="EU",
        ),
        _normalized_listing(
            listing_id="seed-us",
            slug="public-record~us",
            name="US Firm",
            region="US",
        ),
    ]

    with pytest.raises(PublicRecordRefreshError, match="Missing region target for EU"):
        _apply_region_targets([normalized_rows[1]], ["EU"], {})

    with pytest.raises(PublicRecordRefreshError, match="Region target must be >= 0 for EU"):
        _apply_region_targets([normalized_rows[1]], ["EU"], {"EU": -1})


def test_normalization_helpers_validate_and_filter_values() -> None:
    assert _normalize_practice_tags([" Whistleblowing ", "", "Whistleblowing", "Employment"]) == (
        "Whistleblowing",
        "Employment",
    )

    with pytest.raises(PublicRecordRefreshError, match="practice_tags must be a list"):
        _normalize_practice_tags("not-a-list")

    with pytest.raises(PublicRecordRefreshError, match="practice_tags entries must be strings"):
        _normalize_practice_tags(["Whistleblowing", 1])

    with pytest.raises(
        PublicRecordRefreshError,
        match="practice_tags must contain at least one non-empty tag",
    ):
        _normalize_practice_tags([" ", "\t"])

    assert _required_string({"name": " Alpha LLP "}, "name") == "Alpha LLP"

    with pytest.raises(PublicRecordRefreshError, match="Missing required field: name"):
        _required_string({}, "name")

    with pytest.raises(PublicRecordRefreshError, match="Field 'name' must be a string"):
        _required_string({"name": 1}, "name")

    with pytest.raises(PublicRecordRefreshError, match="Field 'name' cannot be empty"):
        _required_string({"name": "   "}, "name")

    assert _optional_string(None) is None
    assert _optional_string(" Alpha LLP ") == "Alpha LLP"

    with pytest.raises(
        PublicRecordRefreshError,
        match="Optional string field must be a string or null",
    ):
        _optional_string(1)

    assert _slug_base(" Alpha LLP ") == "alpha-llp"

    with pytest.raises(PublicRecordRefreshError, match="Unable to derive slug from value"):
        _slug_base("!!!")


def test_discover_seed_rows_respects_zero_limit_and_maximum() -> None:
    seed_rows: list[public_record_refresh.PublicRecordRow] = [
        _row(
            state="CA",
            id_value="seed-one",
            slug="public-record~seed-one",
            name="Seed One",
            website="https://seed-one.example",
        ),
        _row(
            state="CA",
            id_value="seed-two",
            slug="public-record~seed-two",
            name="Seed Two",
            website="https://seed-two.example",
        ),
    ]

    assert (
        public_record_refresh._discover_seed_rows(
            seed_rows=seed_rows,
            existing_rows=[],
            max_new_per_state=0,
        )
        == []
    )
    assert public_record_refresh._discover_seed_rows(
        seed_rows=seed_rows,
        existing_rows=[],
        max_new_per_state=1,
    ) == [seed_rows[0]]


def test_discover_noop_official_public_record_rows_returns_empty_list() -> None:
    assert (
        public_record_refresh._discover_noop_official_public_record_rows(
            existing_rows=[
                _row(
                    state="CA",
                    id_value="seed-one",
                    slug="public-record~seed-one",
                    name="Seed One",
                    website="https://seed-one.example",
                )
            ],
            max_new_per_state=5,
            timeout_seconds=5,
            session=None,
        )
        == []
    )


def test_parse_chambers_index_entries_returns_empty_for_non_list_payload() -> None:
    assert _parse_chambers_index_entries({"not": "a-list"}, default_group_id=5) == []


def test_fetch_json_payload_handles_exceptions_and_invalid_json() -> None:
    closed: list[str] = []

    class _Response:
        status_code = 200

        def json(self) -> object:
            raise ValueError("bad json")

        def close(self) -> None:
            closed.append("closed")

    class _Session:
        def __init__(self) -> None:
            self._calls = 0

        def get(self, *_args: Any, **_kwargs: Any) -> _Response:
            self._calls += 1
            if self._calls == 1:
                raise requests.RequestException("network down")
            return _Response()

    session = cast(requests.Session, _Session())

    assert _fetch_json_payload(session, "https://example.test/one", timeout_seconds=5) is None
    assert _fetch_json_payload(session, "https://example.test/two", timeout_seconds=5) is None
    assert closed == ["closed"]


def test_chambers_discovery_helpers_cover_locations_tags_and_url_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert public_record_refresh._normalize_discovered_website(None) is None
    assert (
        public_record_refresh._normalize_discovered_website("https://example.test")
        == "https://example.test"
    )
    assert (
        public_record_refresh._normalize_discovered_website("www.example.test")
        == "https://www.example.test"
    )
    assert (
        public_record_refresh._normalize_discovered_website("example.test")
        == "https://example.test"
    )

    assert public_record_refresh._iter_office_candidates({"locations": "bad"}) == []
    assert public_record_refresh._iter_office_candidates(
        {
            "headOffice": {"town": "Headquarters", "country": "USA"},
            "locations": [
                "bad-location",
                {"country": "France", "offices": [{"town": "Paris"}, "bad-office"]},
                {"country": "Germany", "offices": "bad-list"},
            ],
        }
    ) == [
        {"town": "Headquarters", "country": "USA"},
        {"town": "Paris", "country": "France"},
    ]

    assert (
        public_record_refresh._pick_discovered_location(
            {"locations": []},
            region="US",
            allowed_states=frozenset({"CA"}),
        )
        is None
    )
    assert (
        public_record_refresh._pick_discovered_location(
            {"headOffice": {"country": "Canada", "town": "Toronto", "region": "Ontario"}},
            region="US",
            allowed_states=frozenset({"CA"}),
        )
        is None
    )
    assert (
        public_record_refresh._pick_discovered_location(
            {"headOffice": {"country": "United States", "town": "Austin", "region": "Texas"}},
            region="US",
            allowed_states=frozenset({"CA"}),
        )
        is None
    )
    assert public_record_refresh._pick_discovered_location(
        {
            "headOffice": {
                "country": "United States",
                "town": "San Francisco",
                "region": "California",
            }
        },
        region="US",
        allowed_states=frozenset({"CA"}),
    ) == ("San Francisco", "CA")
    assert public_record_refresh._pick_discovered_location(
        {
            "headOffice": {
                "country": "USA",
                "town": "Seattle",
                "address": "123 Pike Street, Seattle WA",
            }
        },
        region="US",
        allowed_states=frozenset({"WA"}),
    ) == ("Seattle", "WA")
    assert (
        public_record_refresh._pick_discovered_location(
            {"headOffice": {"town": "Paris"}},
            region="EU",
            allowed_states=frozenset({"France"}),
        )
        is None
    )
    assert (
        public_record_refresh._pick_discovered_location(
            {"headOffice": {"country": "France", "town": "Paris"}},
            region="EU",
            allowed_states=frozenset({"Germany"}),
        )
        is None
    )
    assert public_record_refresh._pick_discovered_location(
        {
            "locations": [
                {"country": "France", "offices": [{"town": "Paris"}]},
                {"country": "Germany", "offices": [{"town": "Berlin"}]},
            ]
        },
        region="EU",
        allowed_states=frozenset({"France", "Germany"}),
    ) == ("Paris", "France")

    assert public_record_refresh._canonical_country(" Republic of Singapore ") == "Singapore"
    assert public_record_refresh._canonical_country("U.S.A.") == "USA"
    assert public_record_refresh._canonical_country("United States") == "USA"
    assert public_record_refresh._canonical_country(None) is None

    assert public_record_refresh._us_state_code_for_office({"region": "CA"}) == "CA"
    assert public_record_refresh._us_state_code_for_office({"region": "Massachusetts"}) == "MA"
    assert (
        public_record_refresh._us_state_code_for_office(
            {"address": "100 Main Street, New York, NY"}
        )
        == "NY"
    )
    assert public_record_refresh._us_state_code_for_office({}) is None
    assert public_record_refresh._us_state_code_for_office({"address": "No state here"}) is None

    ranked_offices_payload = {
        "headOffice": {"website": "https://hq.example"},
        "locations": [{"country": "France", "offices": [{"phone": "+33"}]}],
    }
    assert public_record_refresh._first_office_field(ranked_offices_payload, "website") == (
        "https://hq.example"
    )
    assert public_record_refresh._first_office_field(ranked_offices_payload, "phone") == "+33"
    assert public_record_refresh._first_office_field(ranked_offices_payload, "missing") is None

    payloads = iter(
        [
            {"not": "a-list"},
            [
                "bad-item",
                {"practiceAreaName": "Whistleblowing investigations"},
                {"displayName": "Employment law"},
                {"practiceAreaName": "White collar defense"},
                {"practiceAreaName": "Employment law"},
            ],
            [
                {"displayName": "Fraud matters"},
                {"practiceAreaName": "Employment counseling"},
            ],
            [{"displayName": "Corporate advisory"}],
        ]
    )
    monkeypatch.setattr(
        public_record_refresh,
        "_fetch_json_payload",
        lambda *_args, **_kwargs: next(payloads),
    )
    session = cast(requests.Session, object())
    assert public_record_refresh._discover_practice_tags(
        session,
        organisation_id=1,
        group_id=5,
        timeout_seconds=5,
    ) == ("Whistleblowing", "Investigations", "Employment")
    assert public_record_refresh._discover_practice_tags(
        session,
        organisation_id=1,
        group_id=5,
        timeout_seconds=5,
    ) == ("Whistleblowing", "Investigations", "Employment")
    assert public_record_refresh._discover_practice_tags(
        session,
        organisation_id=1,
        group_id=5,
        timeout_seconds=5,
    ) == ("Fraud", "Employment")
    assert public_record_refresh._discover_practice_tags(
        session,
        organisation_id=1,
        group_id=5,
        timeout_seconds=5,
    ) == ("Whistleblowing", "Investigations", "Employment")


def test_discover_official_us_state_public_record_rows_validates_arguments_and_missing_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(PublicRecordRefreshError, match="Discovery timeout_seconds must be > 0"):
        discover_official_us_state_public_record_rows([], timeout_seconds=0)

    with pytest.raises(PublicRecordRefreshError, match="max_new_per_state must be >= 0"):
        discover_official_us_state_public_record_rows([], max_new_per_state=-1)

    no_us_result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["EU"],
        region_state_map={"EU": frozenset({"France"})},
    )
    assert no_us_result == OfficialStateDiscoveryResult(
        rows=[],
        added_count_by_state={},
        unsupported_states=(),
    )

    monkeypatch.setattr(
        public_record_refresh,
        "OFFICIAL_US_STATE_DISCOVERY_ADAPTERS",
        {"CA": OFFICIAL_US_STATE_DISCOVERY_ADAPTERS["CA"]},
    )
    with pytest.raises(
        PublicRecordRefreshError,
        match="Official-source discovery adapters are missing for states: NY",
    ):
        discover_official_us_state_public_record_rows(
            [],
            selected_regions=["US"],
            region_state_map={"US": frozenset({"CA", "NY"})},
            strict_state_adapter_coverage=True,
        )

    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"CA", "NY"})},
    )
    assert result.unsupported_states == ("NY",)
    assert result.added_count_by_state == {"CA": len(result.rows)}


def test_authoritative_source_and_url_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(
        PublicRecordRefreshError,
        match="Listing slug must start with 'public-record~': bad-slug",
    ):
        public_record_refresh._normalize_row(
            _row(
                state="CA",
                id_value="seed-one",
                slug="bad-slug",
                name="Seed One",
                website="https://seed-one.example",
            ),
            {"US": frozenset({"CA"})},
        )

    public_record_refresh._validate_authoritative_source(
        name="Alpha Avocats",
        state="France",
        website="https://alpha.example",
        source_label="French bar directory",
        source_url=None,
    )

    assert public_record_refresh._url_host("not a url") is None
    assert not public_record_refresh._is_chambers_search_url("not a url")
    assert not public_record_refresh._is_chambers_source_url("not a url")
    assert public_record_refresh._is_ohio_attorney_profile_source_url(
        "https://www.ohiobar.org/attorneysearch#/12345/attyinfo"
    )
    assert not public_record_refresh._is_ohio_attorney_profile_source_url(
        "https://www.ohiobar.org/not-attorneysearch#/12345/attyinfo"
    )

    monkeypatch.setattr(public_record_refresh, "_is_chambers_source_url", lambda _value: False)
    monkeypatch.setattr(public_record_refresh, "_is_chambers_search_url", lambda _value: True)
    with pytest.raises(PublicRecordRefreshError, match="uses a Chambers search URL"):
        public_record_refresh._validate_authoritative_source(
            name="Alpha LLP",
            state="France",
            website="https://alpha.example",
            source_label="Official directory",
            source_url="https://www.chambers.com/search?query=alpha",
        )

    ca_rule = US_STATE_AUTHORITATIVE_SOURCES["CA"]
    monkeypatch.setattr(
        public_record_refresh,
        "US_STATE_AUTHORITATIVE_SOURCES",
        {"NY": US_STATE_AUTHORITATIVE_SOURCES["NY"]},
    )
    with pytest.raises(
        PublicRecordRefreshError,
        match="missing an authoritative source rule for state 'CA'",
    ):
        public_record_refresh._validate_us_state_source_policy(
            name="Alpha LLP",
            state="CA",
            source_label=ca_rule["source_label"],
            source_url="https://apps.calbar.ca.gov/attorney/Licensee/Detail/350631",
        )

    monkeypatch.setattr(
        public_record_refresh,
        "US_STATE_AUTHORITATIVE_SOURCES",
        {"CA": ca_rule},
    )
    with pytest.raises(PublicRecordRefreshError, match="invalid source_url hostname"):
        public_record_refresh._validate_us_state_source_policy(
            name="Alpha LLP",
            state="CA",
            source_label=ca_rule["source_label"],
            source_url="not a url",
        )
    with pytest.raises(
        PublicRecordRefreshError, match="source_url host 'example.test' is not allowed"
    ):
        public_record_refresh._validate_us_state_source_policy(
            name="Alpha LLP",
            state="CA",
            source_label=ca_rule["source_label"],
            source_url="https://example.test/record/alpha",
        )


def test_validate_links_skips_empty_fields_and_region_lookup_requires_mapping() -> None:
    row = _NormalizedListing(
        id="seed-one",
        slug="public-record~seed-one",
        name="Seed One",
        website="https://example.test/profile",
        description="Seed One description",
        city="City",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="California Bar public directory",
        source_url=None,
        region="US",
    )
    checked_urls: list[str] = []

    def link_checker(url: str) -> LinkCheckResult:
        checked_urls.append(url)
        return LinkCheckResult(ok=True, definitive_failure=False, reason=None)

    result = public_record_refresh._validate_links([row], link_checker, drop_failed_links=True)
    assert result.rows == [row]
    assert result.checked_url_count == 1
    assert checked_urls == ["https://example.test/profile"]

    with pytest.raises(
        PublicRecordRefreshError,
        match="State/country 'Atlantis' does not map to any configured region",
    ):
        public_record_refresh._region_for_state("Atlantis", {"US": frozenset({"CA"})})


def test_discover_chambers_public_record_rows_is_disabled() -> None:
    with pytest.raises(PublicRecordRefreshError, match="Chambers discovery is disabled"):
        discover_chambers_public_record_rows(
            [],
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
        )


def test_discover_official_us_state_public_record_rows_strict_accepts_full_coverage() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"CA", "NY"})},
        strict_state_adapter_coverage=True,
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state["NY"] > 0
    assert result.added_count_by_state["CA"] > 0


def test_official_source_adapter_harness_covers_current_implemented_states() -> None:
    assert set(_IMPLEMENTED_OFFICIAL_SOURCE_STATES) == set(US_STATE_CODES)


@pytest.mark.parametrize("state_code", _IMPLEMENTED_OFFICIAL_SOURCE_STATES)
def test_official_source_adapter_harness_validates_state_outputs(state_code: str) -> None:
    result = _discover_rows_for_state(state_code=state_code, existing_rows=[])

    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: len(result.rows)}
    assert_official_source_adapter_rows(state_code, result.rows)


@pytest.mark.parametrize("state_code", _IMPLEMENTED_OFFICIAL_SOURCE_STATES)
@pytest.mark.parametrize("collision", ["id", "slug", "name"])
def test_official_source_adapter_harness_skips_existing_rows(
    state_code: str,
    collision: str,
) -> None:
    baseline = _discover_rows_for_state(state_code=state_code, existing_rows=[])
    assert baseline.unsupported_states == ()
    assert baseline.rows

    existing_row = build_existing_row_for_collision(
        baseline.rows[0],
        collision=collision,
    )
    result = _discover_rows_for_state(state_code=state_code, existing_rows=[existing_row])

    expected_count = len(baseline.rows) - 1
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: expected_count}
    assert len(result.rows) == expected_count
    if result.rows:
        assert_official_source_adapter_rows(state_code, result.rows)


def test_discover_official_us_state_public_record_rows_adds_california_seeds() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"CA"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {"CA": 9}
    assert len(result.rows) == 9

    by_name = {row["name"]: row for row in result.rows}
    assert by_name["Jeffrey Farley Keller"]["state"] == "CA"
    assert by_name["Jeffrey Farley Keller"]["source_label"] == (
        "State Bar of California attorney profile"
    )
    assert by_name["Jeffrey Farley Keller"]["source_url"] == (
        "https://apps.calbar.ca.gov/attorney/Licensee/Detail/148005"
    )

    assert by_name["Daniel Noel"]["state"] == "CA"
    assert by_name["Daniel Noel"]["source_label"] == "State Bar of California attorney profile"
    assert by_name["Daniel Noel"]["source_url"] == (
        "https://apps.calbar.ca.gov/attorney/Licensee/Detail/339078"
    )

    assert by_name["Elizabeth Aida Acevedo"]["state"] == "CA"
    assert by_name["Elizabeth Aida Acevedo"]["source_url"] == (
        "https://apps.calbar.ca.gov/attorney/Licensee/Detail/227347"
    )

    assert by_name["Cara Whittaker Van Dorn"]["state"] == "CA"
    assert by_name["Cara Whittaker Van Dorn"]["source_url"] == (
        "https://apps.calbar.ca.gov/attorney/Licensee/Detail/321669"
    )


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_ONE_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_TWO_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_two_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_THREE_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_three_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_FOUR_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_four_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_FIVE_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_five_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_SIX_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_six_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_SEVEN_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_seven_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_EIGHT_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_eight_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    (
        "state_code",
        "expected_id",
        "expected_slug",
        "expected_name",
        "expected_source_label",
        "expected_source_url",
    ),
    _BATCH_NINE_STATE_SEEDS,
)
def test_discover_official_us_state_public_record_rows_adds_batch_nine_seed(  # noqa: PLR0913
    state_code: str,
    expected_id: str,
    expected_slug: str,
    expected_name: str,
    expected_source_label: str,
    expected_source_url: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {state_code: 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["id"] == expected_id
    assert row["slug"] == expected_slug
    assert row["name"] == expected_name
    assert row["state"] == state_code
    assert row["source_label"] == expected_source_label
    assert row["source_url"] == expected_source_url


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_ONE_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_TWO_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_two_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_FOUR_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_four_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_THREE_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_three_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_FIVE_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_five_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_SIX_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_six_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_SEVEN_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_seven_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_EIGHT_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_eight_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


@pytest.mark.parametrize(
    ("state_code", "existing_id", "existing_slug", "existing_name"),
    _BATCH_NINE_EXISTING_COLLISION_CASES,
)
def test_discover_official_us_state_public_record_rows_skips_existing_batch_nine_seed(
    state_code: str,
    existing_id: str,
    existing_slug: str,
    existing_name: str,
) -> None:
    result = discover_official_us_state_public_record_rows(
        [{"id": existing_id, "name": existing_name, "slug": existing_slug}],
        selected_regions=["US"],
        region_state_map={"US": frozenset({state_code})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {state_code: 0}
    assert result.unsupported_states == ()


def test_discover_official_us_state_public_record_rows_adds_washington_seed() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"WA"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {"WA": 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["name"] == "Barbara Mahoney"
    assert row["state"] == "WA"
    assert row["source_label"] == "Washington State Bar Association legal directory"
    assert row["source_url"] == (
        "https://www.mywsba.org/PersonifyEbusiness/Default.aspx?TabID=1538&Usr_ID=31845"
    )


def test_discover_official_us_state_public_record_rows_skips_existing_washington_seed() -> None:
    result = discover_official_us_state_public_record_rows(
        [
            {
                "id": "seed-barbara-mahoney",
                "name": "Barbara Mahoney",
                "slug": "public-record~barbara-mahoney",
            }
        ],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"WA"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"WA": 0}
    assert result.unsupported_states == ()


def test_discover_official_us_state_public_record_rows_adds_ohio_seed() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"OH"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {"OH": 1}
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["name"] == "Alissa Jacqueline Sammarco"
    assert row["state"] == "OH"
    assert row["source_label"] == "Supreme Court of Ohio attorney directory"
    assert row["source_url"] == (
        "https://www.supremecourt.ohio.gov/AttorneySearch/#/77563/attyinfo"
    )


def test_discover_official_us_state_public_record_rows_skips_existing_ohio_seed() -> None:
    result = discover_official_us_state_public_record_rows(
        [
            {
                "id": "seed-alissa-jacqueline-sammarco",
                "name": "Alissa Jacqueline Sammarco",
                "slug": "public-record~alissa-jacqueline-sammarco",
            }
        ],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"OH"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"OH": 0}
    assert result.unsupported_states == ()


def test_discover_official_us_state_public_record_rows_adds_tennessee_seeds() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"TN"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {"TN": 5}
    assert len(result.rows) == 5

    by_name = {row["name"]: row for row in result.rows}
    assert by_name["Kevin Hunter Sharp"]["state"] == "TN"
    assert by_name["Kevin Hunter Sharp"]["source_label"] == (
        "Tennessee Board of Professional Responsibility attorney records"
    )
    assert by_name["Kevin Hunter Sharp"]["source_url"] == "https://www.tbpr.org/attorneys/016287"

    assert by_name["Jonathan Patrick Tepe"]["state"] == "TN"
    assert by_name["Jonathan Patrick Tepe"]["source_url"] == (
        "https://www.tbpr.org/attorneys/037266"
    )

    assert by_name["Michael Joseph Lockman"]["state"] == "TN"
    assert by_name["Michael Joseph Lockman"]["source_url"] == (
        "https://www.tbpr.org/attorneys/039797"
    )

    assert by_name["Kasi Lynn Wautlet"]["state"] == "TN"
    assert by_name["Kasi Lynn Wautlet"]["source_url"] == "https://www.tbpr.org/attorneys/038688"

    assert by_name["David Bragg McNamee"]["state"] == "TN"
    assert by_name["David Bragg McNamee"]["source_url"] == ("https://www.tbpr.org/attorneys/038124")


def test_discover_official_us_state_public_record_rows_skips_existing_tennessee_seeds() -> None:
    result = discover_official_us_state_public_record_rows(
        [
            {
                "id": "seed-kevin-hunter-sharp",
                "name": "Kevin Hunter Sharp",
                "slug": "public-record~kevin-hunter-sharp",
            },
            {
                "id": "seed-jonathan-patrick-tepe",
                "name": "Jonathan Patrick Tepe",
                "slug": "public-record~jonathan-patrick-tepe",
            },
            {
                "id": "seed-michael-joseph-lockman",
                "name": "Michael Joseph Lockman",
                "slug": "public-record~michael-joseph-lockman",
            },
            {
                "id": "seed-kasi-lynn-wautlet",
                "name": "Kasi Lynn Wautlet",
                "slug": "public-record~kasi-lynn-wautlet",
            },
            {
                "id": "seed-david-bragg-mcnamee",
                "name": "David Bragg McNamee",
                "slug": "public-record~david-bragg-mcnamee",
            },
        ],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"TN"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"TN": 0}
    assert result.unsupported_states == ()


def test_discover_official_us_state_public_record_rows_adds_illinois_seeds() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"IL"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state == {"IL": 4}
    assert len(result.rows) == 4

    by_name = {row["name"]: row for row in result.rows}
    assert by_name["Douglas Michael Werman"]["state"] == "IL"
    assert by_name["Douglas Michael Werman"]["source_label"] == (
        "Illinois ARDC attorney registration records"
    )
    assert by_name["Douglas Michael Werman"]["source_url"] == (
        "https://www.iardc.org/Lawyer/PrintableDetails/"
        "00034ffd-aa64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
    )

    assert by_name["Amy Elisabeth Keller"]["state"] == "IL"
    assert by_name["Amy Elisabeth Keller"]["source_label"] == (
        "Illinois ARDC attorney registration records"
    )
    assert by_name["Amy Elisabeth Keller"]["source_url"] == (
        "https://www.iardc.org/Lawyer/PrintableDetails/"
        "f22e492e-aa64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
    )

    assert by_name["Adam J. Levitt"]["state"] == "IL"
    assert by_name["Adam J. Levitt"]["source_url"] == (
        "https://www.iardc.org/Lawyer/PrintableDetails/"
        "a1420f47-ab64-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
    )

    assert by_name["Daniel Richard Ferri"]["state"] == "IL"
    assert by_name["Daniel Richard Ferri"]["source_url"] == (
        "https://www.iardc.org/Lawyer/PrintableDetails/"
        "4b9c1c91-a964-eb11-b810-000d3a9f4eeb?includeFormerNames=False"
    )


def test_discover_official_us_state_public_record_rows_skips_existing_illinois_seeds() -> None:
    result = discover_official_us_state_public_record_rows(
        [
            {
                "id": "seed-adam-j-levitt",
                "name": "Adam J. Levitt",
                "slug": "public-record~adam-j-levitt",
            },
            {
                "id": "seed-daniel-richard-ferri",
                "name": "Daniel Richard Ferri",
                "slug": "public-record~daniel-richard-ferri",
            },
            {
                "id": "seed-douglas-michael-werman",
                "name": "Douglas Michael Werman",
                "slug": "public-record~douglas-michael-werman",
            },
            {
                "id": "seed-amy-elisabeth-keller",
                "name": "Amy Elisabeth Keller",
                "slug": "public-record~amy-elisabeth-keller",
            },
        ],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"IL"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"IL": 0}
    assert result.unsupported_states == ()

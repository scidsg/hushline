from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

import pytest

from hushline.public_record_refresh import (
    DEFAULT_REGION_STATE_MAP,
    OFFICIAL_US_STATE_DISCOVERY_ADAPTERS,
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    LinkCheckResult,
    OfficialStateDiscoveryResult,
    PublicRecordRefreshError,
    build_requests_link_checker,
    discover_chambers_public_record_rows,
    discover_official_us_state_public_record_rows,
    refresh_public_record_rows,
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
        (
            "https://www.arkbar.com/network/members/profile"
            "?UserKey=10e2c501-bea8-4749-913c-0d6e319cdff6"
        ),
    ),
    (
        "AZ",
        "seed-anthony-cali",
        "public-record~anthony-cali",
        "Anthony Cali",
        "State Bar of Arizona public directory",
        "https://www.azbar.org/for-the-public/find-a-lawyer-results/?m=Anthony-Cali-177781",
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


def _row(  # noqa: PLR0913
    *,
    id_value: str | None,
    slug: str | None,
    name: str,
    state: str,
    website: str,
    source_url: str | None = None,
) -> dict[str, object]:
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
    return row


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
        return LinkCheckResult(ok=url != "https://broken.example", reason="HTTP 404")

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


def test_discover_chambers_public_record_rows_is_disabled() -> None:
    with pytest.raises(PublicRecordRefreshError, match="Chambers discovery is disabled"):
        discover_chambers_public_record_rows(
            [],
            selected_regions=["US"],
            region_state_map={"US": frozenset({"NY"})},
        )


def test_discover_official_us_state_public_record_rows_includes_noop_states() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"NY"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"NY": 0}
    assert result.unsupported_states == ()


def test_discover_official_us_state_public_record_rows_strict_accepts_full_coverage() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"CA", "NY"})},
        strict_state_adapter_coverage=True,
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.unsupported_states == ()
    assert result.added_count_by_state["NY"] == 0
    assert result.added_count_by_state["CA"] > 0


def test_official_source_adapter_harness_covers_current_implemented_states() -> None:
    assert {"AK", "AL", "AR", "AZ", "CA", "CO", "IL", "OH", "TN", "WA"}.issubset(
        _IMPLEMENTED_OFFICIAL_SOURCE_STATES
    )


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
def test_discover_official_us_state_public_record_rows_adds_batch_one_seed(  # noqa: PLR0913
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
def test_discover_official_us_state_public_record_rows_skips_existing_batch_one_seed(
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

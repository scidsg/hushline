from __future__ import annotations

import re
from typing import Any

import pytest

from hushline.public_record_refresh import (
    DEFAULT_REGION_STATE_MAP,
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


def test_discover_official_us_state_public_record_rows_reports_unsupported_states() -> None:
    result = discover_official_us_state_public_record_rows(
        [],
        selected_regions=["US"],
        region_state_map={"US": frozenset({"CA", "NY"})},
    )

    assert isinstance(result, OfficialStateDiscoveryResult)
    assert result.rows == []
    assert result.added_count_by_state == {"CA": 0}
    assert result.unsupported_states == ("NY",)


def test_discover_official_us_state_public_record_rows_strict_requires_full_coverage() -> None:
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

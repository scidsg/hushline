from __future__ import annotations

from typing import Any

import pytest

from hushline.public_record_refresh import (
    LinkCheckResult,
    PublicRecordRefreshError,
    build_requests_link_checker,
    discover_chambers_public_record_rows,
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
    row: dict[str, object] = {
        "name": name,
        "website": website,
        "description": f"{name} description",
        "city": "New York",
        "state": state,
        "practice_tags": ["Whistleblowing", "Investigations"],
        "source_label": "Seed dataset from official firm website",
        "source_url": source_url or website,
    }
    if id_value is not None:
        row["id"] = id_value
    if slug is not None:
        row["slug"] = slug
    return row


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
    assert len(flagged.link_failures) == 2
    assert flagged.dropped_record_ids == []
    assert flagged.checked_url_count == 2

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
    assert dropped.checked_url_count == 2
    assert checked_urls


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


class _DiscoveryFakeResponse:
    def __init__(self, *, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload

    def close(self) -> None:
        return None


class _DiscoveryFakeSession:
    def __init__(self, responses: dict[str, _DiscoveryFakeResponse]) -> None:
        self._responses = responses
        self.headers: dict[str, str] = {}
        self.requested_urls: list[str] = []

    def get(self, url: str, *_args: Any, **_kwargs: Any) -> _DiscoveryFakeResponse:
        self.requested_urls.append(url)
        return self._responses.get(
            url,
            _DiscoveryFakeResponse(status_code=404, payload={"error": "not found"}),
        )


def _ranked_index_url(group_id: int) -> str:
    return (
        f"https://chamberssitemap.blob.core.windows.net/site-json/organisations/ranked/{group_id}"
    )


def _profile_basics_url(organisation_id: int, group_id: int) -> str:
    return (
        "https://profiles-portal.chambers.com/api/organisations/"
        f"{organisation_id}/profile-basics?groupId={group_id}"
    )


def _ranked_offices_url(organisation_id: int, group_id: int) -> str:
    return (
        "https://profiles-portal.chambers.com/api/organisations/"
        f"{organisation_id}/ranked-offices?groupId={group_id}"
    )


def _ranked_departments_url(organisation_id: int, group_id: int) -> str:
    return (
        "https://ranking-tables.chambers.com/api/organisations/"
        f"{organisation_id}/ranked-departments?groupId={group_id}"
    )


def test_discover_chambers_public_record_rows_adds_new_us_law_firm() -> None:
    existing_rows = [
        _row(
            id_value="seed-ao-shearman",
            slug="public-record~ao-shearman",
            name="A&O Shearman",
            state="NY",
            website="https://www.aoshearman.com/",
        )
    ]
    responses = {
        _ranked_index_url(5): _DiscoveryFakeResponse(
            status_code=200,
            payload=[
                {"oid": 7, "on": "A&O Shearman", "ptgid": 5},
                {"oid": 67329, "on": "Cohen Milstein Sellers & Toll PLLC", "ptgid": 5},
            ],
        ),
        _profile_basics_url(67329, 5): _DiscoveryFakeResponse(
            status_code=200,
            payload={
                "organisationTypeId": 1,
                "webLink": "https://www.cohenmilstein.com/",
            },
        ),
        _ranked_offices_url(67329, 5): _DiscoveryFakeResponse(
            status_code=200,
            payload={
                "headOffice": {
                    "country": "USA",
                    "region": "District of Columbia",
                    "town": "Washington",
                    "webLink": "https://www.cohenmilstein.com/",
                },
                "locations": [],
            },
        ),
        _ranked_departments_url(67329, 5): _DiscoveryFakeResponse(
            status_code=200,
            payload=[
                {"practiceAreaName": ("Litigation: White Collar Crime & Government Investigations")}
            ],
        ),
    }
    session = _DiscoveryFakeSession(responses)

    result = discover_chambers_public_record_rows(
        existing_rows,
        selected_regions=["US"],
        region_state_map={"US": frozenset({"DC", "NY"})},
        max_new_per_region=5,
        session=session,  # type: ignore[arg-type]
    )

    assert result.scanned_count_by_region == {"US": 2}
    assert result.added_count_by_region == {"US": 1}
    assert len(result.rows) == 1
    added = result.rows[0]
    assert added["name"] == "Cohen Milstein Sellers & Toll PLLC"
    assert added["website"] == "https://www.cohenmilstein.com/"
    assert added["city"] == "Washington"
    assert added["state"] == "DC"
    assert added["source_url"] == (
        "https://profiles-portal.chambers.com/api/organisations/67329/profile-basics?groupId=5"
    )
    assert "Investigations" in added["practice_tags"]
    assert all("/organisations/7/" not in url for url in session.requested_urls)


def test_discover_chambers_public_record_rows_filters_non_law_firm_and_location() -> None:
    responses = {
        _ranked_index_url(8): _DiscoveryFakeResponse(
            status_code=200,
            payload=[
                {"oid": 100, "on": "Example Chambers", "ptgid": 8},
                {"oid": 200, "on": "Bangladesh Legal LLP", "ptgid": 8},
                {"oid": 300, "on": "Singapore Legal LLP", "ptgid": 8},
            ],
        ),
        _profile_basics_url(100, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload={"organisationTypeId": 2, "webLink": "https://example.invalid"},
        ),
        _profile_basics_url(200, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload={"organisationTypeId": 1, "webLink": "https://bangladesh.example"},
        ),
        _ranked_offices_url(200, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload={
                "headOffice": {
                    "country": "Bangladesh",
                    "region": "Dhaka",
                    "town": "Dhaka",
                    "webLink": "https://bangladesh.example",
                },
                "locations": [],
            },
        ),
        _profile_basics_url(300, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload={"organisationTypeId": 1, "webLink": None},
        ),
        _ranked_offices_url(300, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload={
                "headOffice": {
                    "country": "Singapore",
                    "region": "Singapore Island",
                    "town": "Singapore",
                    "webLink": "https://singapore.example",
                },
                "locations": [],
            },
        ),
        _ranked_departments_url(300, 8): _DiscoveryFakeResponse(
            status_code=200,
            payload=[],
        ),
    }
    session = _DiscoveryFakeSession(responses)

    result = discover_chambers_public_record_rows(
        [],
        selected_regions=["APAC"],
        region_state_map={"APAC": frozenset({"Singapore"})},
        max_new_per_region=3,
        session=session,  # type: ignore[arg-type]
    )

    assert result.scanned_count_by_region == {"APAC": 3}
    assert result.added_count_by_region == {"APAC": 1}
    assert len(result.rows) == 1
    added = result.rows[0]
    assert added["name"] == "Singapore Legal LLP"
    assert added["website"] == "https://singapore.example"
    assert added["city"] == "Singapore"
    assert added["state"] == "Singapore"
    assert added["practice_tags"] == ["Whistleblowing", "Investigations", "Employment"]

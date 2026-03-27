from __future__ import annotations

import pytest
import requests

import hushline.newsroom_directory_refresh as refresh_module
from hushline.newsroom_directory_refresh import (
    NEWSROOM_DIRECTORY_SOURCE_URL,
    NewsroomDirectoryRefreshError,
    _extract_organization_urls,
    _normalize_http_url,
    _normalize_string_list,
    _parse_location,
    fetch_newsroom_directory_rows,
    refresh_newsroom_directory_rows,
    render_newsroom_refresh_summary,
)


class _FakeResponse:
    def __init__(self, text: str, *, error: requests.RequestException | None = None) -> None:
        self.text = text
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error


class _FakeSession:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
        assert timeout == 30.0
        assert "HushlineNewsroomSync" in headers["User-Agent"]
        self.requested_urls.append(url)
        return self.responses[url]


class _ErrorSession:
    def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
        raise requests.Timeout(f"timed out fetching {url}")


def test_normalize_string_list_handles_split_deduping_and_invalid_inputs() -> None:
    assert _normalize_string_list(" English | Spanish ; english ,, ") == ["English", "Spanish"]
    assert _normalize_string_list(["Investigations", 1, " investigations ", "", "Local"]) == [
        "Investigations",
        "Local",
    ]
    assert _normalize_string_list({"topics": ["Investigations"]}) == []


def test_normalize_http_url_validates_required_and_optional_fields() -> None:
    assert (
        _normalize_http_url(
            " https://findyournews.org/organization/sample/ ",
            field="directory_url",
            required=True,
        )
        == "https://findyournews.org/organization/sample/"
    )
    assert _normalize_http_url("mailto:test@example.org", field="website", required=False) == ""
    assert _normalize_http_url("   ", field="website", required=False) == ""

    with pytest.raises(
        NewsroomDirectoryRefreshError, match="Missing required URL field: directory_url"
    ):
        _normalize_http_url(None, field="directory_url", required=True)


def test_extract_organization_urls_filters_duplicates_and_non_listing_links() -> None:
    urls = _extract_organization_urls(
        """
        <html>
          <body>
            <a href="/explore/">Explore</a>
            <a href="https://findyournews.org/organization/sample-one/">Sample One</a>
            <a href="https://findyournews.org/organization/sample-two/">Sample Two</a>
            <a href="https://findyournews.org/organization/sample-two/">Sample Two Again</a>
            <a href="https://example.org/organization/not-in-scope/">Other Host</a>
          </body>
        </html>
        """,
        source_url=NEWSROOM_DIRECTORY_SOURCE_URL,
    )

    assert urls == [
        "https://findyournews.org/organization/sample-one/",
        "https://findyournews.org/organization/sample-two/",
    ]


def test_parse_location_normalizes_united_states_and_state_abbreviations() -> None:
    normalized = _parse_location("Chicago, IL, UNITED STATES")

    assert normalized["city"] == "Chicago"
    assert normalized["country"] == "United States"
    assert normalized["subdivision"] == "Illinois"
    assert normalized["countries"] == ["United States"]


def test_refresh_newsroom_directory_rows_validates_normalized_row_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows_iter = iter(
        [
            {"id": 1, "slug": "newsroom~one", "name": "One"},
            {"id": "newsroom-two", "slug": 1, "name": "Two"},
        ]
    )

    def fake_normalize(
        row: dict[str, object],
        *,
        source_label: str,
        source_url: str,
    ) -> dict[str, object]:
        return next(rows_iter)

    monkeypatch.setattr(refresh_module, "_normalize_newsroom_row", fake_normalize)

    with pytest.raises(NewsroomDirectoryRefreshError, match="Normalized row id must be a string"):
        refresh_newsroom_directory_rows([{}, {}])


def test_refresh_newsroom_directory_rows_is_deterministic_and_schema_compatible() -> None:
    rows = [
        {
            "id": "newsroom-chicago-reporter",
            "slug": "newsroom~chicago-reporter",
            "name": "Chicago Reporter",
            "website": "https://www.chicagoreporter.com",
            "description": "",
            "directory_url": "https://findyournews.org/organization/chicago-reporter/",
            "tagline": "Investigative nonprofit newsroom",
            "mission": "",
            "about": "",
            "city": "Chicago",
            "country": "UNITED STATES",
            "subdivision": "IL",
            "countries": ["UNITED STATES"],
            "places_covered": ["Chicago", "Illinois", "chicago"],
            "languages": ["English", "english"],
            "topics": ["Accountability", "Education", "accountability"],
            "reach": "Local",
            "year_founded": "1972",
            "source_label": "INN Find Your News directory",
            "source_url": "https://findyournews.org/organization/chicago-reporter/",
        },
        {
            "id": "newsroom-afrola",
            "slug": "newsroom~afrola",
            "name": "AfroLA",
            "website": "https://afrola.org",
            "description": "Community newsroom",
            "directory_url": "https://findyournews.org/organization/afrola/",
            "tagline": "",
            "mission": "",
            "about": "",
            "city": "Los Angeles",
            "country": "United States",
            "subdivision": "California",
            "countries": ["United States"],
            "places_covered": ["Los Angeles"],
            "languages": ["English"],
            "topics": ["Community"],
            "reach": "Local",
            "year_founded": "2020",
            "source_label": "INN Find Your News directory",
            "source_url": "https://findyournews.org/organization/afrola/",
        },
    ]

    result_a = refresh_newsroom_directory_rows(rows)
    result_b = refresh_newsroom_directory_rows(rows)

    assert result_a == result_b
    assert [row["name"] for row in result_a] == ["AfroLA", "Chicago Reporter"]
    assert result_a[1]["description"] == "Investigative nonprofit newsroom"
    assert result_a[1]["country"] == "United States"
    assert result_a[1]["subdivision"] == "Illinois"
    assert result_a[1]["countries"] == ["United States"]
    assert result_a[1]["places_covered"] == ["Chicago", "Illinois"]
    assert result_a[1]["languages"] == ["English"]
    assert result_a[1]["topics"] == ["Accountability", "Education"]


def test_fetch_newsroom_directory_rows_uses_public_explore_urls_only() -> None:
    explore_html = """
    <html>
      <body>
        <a href="https://findyournews.org/organization/sample-one/">Sample One</a>
        <a href="https://findyournews.org/organization/sample-two/">Sample Two</a>
      </body>
    </html>
    """
    detail_html = """
    <div class="hero-organization">
      <h1>Sample One</h1>
      <h4>Investigative nonprofit newsroom</h4>
    </div>
    <div class="panel-content core-details">
      <h6>Location</h6><hr><p class="small">Chicago, IL, UNITED STATES</p>
      <h6>Places Covered</h6><hr><p class="small"><a>Chicago</a>, <a>Illinois</a></p>
      <h6>Topics</h6><hr><p class="small"><a>Corruption</a></p>
      <h6>Languages</h6><hr><p class="small"><a>English</a></p>
      <h6>Reach</h6><hr><p class="small">Local</p>
      <h6>Year Founded</h6><hr><p class="small">2018</p>
    </div>
    <div class="text-block"><h6>Mission</h6><p>Mission text</p></div>
    <div class="text-block"><h6>About our journalism</h6><p>About text</p></div>
    <a href="https://example.org" id="button-website">Website</a>
    """
    responses = {
        NEWSROOM_DIRECTORY_SOURCE_URL: _FakeResponse(explore_html),
        "https://findyournews.org/organization/sample-one/": _FakeResponse(detail_html),
        "https://findyournews.org/organization/sample-two/": _FakeResponse(
            detail_html.replace("Sample One", "Sample Two", 1)
        ),
    }

    rows = fetch_newsroom_directory_rows(session=_FakeSession(responses))

    assert len(rows) == 2
    assert rows[0]["id"] == "newsroom-sample-one"
    assert rows[0]["country"] == "United States"
    assert rows[0]["subdivision"] == "Illinois"
    assert rows[0]["source_url"] == "https://findyournews.org/organization/sample-one/"
    assert rows[1]["id"] == "newsroom-sample-two"


def test_fetch_newsroom_directory_rows_wraps_request_errors() -> None:
    with pytest.raises(
        NewsroomDirectoryRefreshError, match="Failed to fetch INN Find Your News listings"
    ):
        fetch_newsroom_directory_rows(session=_ErrorSession())


def test_fetch_newsroom_directory_rows_retries_transient_gateway_timeout() -> None:
    gateway_timeout = requests.HTTPError("gateway timeout")
    gateway_timeout.response = requests.Response()
    gateway_timeout.response.status_code = 504

    class _RetrySession:
        def __init__(self) -> None:
            self.attempts = 0

        def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
            assert timeout == 30.0
            assert "HushlineNewsroomSync" in headers["User-Agent"]
            if url == NEWSROOM_DIRECTORY_SOURCE_URL:
                return _FakeResponse(
                    '<a href="https://findyournews.org/organization/sample-one/">Sample One</a>'
                )
            self.attempts += 1
            if self.attempts == 1:
                return _FakeResponse("", error=gateway_timeout)
            return _FakeResponse(
                """
                <div class="hero-organization"><h1>Sample One</h1><h4>Tagline</h4></div>
                <div class="panel-content core-details">
                  <h6>Location</h6><hr><p class="small">Chicago, IL, UNITED STATES</p>
                </div>
                <a href="https://example.org" id="button-website">Website</a>
                """
            )

    rows = fetch_newsroom_directory_rows(session=_RetrySession())

    assert len(rows) == 1
    assert rows[0]["id"] == "newsroom-sample-one"


def test_render_newsroom_refresh_summary_includes_counts() -> None:
    summary = render_newsroom_refresh_summary(
        source_url=NEWSROOM_DIRECTORY_SOURCE_URL,
        total_count=566,
        added_count=5,
        removed_count=2,
        updated_count=11,
    )

    assert "## Newsroom Directory Refresh Summary" in summary
    assert "- Source: https://findyournews.org/explore/" in summary
    assert "- Total newsrooms: 566" in summary
    assert "- Added newsrooms: 5" in summary
    assert "- Removed newsrooms: 2" in summary
    assert "- Updated newsrooms: 11" in summary

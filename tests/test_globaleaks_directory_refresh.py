from __future__ import annotations

import pytest
import requests

from hushline import globaleaks_directory_refresh as refresh_module
from hushline.globaleaks_directory_refresh import (
    GLOBALEAKS_SOURCE_URL,
    GlobaLeaksDirectoryRefreshError,
    _candidate_hosts,
    _choose_host,
    _choose_submission_url,
    _extract_discovery_links,
    _index_known_rows_by_host,
    _infer_scheme,
    _normalize_http_url,
    _normalize_string_list,
    fetch_globaleaks_directory_rows,
    refresh_globaleaks_directory_rows,
    render_globaleaks_refresh_summary,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeSession:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
        assert timeout == 30.0
        assert "HushlineGlobaLeaksSync" in headers["User-Agent"]
        self.requested_urls.append(url)
        return self.responses[url]


class _ErrorSession:
    def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
        raise requests.Timeout(f"timed out fetching {url}")


def test_normalize_string_list_handles_split_deduping_and_invalid_inputs() -> None:
    assert _normalize_string_list(" English | Italian ; english ,, ") == ["English", "Italian"]
    assert _normalize_string_list(["French", 1, " french ", "", "German"]) == ["French", "German"]
    assert _normalize_string_list({"languages": ["English"]}) == []


def test_normalize_http_url_validates_required_and_optional_fields() -> None:
    assert (
        _normalize_http_url(
            " https://submit.example.org/report ",
            field="submission_url",
            required=True,
        )
        == "https://submit.example.org/report"
    )
    assert _normalize_http_url("mailto:test@example.org", field="website", required=False) == ""
    assert _normalize_http_url("   ", field="website", required=False) == ""

    with pytest.raises(
        GlobaLeaksDirectoryRefreshError, match="Missing required URL field: source_url"
    ):
        _normalize_http_url(None, field="source_url", required=True)

    with pytest.raises(
        GlobaLeaksDirectoryRefreshError, match="Missing required URL field: source_url"
    ):
        _normalize_http_url("   ", field="source_url", required=True)


def test_infer_scheme_uses_port_module_cert_and_http_fallback() -> None:
    assert _infer_scheme({"port": "443"}) == "https"
    assert _infer_scheme({"_shodan": {"module": "https-simple-new"}}) == "https"
    assert _infer_scheme({"ssl.cert.subject.cn": "secure.example.org"}) == "https"
    assert _infer_scheme({"port": 80, "module": "http-simple-new"}) == "http"


def test_choose_submission_url_uses_website_http_location_and_host_fallbacks() -> None:
    assert (
        _choose_submission_url({"website": "https://site.example.org/"})
        == "https://site.example.org/"
    )
    assert (
        _choose_submission_url(
            {
                "website": "ftp://site.example.org/",
                "http.location": "https://submit.example.org/form",
            }
        )
        == "https://submit.example.org/form"
    )
    assert _choose_submission_url(
        {"hostnames": "Tips.example.org | tips.example.org", "port": "443"}
    ) == ("https://tips.example.org/")


def test_choose_host_falls_back_to_candidate_hosts_or_errors() -> None:
    assert _choose_host(
        {"ssl.cert.subject.cn": "Secure.Example.org."}, "mailto:test@example.org"
    ) == ("secure.example.org")

    with pytest.raises(GlobaLeaksDirectoryRefreshError, match="missing a usable host"):
        _choose_host({}, "mailto:test@example.org")


def test_candidate_hosts_normalizes_and_skips_blank_or_duplicate_values() -> None:
    assert _candidate_hosts(
        {
            "host": " Tips.Example.org ",
            "domains": ["https://tips.example.org/report", ".", "tips.example.org"],
            "_shodan": {"http": {"host": " "}},
        }
    ) == ["tips.example.org"]


def test_refresh_globaleaks_directory_rows_rejects_empty_slug_after_normalization() -> None:
    with pytest.raises(GlobaLeaksDirectoryRefreshError, match="slug normalized to an empty value"):
        refresh_globaleaks_directory_rows([{"host": "!!!"}])


@pytest.mark.parametrize(
    ("normalized_rows", "message"),
    [
        (
            [{"id": 1, "slug": "globaleaks~one", "name": "One"}],
            "Normalized row id must be a string",
        ),
        (
            [{"id": "globaleaks-one", "slug": 1, "name": "One"}],
            "Normalized row slug must be a string",
        ),
        (
            [
                {"id": "globaleaks-one", "slug": "globaleaks~shared", "name": "One"},
                {"id": "globaleaks-two", "slug": "globaleaks~shared", "name": "Two"},
            ],
            "Duplicate GlobaLeaks listing slug: globaleaks~shared",
        ),
    ],
)
def test_refresh_globaleaks_directory_rows_validates_normalized_row_shapes(
    monkeypatch: pytest.MonkeyPatch,
    normalized_rows: list[dict[str, object]],
    message: str,
) -> None:
    rows_iter = iter(normalized_rows)

    def fake_normalize(
        row: dict[str, object],
        *,
        source_label: str,
        source_url: str,
    ) -> dict[str, object]:
        return next(rows_iter)

    monkeypatch.setattr(refresh_module, "_normalize_globaleaks_row", fake_normalize)

    with pytest.raises(GlobaLeaksDirectoryRefreshError, match=message):
        refresh_globaleaks_directory_rows([{} for _ in normalized_rows])


def test_index_known_rows_by_host_ignores_blank_url_fields() -> None:
    indexed = _index_known_rows_by_host(
        [
            {
                "host": "known.example.org",
                "website": " ",
                "submission_url": None,
            }
        ]
    )

    assert indexed == {
        "known.example.org": {
            "host": "known.example.org",
            "website": " ",
            "submission_url": None,
        }
    }


def test_extract_discovery_links_filters_excluded_duplicate_and_non_candidate_hosts() -> None:
    links = _extract_discovery_links(
        """
        <html>
          <body>
            <a href="/relative">Relative</a>
            <a href="https://www.globaleaks.org/usecases/anti-corruption/">Source</a>
            <a href="https://github.com/globaleaks/globaleaks">GitHub</a>
            <a href="https://plain.example.org/about">Plain</a>
            <a href="https://tip.example.org/submit">Tip Desk</a>
            <a href="https://tip.example.org/other">Tip Desk Duplicate</a>
            <a href="https://known.example.org/"> </a>
          </body>
        </html>
        """,
        source_url="https://www.globaleaks.org/usecases/anti-corruption/",
        known_hosts={"known.example.org"},
    )

    assert links == [
        {
            "name": "Tip Desk",
            "url": "https://tip.example.org/submit",
            "host": "tip.example.org",
        },
        {
            "name": "known.example.org",
            "url": "https://known.example.org/",
            "host": "known.example.org",
        },
    ]


def test_refresh_globaleaks_directory_rows_is_deterministic_and_schema_compatible() -> None:
    rows: list[dict[str, object]] = [
        {
            "hostnames": ["tips.example.org"],
            "http": {"title": "Eclair Desk", "html_lang": "fr"},
            "location": {"country_name": "France"},
            "port": 443,
            "description": "French civic whistleblowing intake.",
        },
        {
            "name": "Alpha GlobaLeaks",
            "submission_url": "https://submit.alpha.example.org/",
            "countries": ["Italy", "Italy"],
            "languages": ["English", "Italian", "English"],
            "description": "",
        },
    ]

    result_a = refresh_globaleaks_directory_rows(rows)
    result_b = refresh_globaleaks_directory_rows(rows)

    assert result_a == result_b
    assert [row["name"] for row in result_a] == ["Alpha GlobaLeaks", "Eclair Desk"]
    assert [row["id"] for row in result_a] == [
        "globaleaks-submit-alpha-example-org",
        "globaleaks-tips-example-org",
    ]
    assert result_a[0]["website"] == "https://submit.alpha.example.org/"
    assert result_a[0]["host"] == "submit.alpha.example.org"
    assert (
        result_a[0]["description"] == "GlobaLeaks instance listed on the GlobaLeaks use case pages."
    )
    assert result_a[0]["countries"] == ["Italy"]
    assert result_a[0]["languages"] == ["English", "Italian"]
    assert result_a[1]["submission_url"] == "https://tips.example.org/"
    assert result_a[1]["countries"] == ["France"]
    assert result_a[1]["languages"] == ["fr"]
    assert list(result_a[0]) == [
        "id",
        "slug",
        "name",
        "website",
        "description",
        "submission_url",
        "host",
        "countries",
        "languages",
        "source_label",
        "source_url",
    ]


def test_refresh_globaleaks_directory_rows_rejects_duplicates() -> None:
    rows: list[dict[str, object]] = [
        {"submission_url": "https://tips.example.org/", "name": "One"},
        {"submission_url": "https://tips.example.org/disclosure", "name": "Two"},
    ]

    with pytest.raises(GlobaLeaksDirectoryRefreshError, match="Duplicate GlobaLeaks listing"):
        refresh_globaleaks_directory_rows(rows)


def test_refresh_globaleaks_directory_rows_requires_submission_host_or_url() -> None:
    with pytest.raises(GlobaLeaksDirectoryRefreshError, match="submission URL or host"):
        refresh_globaleaks_directory_rows([{"name": "No Host"}])


def test_refresh_globaleaks_directory_rows_rejects_invalid_explicit_submission_url() -> None:
    with pytest.raises(GlobaLeaksDirectoryRefreshError, match="Invalid URL for field"):
        refresh_globaleaks_directory_rows(
            [
                {
                    "name": "Bad URL",
                    "submission_url": "javascript:alert(1)",
                }
            ]
        )


def test_fetch_globaleaks_directory_rows_scrapes_usecase_pages_and_preserves_known_rows() -> None:
    session = _FakeSession(
        {
            "https://www.globaleaks.org/usecases/investigative-journalism/": _FakeResponse(
                """
                <html>
                  <body>
                    <a href="https://www.globaleaks.org/">GlobaLeaks</a>
                    <a href="https://www.publeaks.nl/">PubLeaks</a>
                    <a href="https://whistle.alpha.example.org/">Alpha Desk</a>
                    <a href="https://github.com/globaleaks/globaleaks">GitHub</a>
                  </body>
                </html>
                """
            )
        }
    )
    known_rows = [
        {
            "id": "globaleaks-secure-publeaks-nl",
            "slug": "globaleaks~secure-publeaks-nl",
            "name": "PubLeaks",
            "website": "https://www.publeaks.nl/",
            "description": "Known curated PubLeaks listing.",
            "submission_url": "https://secure.publeaks.nl/",
            "host": "secure.publeaks.nl",
            "countries": ["Netherlands"],
            "languages": ["Dutch"],
            "source_label": "Old source",
            "source_url": "https://old.example.org/",
        }
    ]

    rows = fetch_globaleaks_directory_rows(
        known_rows=known_rows,
        source_pages=(
            {
                "source_label": "GlobaLeaks investigative journalism use case page",
                "source_url": "https://www.globaleaks.org/usecases/investigative-journalism/",
            },
        ),
        session=session,
    )

    assert session.requested_urls == [
        "https://www.globaleaks.org/usecases/investigative-journalism/"
    ]
    assert rows == [
        {
            "id": "globaleaks-secure-publeaks-nl",
            "slug": "globaleaks~secure-publeaks-nl",
            "name": "PubLeaks",
            "website": "https://www.publeaks.nl/",
            "description": "Known curated PubLeaks listing.",
            "submission_url": "https://secure.publeaks.nl/",
            "host": "secure.publeaks.nl",
            "countries": ["Netherlands"],
            "languages": ["Dutch"],
            "source_label": "GlobaLeaks investigative journalism use case page",
            "source_url": "https://www.globaleaks.org/usecases/investigative-journalism/",
        },
        {
            "name": "Alpha Desk",
            "website": "https://whistle.alpha.example.org/",
            "submission_url": "https://whistle.alpha.example.org/",
            "host": "whistle.alpha.example.org",
            "source_label": "GlobaLeaks investigative journalism use case page",
            "source_url": "https://www.globaleaks.org/usecases/investigative-journalism/",
        },
    ]


def test_fetch_globaleaks_directory_rows_skips_hosts_seen_on_earlier_pages() -> None:
    session = _FakeSession(
        {
            "https://www.globaleaks.org/usecases/anti-corruption/": _FakeResponse(
                """
                <html>
                  <body>
                    <a href="https://tip.repeat.example.org/submit">Repeat Desk</a>
                  </body>
                </html>
                """
            ),
            "https://www.globaleaks.org/usecases/investigative-journalism/": _FakeResponse(
                """
                <html>
                  <body>
                    <a href="https://tip.repeat.example.org/other">Repeat Desk Again</a>
                  </body>
                </html>
                """
            ),
        }
    )

    rows = fetch_globaleaks_directory_rows(
        source_pages=(
            {
                "source_label": "GlobaLeaks anti-corruption use case page",
                "source_url": "https://www.globaleaks.org/usecases/anti-corruption/",
            },
            {
                "source_label": "GlobaLeaks investigative journalism use case page",
                "source_url": "https://www.globaleaks.org/usecases/investigative-journalism/",
            },
        ),
        session=session,
    )

    assert rows == [
        {
            "name": "Repeat Desk",
            "website": "https://tip.repeat.example.org/submit",
            "submission_url": "https://tip.repeat.example.org/submit",
            "host": "tip.repeat.example.org",
            "source_label": "GlobaLeaks anti-corruption use case page",
            "source_url": "https://www.globaleaks.org/usecases/anti-corruption/",
        }
    ]


def test_fetch_globaleaks_directory_rows_wraps_request_failures() -> None:
    with pytest.raises(
        GlobaLeaksDirectoryRefreshError,
        match="Failed to fetch GlobaLeaks discovery pages: timed out fetching",
    ):
        fetch_globaleaks_directory_rows(
            source_pages=(
                {
                    "source_label": "GlobaLeaks anti-corruption use case page",
                    "source_url": "https://www.globaleaks.org/usecases/anti-corruption/",
                },
            ),
            session=_ErrorSession(),
        )


def test_fetch_globaleaks_directory_rows_fails_closed_when_no_candidates_are_found() -> None:
    session = _FakeSession(
        {
            "https://www.globaleaks.org/usecases/anti-corruption/": _FakeResponse(
                """
                <html>
                  <body>
                    <a href="https://www.globaleaks.org/">GlobaLeaks</a>
                    <a href="https://github.com/globaleaks/globaleaks">GitHub</a>
                  </body>
                </html>
                """
            )
        }
    )

    with pytest.raises(
        GlobaLeaksDirectoryRefreshError,
        match="No GlobaLeaks listings were discovered",
    ):
        fetch_globaleaks_directory_rows(
            source_pages=(
                {
                    "source_label": "GlobaLeaks anti-corruption use case page",
                    "source_url": "https://www.globaleaks.org/usecases/anti-corruption/",
                },
            ),
            session=session,
        )


def test_render_globaleaks_refresh_summary() -> None:
    summary = render_globaleaks_refresh_summary(
        source_url=GLOBALEAKS_SOURCE_URL,
        total_count=11,
        added_count=2,
        removed_count=3,
        updated_count=4,
    )

    assert "GlobaLeaks Directory Refresh Summary" in summary
    assert "Total instances: 11" in summary
    assert "Added instances: 2" in summary
    assert "Removed instances: 3" in summary
    assert "Updated instances: 4" in summary

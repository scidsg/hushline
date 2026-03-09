from __future__ import annotations

import pytest

from hushline.globaleaks_directory_refresh import (
    GLOBALEAKS_SOURCE_URL,
    GlobaLeaksDirectoryRefreshError,
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

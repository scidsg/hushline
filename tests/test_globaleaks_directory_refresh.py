from __future__ import annotations

from pathlib import Path

import pytest

from hushline.globaleaks_directory_refresh import (
    GLOBALEAKS_SOURCE_LABEL,
    GLOBALEAKS_SOURCE_URL,
    GlobaLeaksDirectoryRefreshError,
    load_globaleaks_source_rows,
    refresh_globaleaks_directory_rows,
    render_globaleaks_refresh_summary,
)


def test_refresh_globaleaks_directory_rows_is_deterministic_and_schema_compatible() -> None:
    rows: list[dict[str, object]] = [
        {
            "hostnames": ["tips.example.org"],
            "http": {"title": "Éclair Desk", "html_lang": "fr"},
            "location": {"country_name": "France"},
            "port": 443,
            "_shodan": {"module": "https"},
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
    assert [row["name"] for row in result_a] == ["Alpha GlobaLeaks", "Éclair Desk"]
    assert [row["id"] for row in result_a] == [
        "globaleaks-submit-alpha-example-org",
        "globaleaks-tips-example-org",
    ]
    assert result_a[0]["website"] == "https://submit.alpha.example.org/"
    assert result_a[0]["host"] == "submit.alpha.example.org"
    assert result_a[0]["description"] == "GlobaLeaks instance discovered from an automated dataset."
    assert result_a[0]["countries"] == ["Italy"]
    assert result_a[0]["languages"] == ["English", "Italian"]
    assert result_a[1]["submission_url"] == "https://tips.example.org/"
    assert result_a[1]["countries"] == ["France"]
    assert result_a[1]["languages"] == ["fr"]
    assert result_a[1]["source_label"] == GLOBALEAKS_SOURCE_LABEL
    assert result_a[1]["source_url"] == GLOBALEAKS_SOURCE_URL
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


def test_load_globaleaks_source_rows_supports_matches_wrapper(tmp_path: Path) -> None:
    input_path = tmp_path / "globaleaks.json"
    input_path.write_text('{"matches":[{"name":"Alpha","submission_url":"https://alpha.example"}]}')

    rows = load_globaleaks_source_rows(input_path)

    assert rows == [{"name": "Alpha", "submission_url": "https://alpha.example"}]


def test_load_globaleaks_source_rows_supports_jsonl(tmp_path: Path) -> None:
    input_path = tmp_path / "globaleaks.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"name":"Alpha","submission_url":"https://alpha.example"}',
                '{"name":"Beta","submission_url":"https://beta.example"}',
            ]
        )
    )

    rows = load_globaleaks_source_rows(input_path)

    assert rows == [
        {"name": "Alpha", "submission_url": "https://alpha.example"},
        {"name": "Beta", "submission_url": "https://beta.example"},
    ]


def test_load_globaleaks_source_rows_supports_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "globaleaks.csv"
    input_path.write_text(
        "\n".join(
            [
                "name,submission_url,country_name",
                "Alpha,https://alpha.example,Italy",
            ]
        )
    )

    rows = load_globaleaks_source_rows(input_path)

    assert rows == [
        {
            "name": "Alpha",
            "submission_url": "https://alpha.example",
            "country_name": "Italy",
        }
    ]


def test_render_globaleaks_refresh_summary() -> None:
    summary = render_globaleaks_refresh_summary(
        source_url=GLOBALEAKS_SOURCE_URL,
        total_count=5802,
        added_count=50,
        removed_count=7,
        updated_count=101,
    )

    assert "GlobaLeaks Directory Refresh Summary" in summary
    assert "Total instances: 5802" in summary
    assert "Added instances: 50" in summary
    assert "Removed instances: 7" in summary
    assert "Updated instances: 101" in summary

from __future__ import annotations

from typing import Any, cast

import pytest
import requests

from hushline import securedrop_directory_refresh as refresh_module
from hushline.securedrop_directory_refresh import (
    SECUREDROP_DIRECTORY_API_URL,
    SecureDropDirectoryRefreshError,
    SecureDropRefreshSummary,
    _choose_website,
    _normalize_http_url,
    _normalize_string_list,
    fetch_securedrop_directory_rows,
    refresh_securedrop_directory_rows,
    render_securedrop_refresh_summary,
)


def _raw_row(  # noqa: PLR0913
    *,
    title: str,
    slug: str,
    directory_url: str,
    organization_url: str,
    landing_page_url: str,
    onion_address: str,
    onion_name: str = "",
    organization_description: str = "",
    countries: list[str] | None = None,
    languages: list[str] | None = None,
    topics: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "slug": slug,
        "directory_url": directory_url,
        "organization_url": organization_url,
        "landing_page_url": landing_page_url,
        "onion_address": onion_address,
        "onion_name": onion_name,
        "organization_description": organization_description,
        "countries": countries or [],
        "languages": languages or [],
        "topics": topics or [],
    }


def test_refresh_securedrop_directory_rows_is_deterministic_and_schema_compatible() -> None:
    rows = [
        _raw_row(
            title="Éclair News",
            slug="eclair-news",
            directory_url="https://securedrop.org/directory/eclair-news/",
            organization_url="https://example.org/eclair",
            landing_page_url="https://example.org/eclair/tips",
            onion_address="eclair1234567890eclair1234567890eclair1234567890eclair12.onion",
            organization_description="French investigative newsroom.",
            countries=["France", "France", "Europe"],
            languages=["French", "French"],
            topics=["corruption", "government", "government"],
        ),
        _raw_row(
            title="Alpha Desk",
            slug="alpha-desk",
            directory_url="https://securedrop.org/directory/alpha-desk/",
            organization_url="",
            landing_page_url="https://example.org/alpha/tips",
            onion_address="alpha1234567890alpha1234567890alpha1234567890alpha1234.onion",
            organization_description="",
            countries=["USA"],
            languages=["English"],
            topics=["business"],
        ),
    ]

    result_a = refresh_securedrop_directory_rows(rows)
    result_b = refresh_securedrop_directory_rows(rows)

    assert result_a == result_b
    assert [row["name"] for row in result_a] == ["Alpha Desk", "Éclair News"]
    assert [row["id"] for row in result_a] == ["securedrop-alpha-desk", "securedrop-eclair-news"]
    assert result_a[0]["website"] == "https://example.org/alpha/tips"
    assert result_a[0]["description"] == "SecureDrop instance listed in the SecureDrop directory."
    assert result_a[1]["countries"] == ["France", "Europe"]
    assert result_a[1]["languages"] == ["French"]
    assert result_a[1]["topics"] == ["corruption", "government"]
    assert list(result_a[0]) == [
        "id",
        "slug",
        "name",
        "website",
        "description",
        "directory_url",
        "landing_page_url",
        "onion_address",
        "onion_name",
        "countries",
        "languages",
        "topics",
        "source_label",
        "source_url",
    ]


def test_normalize_string_list_filters_invalid_blank_and_duplicate_values() -> None:
    assert _normalize_string_list("English") == []
    assert _normalize_string_list([" English ", 3, "", "english", "French", " french "]) == [
        "English",
        "French",
    ]


def test_normalize_http_url_validates_required_and_optional_missing_values() -> None:
    assert _normalize_http_url(None, field="landing_page_url", required=False) == ""
    assert _normalize_http_url("   ", field="landing_page_url", required=False) == ""

    with pytest.raises(
        SecureDropDirectoryRefreshError,
        match="Missing required URL field: directory_url",
    ):
        _normalize_http_url(None, field="directory_url", required=True)

    with pytest.raises(
        SecureDropDirectoryRefreshError,
        match="Missing required URL field: directory_url",
    ):
        _normalize_http_url("   ", field="directory_url", required=True)


def test_choose_website_requires_a_usable_url() -> None:
    with pytest.raises(
        SecureDropDirectoryRefreshError,
        match="missing organization/landing/directory URL",
    ):
        _choose_website(
            {
                "organization_url": "mailto:tips@example.org",
                "landing_page_url": "javascript:alert(1)",
                "directory_url": "ftp://securedrop.example/directory",
            }
        )


def test_refresh_securedrop_directory_rows_requires_onion_address() -> None:
    with pytest.raises(SecureDropDirectoryRefreshError, match="onion_address"):
        refresh_securedrop_directory_rows(
            [
                _raw_row(
                    title="Missing Onion",
                    slug="missing-onion",
                    directory_url="https://securedrop.org/directory/missing-onion/",
                    organization_url="https://missing.example",
                    landing_page_url="https://missing.example/tips",
                    onion_address="",
                ),
            ],
        )


def test_refresh_securedrop_directory_rows_rejects_invalid_required_directory_url() -> None:
    with pytest.raises(
        SecureDropDirectoryRefreshError,
        match="Invalid URL for field directory_url",
    ):
        refresh_securedrop_directory_rows(
            [
                _raw_row(
                    title="Bad Directory URL",
                    slug="bad-directory-url",
                    directory_url="javascript:alert(1)",
                    organization_url="https://valid.example",
                    landing_page_url="https://valid.example/tips",
                    onion_address="bad1234567890bad1234567890bad1234567890bad1234567.onion",
                ),
            ]
        )


def test_refresh_securedrop_directory_rows_sanitizes_optional_and_website_urls() -> None:
    rows = refresh_securedrop_directory_rows(
        [
            _raw_row(
                title="Sanitized URLs",
                slug="sanitized-urls",
                directory_url="https://securedrop.org/directory/sanitized-urls/",
                organization_url="javascript:alert(1)",
                landing_page_url="mailto:tips@example.org",
                onion_address="safe1234567890safe1234567890safe1234567890safe12345.onion",
            ),
            _raw_row(
                title="Fallback Website",
                slug="fallback-website",
                directory_url="https://securedrop.org/directory/fallback-website/",
                organization_url="example.org/no-scheme",
                landing_page_url="https://valid.example/tips",
                onion_address="good1234567890good1234567890good1234567890good12345.onion",
            ),
        ]
    )

    sanitized = next(row for row in rows if row["slug"] == "securedrop~sanitized-urls")
    fallback = next(row for row in rows if row["slug"] == "securedrop~fallback-website")
    assert sanitized["landing_page_url"] == ""
    assert sanitized["website"] == "https://securedrop.org/directory/sanitized-urls/"
    assert fallback["website"] == "https://valid.example/tips"


def test_refresh_securedrop_directory_rows_rejects_empty_slug_after_normalization() -> None:
    with pytest.raises(
        SecureDropDirectoryRefreshError,
        match="SecureDrop slug normalized to an empty value",
    ):
        refresh_securedrop_directory_rows(
            [
                _raw_row(
                    title="Bad Slug",
                    slug="!!!",
                    directory_url="https://securedrop.org/directory/bad-slug/",
                    organization_url="https://valid.example",
                    landing_page_url="https://valid.example/tips",
                    onion_address="badslug1234567890badslug1234567890badslug1234567890.onion",
                ),
            ]
        )


@pytest.mark.parametrize(
    ("normalized_rows", "message"),
    [
        (
            [{"id": 1, "slug": "securedrop~one", "name": "One"}],
            "Normalized row id must be a string",
        ),
        (
            [
                {"id": "securedrop-one", "slug": "securedrop~one", "name": "One"},
                {"id": "securedrop-one", "slug": "securedrop~two", "name": "Two"},
            ],
            "Duplicate SecureDrop listing id: securedrop-one",
        ),
        (
            [{"id": "securedrop-one", "slug": 1, "name": "One"}],
            "Normalized row slug must be a string",
        ),
        (
            [
                {"id": "securedrop-one", "slug": "securedrop~shared", "name": "One"},
                {"id": "securedrop-two", "slug": "securedrop~shared", "name": "Two"},
            ],
            "Duplicate SecureDrop listing slug: securedrop~shared",
        ),
    ],
)
def test_refresh_securedrop_directory_rows_validates_normalized_row_shapes(
    monkeypatch: pytest.MonkeyPatch,
    normalized_rows: list[dict[str, object]],
    message: str,
) -> None:
    rows_iter = iter(normalized_rows)

    def fake_normalize(row: dict[str, object]) -> dict[str, object]:
        return next(rows_iter)

    monkeypatch.setattr(refresh_module, "_normalize_securedrop_row", fake_normalize)

    with pytest.raises(SecureDropDirectoryRefreshError, match=message):
        refresh_securedrop_directory_rows([{} for _ in normalized_rows])


class _FakeResponse:
    def __init__(self, *, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError("bad status")

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, timeout: float, headers: dict[str, str]) -> _FakeResponse:
        self.calls.append({"url": url, "timeout": timeout, "headers": headers})
        return _FakeResponse(payload=self.payload)


def test_fetch_securedrop_directory_rows_requests_expected_shape() -> None:
    session = _FakeSession(payload=[{"slug": "alpha"}, {"slug": "beta"}])
    rows = fetch_securedrop_directory_rows(
        session=cast(requests.Session, session),
        timeout_seconds=12.5,
    )

    assert rows == [{"slug": "alpha"}, {"slug": "beta"}]
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == SECUREDROP_DIRECTORY_API_URL
    assert call["timeout"] == 12.5
    assert isinstance(call["headers"], dict)
    assert "User-Agent" in call["headers"]


def test_fetch_securedrop_directory_rows_rejects_non_list_payload() -> None:
    session = _FakeSession(payload={"slug": "alpha"})
    with pytest.raises(SecureDropDirectoryRefreshError, match="JSON array"):
        fetch_securedrop_directory_rows(session=cast(requests.Session, session))


def test_fetch_securedrop_directory_rows_rejects_non_object_payload_items() -> None:
    session = _FakeSession(payload=[{"slug": "alpha"}, "beta"])
    with pytest.raises(SecureDropDirectoryRefreshError, match="JSON objects"):
        fetch_securedrop_directory_rows(session=cast(requests.Session, session))


def test_render_securedrop_refresh_summary() -> None:
    summary = render_securedrop_refresh_summary(
        source_url=SECUREDROP_DIRECTORY_API_URL,
        summary=SecureDropRefreshSummary(
            total_count=24,
            added_rows=(
                {
                    "id": "securedrop-new-desk",
                    "name": "New Desk",
                },
            ),
            removed_rows=(
                {
                    "id": "securedrop-old-desk",
                    "name": "Old Desk",
                },
            ),
            updated_rows=(
                (
                    {
                        "id": "securedrop-existing-desk",
                        "name": "Existing Desk",
                        "landing_page_url": "https://old.example.test/tips",
                        "countries": ["United States"],
                    },
                    {
                        "id": "securedrop-existing-desk",
                        "name": "Existing Desk",
                        "landing_page_url": "https://new.example.test/tips",
                        "countries": ["United States", "Canada"],
                    },
                ),
            ),
        ),
    )

    assert "SecureDrop Directory Refresh Summary" in summary
    assert "Total instances: 24" in summary
    assert "Added instances: 1" in summary
    assert "Removed instances: 1" in summary
    assert "Updated instances: 1" in summary
    assert "### Added Instances" in summary
    assert "- New Desk (`securedrop-new-desk`)" in summary
    assert "### Removed Instances" in summary
    assert "- Old Desk (`securedrop-old-desk`)" in summary
    assert "### Updated Instances" in summary
    assert (
        "- Existing Desk (`securedrop-existing-desk`): `landing_page_url`, `countries`" in summary
    )

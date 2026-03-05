from __future__ import annotations

from typing import Any, cast

import pytest
import requests

from hushline.securedrop_directory_refresh import (
    SECUREDROP_DIRECTORY_API_URL,
    SecureDropDirectoryRefreshError,
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


def test_refresh_securedrop_directory_rows_rejects_duplicates() -> None:
    duplicate_slug_rows = [
        _raw_row(
            title="One",
            slug="same",
            directory_url="https://securedrop.org/directory/one/",
            organization_url="https://one.example",
            landing_page_url="https://one.example/tips",
            onion_address="one1234567890one1234567890one1234567890one1234567890.onion",
        ),
        _raw_row(
            title="Two",
            slug="same",
            directory_url="https://securedrop.org/directory/two/",
            organization_url="https://two.example",
            landing_page_url="https://two.example/tips",
            onion_address="two1234567890two1234567890two1234567890two1234567890.onion",
        ),
    ]
    with pytest.raises(SecureDropDirectoryRefreshError, match="Duplicate SecureDrop listing"):
        refresh_securedrop_directory_rows(duplicate_slug_rows)


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


def test_render_securedrop_refresh_summary() -> None:
    summary = render_securedrop_refresh_summary(
        source_url=SECUREDROP_DIRECTORY_API_URL,
        total_count=24,
        added_count=2,
        removed_count=1,
        updated_count=4,
    )

    assert "SecureDrop Directory Refresh Summary" in summary
    assert "Total instances: 24" in summary
    assert "Added instances: 2" in summary
    assert "Removed instances: 1" in summary
    assert "Updated instances: 4" in summary

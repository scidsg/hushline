import time

import pytest
import requests
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import PublicRecordListing, User, get_public_record_listings
from hushline.public_record_refresh import DEFAULT_REGION_STATE_MAP, US_STATE_CODES


def _first_public_record_listing_or_skip() -> PublicRecordListing:
    listings = get_public_record_listings()
    if not listings:
        pytest.skip("No public-record listings configured")
    return listings[0]


def test_directory_accessible(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200
    assert "Whistleblower Support Directory" in response.text
    # New: the tab label is now "Law Firms" plus the "🤖 Automated" badge
    assert "Law Firms" in response.text
    assert "🤖 Automated" in response.text


def test_directory_public_record_banner_links_to_admin(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    public_records_panel = soup.find(id="public-records")
    assert public_records_panel is not None

    banner_link = public_records_panel.select_one(".dirMeta a")
    assert banner_link is not None
    assert banner_link.text.strip() == "Hush Line admin"
    assert banner_link.get("href") == "/to/admin"
    banner_text = public_records_panel.get_text(" ", strip=True)
    assert "These are automated listings pulled from public records." in banner_text
    assert "Message the Hush Line admin for any corrections." in banner_text


def test_directory_hides_tab_bar_when_verified_tabs_disabled(client: FlaskClient) -> None:
    client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = False
    try:
        response = client.get(url_for("directory"))
    finally:
        client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = True

    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.find(id="directory-tabs") is None
    assert soup.find(id="public-records") is None

    all_panel = soup.find(id="all")
    assert all_panel is not None
    assert "🏛️ Public Record Law Firms" not in all_panel.get_text(" ", strip=True)
    assert "🏛️ Public Record" not in all_panel.get_text(" ", strip=True)


def test_directory_users_json_excludes_public_records_when_verified_tabs_disabled(
    client: FlaskClient,
) -> None:
    client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = False
    try:
        response = client.get(url_for("directory_users"))
    finally:
        client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = True

    assert response.status_code == 200
    assert all(not row["is_public_record"] for row in (response.json or []))


def test_directory_lists_only_opted_in_users(client: FlaskClient, user: User) -> None:
    user.primary_username.show_in_directory = True
    db.session.commit()
    response = client.get(url_for("directory"))
    assert user.primary_username.username in response.text, response.text

    user.primary_username.show_in_directory = False
    db.session.commit()
    response = client.get(url_for("directory"))
    assert user.primary_username.username not in response.text


def test_directory_session_user_json_defaults_to_logged_out(client: FlaskClient) -> None:
    response = client.get(url_for("session_user"))
    assert response.status_code == 200
    assert response.json == {"logged_in": False}


@pytest.mark.usefixtures("_authenticated_user")
def test_directory_session_user_json_logged_in(client: FlaskClient) -> None:
    response = client.get(url_for("session_user"))
    assert response.status_code == 200
    assert response.json == {"logged_in": True}


def test_directory_users_json_includes_display_name_fallback_and_flags(
    client: FlaskClient, admin_user: User
) -> None:
    admin_user.primary_username.show_in_directory = True
    admin_user.primary_username._display_name = None
    admin_user.primary_username.bio = "admin bio"
    admin_user.primary_username.is_verified = True
    db.session.commit()

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200
    admin_row = next(
        row
        for row in (response.json or [])
        if row["primary_username"] == admin_user.primary_username.username
    )
    assert admin_row["display_name"] == admin_user.primary_username.username
    assert admin_row["bio"] == "admin bio"
    assert admin_row["is_admin"] is True
    assert admin_row["is_verified"] is True
    assert isinstance(admin_row["has_pgp_key"], bool)


def test_directory_public_records_render_only_in_public_records_and_all(
    client: FlaskClient,
) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    all_panel = soup.find(id="all")

    assert public_records_panel is not None
    assert all_panel is not None
    assert listing.name in public_records_panel.text
    assert listing.name in all_panel.text
    assert listing.description in public_records_panel.text
    assert listing.description in all_panel.text
    assert listing.website not in public_records_panel.text
    assert listing.website not in all_panel.text
    assert f"Source: {listing.source_label}" not in public_records_panel.text
    assert f"Source: {listing.source_label}" not in all_panel.text
    assert "🏛️ Public Record" in public_records_panel.text
    assert "🤖 Automated" in public_records_panel.text
    assert verified_panel is not None
    assert listing.name not in verified_panel.text


def test_directory_users_json_includes_public_record_rows(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200

    row = next(row for row in (response.json or []) if row["display_name"] == listing.name)
    assert row["entry_type"] == "public_record"
    assert row["primary_username"] is None
    assert row["is_public_record"] is True
    assert row["is_automated"] is True
    assert row["message_capable"] is False
    assert row["bio"] == listing.description
    assert row["location"] == listing.location
    assert row["practice_tags"] == list(listing.practice_tags)
    assert row["source_label"] == listing.source_label


def test_public_record_seed_regions_have_coverage() -> None:
    listings = get_public_record_listings()

    allowed_states = {state for states in DEFAULT_REGION_STATE_MAP.values() for state in states}
    assert all(listing.state in allowed_states for listing in listings)

    if listings:
        us_covered = {listing.state for listing in listings if listing.state in US_STATE_CODES}
        assert us_covered == set(US_STATE_CODES)

    assert all(listing.source_url for listing in listings)
    assert all("chambers.com" not in (listing.source_url or "") for listing in listings)


def test_public_record_listing_page_is_read_only(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(url_for("public_record_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    assert "🏛️ Public Record" in page_text
    assert "🤖 Automated" in page_text
    assert listing.description in page_text
    assert listing.website in response.text
    assert "Source" in page_text
    assert listing.source_url is not None
    source_link = soup.find("a", href=listing.source_url)
    assert source_link is not None
    assert "Practice Areas" not in page_text
    assert 'id="messageForm"' not in response.text
    assert "Send Message" not in page_text


def test_public_record_listing_route_rejects_post(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.post(url_for("public_record_listing", slug=listing.slug))
    assert response.status_code == 405


def test_public_record_listing_route_hidden_when_verified_tabs_disabled(
    client: FlaskClient,
) -> None:
    listing = _first_public_record_listing_or_skip()
    client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = False
    try:
        response = client.get(url_for("public_record_listing", slug=listing.slug))
    finally:
        client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = True

    assert response.status_code == 404


def test_public_record_listing_slug_cannot_be_messaged(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(
        url_for("redirect_submit_message", username=listing.slug),
        follow_redirects=True,
    )
    assert response.status_code == 404


@pytest.mark.local_only()
@pytest.mark.external_network()
def test_public_record_external_links_resolve() -> None:
    max_attempts = 3
    retryable_status_codes = {408, 425, 429, 500, 502, 503, 504}
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; HushlineLinkCheck/1.0; "
                "+https://github.com/scidsg/hushline)"
            )
        }
    )

    checked: set[str] = set()
    failures: list[str] = []

    for listing in get_public_record_listings():
        for label, url in {
            "website": listing.website,
            "source": listing.source_url,
        }.items():
            if not url or url in checked:
                continue

            checked.add(url)

            last_error: requests.RequestException | None = None
            last_status_code: int | None = None

            for attempt in range(1, max_attempts + 1):
                response: requests.Response | None = None
                try:
                    response = session.get(url, allow_redirects=True, timeout=15, stream=True)
                    last_status_code = response.status_code
                    if response.status_code not in retryable_status_codes:
                        break
                except requests.RequestException as exc:
                    last_error = exc
                finally:
                    if response is not None:
                        response.close()

                if attempt < max_attempts:
                    time.sleep(attempt)

            if last_status_code is not None and (
                last_status_code >= 500 or last_status_code in {404, 410}
            ):
                failures.append(
                    f"{listing.name} {label} failed with HTTP {last_status_code}: {url}"
                )
            elif last_error is not None and last_status_code is None:
                failures.append(f"{listing.name} {label} request failed: {url} ({last_error})")

    assert not failures, "Broken public record links:\n" + "\n".join(failures)

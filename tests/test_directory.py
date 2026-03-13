import re
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlparse

import pytest
from bs4 import BeautifulSoup, Tag
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    GlobaLeaksDirectoryListing,
    PublicRecordListing,
    SecureDropDirectoryListing,
    User,
    get_globaleaks_directory_listings,
    get_public_record_listings,
    get_securedrop_directory_listings,
)
from hushline.public_record_refresh import (
    DEFAULT_REGION_STATE_MAP,
    US_STATE_AUTHORITATIVE_SOURCES,
    US_STATE_CODES,
    build_requests_link_checker,
)


def _first_public_record_listing_or_skip() -> PublicRecordListing:
    listings = _strict_public_record_listings()
    if not listings:
        pytest.skip("No public-record listings configured")
    return listings[0]


def _first_securedrop_listing_or_skip() -> SecureDropDirectoryListing:
    listings = get_securedrop_directory_listings()
    if not listings:
        pytest.skip("No SecureDrop listings configured")
    return listings[0]


def _sample_globaleaks_listing() -> GlobaLeaksDirectoryListing:
    return GlobaLeaksDirectoryListing(
        id="globaleaks-sample-newsroom",
        slug="globaleaks~sample-newsroom",
        name="Sample GlobaLeaks Newsroom",
        website="https://example.org",
        description="An example GlobaLeaks instance for investigative submissions.",
        submission_url="https://submit.example.org",
        host="submit.example.org",
        countries=("Italy",),
        languages=("English", "Italian"),
        source_label="Automated GlobaLeaks discovery dataset",
        source_url="https://example.org/source/globaleaks-export",
    )


def _sample_onion_globaleaks_listing() -> GlobaLeaksDirectoryListing:
    return GlobaLeaksDirectoryListing(
        id="globaleaks-sample-onion-newsroom",
        slug="globaleaks~sample-onion-newsroom",
        name="Sample Onion GlobaLeaks Newsroom",
        website="https://example.org",
        description="An example GlobaLeaks instance with an onion submission endpoint.",
        submission_url="http://sampleonionaddress1234567890abcdef1234567890abcdef1234567890.onion",
        host="sampleonionaddress1234567890abcdef1234567890abcdef1234567890.onion",
        countries=("Italy",),
        languages=("English",),
        source_label="Automated GlobaLeaks discovery dataset",
        source_url="https://example.org/source/globaleaks-export",
    )


def test_globaleaks_seed_has_rows() -> None:
    listings = get_globaleaks_directory_listings()

    assert listings
    assert all(listing.submission_url for listing in listings)
    assert all(listing.website for listing in listings)
    assert all(listing.host for listing in listings)


def _strict_public_record_listings() -> list[PublicRecordListing]:
    return [
        listing
        for listing in get_public_record_listings()
        if listing.directory_section != "legacy_public_record"
    ]


def _legacy_public_record_listings() -> list[PublicRecordListing]:
    return [
        listing
        for listing in get_public_record_listings()
        if listing.directory_section == "legacy_public_record"
    ]


def _find_directory_card(panel: BeautifulSoup | Tag | None, display_name: str) -> Tag:
    assert panel is not None
    for card in panel.select("article.user"):
        heading = card.select_one("h3")
        if heading is not None and heading.get_text(" ", strip=True) == display_name:
            return card
    raise AssertionError(f"Could not find directory card for {display_name}")


def test_directory_accessible(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200
    assert "Whistleblower Support Directory" in response.text
    assert "Attorneys" in response.text
    assert "GlobaLeaks" in response.text
    assert "SecureDrop" in response.text
    assert "🤖 Automated" in response.text
    assert "⚖️ Attorney" in response.text


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
    assert "Beta: These listings are automated and pulled from public records." in banner_text
    assert "Message the Hush Line admin for any corrections." in banner_text


def test_directory_securedrop_banner_links_to_admin_without_tor_copy(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    securedrop_panel = soup.find(id="securedrop")
    assert securedrop_panel is not None

    banner_links = securedrop_panel.select(".dirMeta a")
    links_by_text = {link.text.strip(): link.get("href") for link in banner_links}
    assert links_by_text["Hush Line admin"] == "/to/admin"
    banner_text = securedrop_panel.get_text(" ", strip=True)
    assert banner_text.startswith("🧪 Beta:")
    assert "These listings are automated." in banner_text
    assert "Contact the Hush Line admin for any corrections." in banner_text
    assert "Onion addresses require" not in banner_text
    assert "Tor Browser" not in banner_text


def test_directory_globaleaks_banner_links_to_admin_without_tor_copy(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    globaleaks_panel = soup.find(id="globaleaks")
    assert globaleaks_panel is not None

    banner = globaleaks_panel.select_one(".dirMeta")
    assert banner is not None
    banner_links = globaleaks_panel.select(".dirMeta a")
    links_by_text = {link.text.strip(): link.get("href") for link in banner_links}
    assert links_by_text["Hush Line admin"] == "/to/admin"
    assert "Tor Browser" not in links_by_text
    banner_text = " ".join(banner.get_text(" ", strip=True).split())
    assert banner_text.startswith("🧪 Beta:")
    assert "These listings are automated." in banner_text
    assert "Contact the Hush Line admin for any corrections." in banner_text
    assert "Onion addresses require" not in banner_text


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
    assert soup.find(id="globaleaks") is None
    assert soup.find(id="securedrop") is None

    all_panel = soup.find(id="all")
    assert all_panel is not None
    assert "🏛️ Public Record Attorneys" not in all_panel.get_text(" ", strip=True)
    assert "🌐 GlobaLeaks" not in all_panel.get_text(" ", strip=True)
    assert "🛡️ SecureDrop Instances" not in all_panel.get_text(" ", strip=True)
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
    assert all(not row["is_globaleaks"] for row in (response.json or []))
    assert all(not row["is_securedrop"] for row in (response.json or []))


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
    assert admin_row["is_globaleaks"] is False
    assert admin_row["is_securedrop"] is False
    assert admin_row["city"] is None
    assert admin_row["country"] is None
    assert admin_row["subdivision"] is None
    assert admin_row["subdivision_code"] is None
    assert admin_row["countries"] == []
    assert admin_row["directory_section"] is None


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
    assert public_records_panel.select_one('span.badge[aria-label="Attorney listing"]') is None
    assert "🤖 Automated" in public_records_panel.text
    assert all_panel.select_one('span.badge[aria-label="Attorney listing"]') is not None
    assert "Public Record Attorneys (Legacy)" not in public_records_panel.text
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
    assert "location" not in row
    assert row["city"] == listing.geography.city
    assert row["country"] == listing.geography.country
    assert row["subdivision"] == listing.geography.subdivision
    assert row["subdivision_code"] == listing.geography.subdivision_code
    assert row["countries"] == list(listing.geography.countries)
    assert row["practice_tags"] == list(listing.practice_tags)
    assert row["source_label"] == listing.source_label
    assert row["directory_section"] == "public_record"


def test_directory_public_record_cards_do_not_show_location(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    public_records_panel = soup.find(id="public-records")
    all_panel = soup.find(id="all")

    public_record_card = _find_directory_card(public_records_panel, listing.name)
    all_card = _find_directory_card(all_panel, listing.name)

    assert listing.location not in public_record_card.get_text(" ", strip=True)
    assert listing.location not in all_card.get_text(" ", strip=True)


def test_directory_users_json_includes_legacy_public_record_rows(client: FlaskClient) -> None:
    legacy_listings = _legacy_public_record_listings()
    if not legacy_listings:
        pytest.skip("No legacy public-record listings configured")

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200

    legacy_listing = legacy_listings[0]
    legacy_row = next(
        row for row in (response.json or []) if row["display_name"] == legacy_listing.name
    )
    assert legacy_row["entry_type"] == "public_record"
    assert legacy_row["country"] == legacy_listing.geography.country
    assert legacy_row["subdivision"] == legacy_listing.geography.subdivision
    assert legacy_row["subdivision_code"] == legacy_listing.geography.subdivision_code
    assert legacy_row["countries"] == list(legacy_listing.geography.countries)
    assert legacy_row["directory_section"] == "legacy_public_record"
    assert legacy_row["is_automated"] is True


def test_directory_filters_public_records_by_country_and_region_query_params(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    new_york_listing = PublicRecordListing(
        id="public-record-new-york",
        slug="public-record~new-york",
        name="New York Attorney",
        website="https://newyork.example",
        description="New York whistleblower attorney.",
        city="New York",
        state="NY",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    australia_listing = PublicRecordListing(
        id="public-record-australia",
        slug="public-record~australia",
        name="Australia Attorney",
        website="https://australia.example",
        description="Australian whistleblower attorney.",
        city="Sydney",
        state="Australia",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing, new_york_listing, australia_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_securedrop_directory_listings", lambda: ())

    response = client.get(f"{url_for('directory')}?country=US&region=CA")
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    public_records_panel = soup.find(id="public-records")
    all_panel = soup.find(id="all")
    public_record_count = soup.find(id="public-record-count")

    assert public_records_panel is not None
    assert all_panel is not None
    assert public_record_count is not None
    public_records_text = public_records_panel.get_text(" ", strip=True)
    all_text = all_panel.get_text(" ", strip=True)

    assert "California Attorney" in public_records_text
    assert "New York Attorney" not in public_records_text
    assert "Australia Attorney" not in public_records_text
    assert "California Attorney" in all_text
    assert "New York Attorney" not in all_text
    assert "Australia Attorney" not in all_text
    assert public_record_count.get_text(" ", strip=True) == "1"


def test_directory_attorney_filter_panel_hidden_by_default(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    australia_listing = PublicRecordListing(
        id="public-record-australia",
        slug="public-record~australia",
        name="Australia Attorney",
        website="https://australia.example",
        description="Australian whistleblower attorney.",
        city="Sydney",
        state="Australia",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing, australia_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_securedrop_directory_listings", lambda: ())

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    toggle_shell = soup.find(id="attorney-filters-toggle-shell")
    panel_shell = soup.find(id="attorney-filters-panel-shell")
    toggle = soup.find(id="attorney-filters-toggle")
    panel = soup.find(id="attorney-filters-panel")
    clear_filters_actions = soup.find(id="attorney-filters-actions")
    country_select = soup.find(id="attorney-country-filter")
    region_select = soup.find(id="attorney-region-filter")
    region_label = soup.find("label", {"for": "attorney-region-filter"})
    clear_filters_link = soup.find(id="attorney-filters-clear")

    assert toggle_shell is not None
    assert toggle_shell.has_attr("hidden")
    assert panel_shell is not None
    assert panel_shell.has_attr("hidden")
    assert toggle is not None
    assert toggle.get_text(" ", strip=True) == "Show Filters"
    assert toggle.get("aria-expanded") == "false"
    assert panel is not None
    assert panel.has_attr("hidden")
    assert country_select is not None
    assert region_select is not None
    assert region_label is not None
    assert region_label.get_text(" ", strip=True) == "State / Province / Region"
    assert not region_select.has_attr("disabled")
    assert region_select.find("option", value="").get_text(" ", strip=True) == "All"
    region_optgroups = region_select.find_all("optgroup")
    assert [optgroup.get("label") for optgroup in region_optgroups] == ["United States"]
    assert region_select.find("option", value="CA").get_text(" ", strip=True) == "California (1)"
    assert country_select.get_text(" ", strip=True) == "All Australia (1) United States (1)"
    assert clear_filters_actions is not None
    assert clear_filters_actions.has_attr("hidden")
    assert clear_filters_link is not None
    assert not clear_filters_link.has_attr("hidden")


def test_directory_attorney_filter_panel_shows_selected_filters(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    new_york_listing = PublicRecordListing(
        id="public-record-new-york",
        slug="public-record~new-york",
        name="New York Attorney",
        website="https://newyork.example",
        description="New York whistleblower attorney.",
        city="New York",
        state="NY",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing, new_york_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_securedrop_directory_listings", lambda: ())

    response = client.get(f"{url_for('directory')}?country=US&region=CA")
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    toggle_shell = soup.find(id="attorney-filters-toggle-shell")
    panel_shell = soup.find(id="attorney-filters-panel-shell")
    toggle = soup.find(id="attorney-filters-toggle")
    panel = soup.find(id="attorney-filters-panel")
    clear_filters_actions = soup.find(id="attorney-filters-actions")
    country_select = soup.find(id="attorney-country-filter")
    region_select = soup.find(id="attorney-region-filter")
    clear_filters_link = (
        panel.find("a", id="attorney-filters-clear", href=url_for("directory"))
        if isinstance(panel, Tag)
        else None
    )

    assert toggle_shell is not None
    assert toggle_shell.has_attr("hidden")
    assert panel_shell is not None
    assert panel_shell.has_attr("hidden")
    assert toggle is not None
    assert toggle.get_text(" ", strip=True) == "Hide Filters"
    assert toggle.get("aria-expanded") == "true"
    assert panel is not None
    assert not panel.has_attr("hidden")
    assert clear_filters_actions is not None
    assert not clear_filters_actions.has_attr("hidden")
    assert country_select is not None
    assert region_select is not None
    assert clear_filters_link is not None
    assert clear_filters_link.get_text(" ", strip=True) == "Clear Filters"
    assert country_select.find("option", selected=True)["value"] == "United States"
    assert country_select.find("option", selected=True).get_text(" ", strip=True) == "United States"
    assert region_select.find("option", selected=True).get_text(" ", strip=True) == "California"
    assert region_select.find("option", selected=True)["value"] == "CA"
    assert not region_select.has_attr("disabled")


def test_directory_users_json_filters_only_public_record_rows_by_query_params(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    new_york_listing = PublicRecordListing(
        id="public-record-new-york",
        slug="public-record~new-york",
        name="New York Attorney",
        website="https://newyork.example",
        description="New York whistleblower attorney.",
        city="New York",
        state="NY",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    securedrop_listing = SecureDropDirectoryListing(
        id="securedrop-sample",
        slug="securedrop~sample",
        name="Sample SecureDrop",
        website="https://securedrop.example",
        description="SecureDrop listing.",
        directory_url="https://securedrop.example/directory",
        landing_page_url="https://securedrop.example/landing",
        onion_address="sample1234567890sample1234567890sample1234567890sample12.onion",
        onion_name="Sample",
        countries=("United States",),
        languages=("English",),
        topics=("Investigations",),
        source_label="SecureDrop directory",
        source_url="https://securedrop.example/source",
    )

    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing, new_york_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr(
        "hushline.routes.directory.get_securedrop_directory_listings",
        lambda: (securedrop_listing,),
    )

    response = client.get(f"{url_for('directory_users')}?country=US&region=CA")
    assert response.status_code == 200

    rows = response.json or []
    public_record_names = {
        row["display_name"] for row in rows if row["entry_type"] == "public_record"
    }
    securedrop_names = {row["display_name"] for row in rows if row["entry_type"] == "securedrop"}

    assert public_record_names == {"California Attorney"}
    assert securedrop_names == {"Sample SecureDrop"}


def test_directory_attorney_filters_json_exposes_metadata_without_reflecting_filters(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    new_york_listing = PublicRecordListing(
        id="public-record-new-york",
        slug="public-record~new-york",
        name="New York Attorney",
        website="https://newyork.example",
        description="New York whistleblower attorney.",
        city="New York",
        state="NY",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    australia_listing = PublicRecordListing(
        id="public-record-australia",
        slug="public-record~australia",
        name="Australia Attorney",
        website="https://australia.example",
        description="Australian whistleblower attorney.",
        city="Sydney",
        state="Australia",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing, new_york_listing, australia_listing),
    )

    response = client.get(f"{url_for('directory_attorney_filters')}?country=US&region=CA")
    assert response.status_code == 200
    assert response.json == {
        "countries": [
            {"code": "Australia", "label": "Australia", "count": 1},
            {"code": "United States", "label": "United States", "count": 2},
        ],
        "regions": {
            "United States": [
                {"code": "CA", "label": "California", "count": 1},
                {"code": "NY", "label": "New York", "count": 1},
            ]
        },
    }


def test_directory_attorney_filters_include_normalized_country_values_outside_legacy_code_map(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    madagascar_listing = PublicRecordListing(
        id="public-record-madagascar",
        slug="public-record~madagascar",
        name="Madagascar Attorney",
        website="https://madagascar.example",
        description="Madagascar whistleblower attorney.",
        city="Antananarivo",
        state="Madagascar",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (madagascar_listing, california_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_securedrop_directory_listings", lambda: ())

    metadata_response = client.get(url_for("directory_attorney_filters"))
    assert metadata_response.status_code == 200
    assert metadata_response.json == {
        "countries": [
            {"code": "Madagascar", "label": "Madagascar", "count": 1},
            {"code": "United States", "label": "United States", "count": 1},
        ],
        "regions": {"United States": [{"code": "CA", "label": "California", "count": 1}]},
    }

    page_response = client.get(f"{url_for('directory')}?country=Madagascar")
    assert page_response.status_code == 200

    soup = BeautifulSoup(page_response.text, "html.parser")
    public_records_panel = soup.find(id="public-records")
    country_select = soup.find(id="attorney-country-filter")

    assert public_records_panel is not None
    assert country_select is not None
    assert country_select.find("option", selected=True)["value"] == "Madagascar"
    public_records_text = public_records_panel.get_text(" ", strip=True)
    assert "Madagascar Attorney" in public_records_text
    assert "California Attorney" not in public_records_text


def test_directory_attorney_filters_support_non_us_subdivisions(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_south_wales_listing = PublicRecordListing(
        id="public-record-new-south-wales",
        slug="public-record~new-south-wales",
        name="New South Wales Attorney",
        website="https://newsouthwales.example",
        description="New South Wales whistleblower attorney.",
        city="Sydney",
        state="Australia",
        country="Australia",
        subdivision="New South Wales",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (new_south_wales_listing, california_listing),
    )
    monkeypatch.setattr("hushline.routes.directory.get_directory_usernames", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_globaleaks_directory_listings", lambda: ())
    monkeypatch.setattr("hushline.routes.directory.get_securedrop_directory_listings", lambda: ())

    metadata_response = client.get(url_for("directory_attorney_filters"))
    assert metadata_response.status_code == 200
    assert metadata_response.json == {
        "countries": [
            {"code": "Australia", "label": "Australia", "count": 1},
            {"code": "United States", "label": "United States", "count": 1},
        ],
        "regions": {
            "Australia": [{"code": "New South Wales", "label": "New South Wales", "count": 1}],
            "United States": [{"code": "CA", "label": "California", "count": 1}],
        },
    }

    page_response = client.get(
        f"{url_for('directory')}?country=Australia&region=New%20South%20Wales"
    )
    assert page_response.status_code == 200

    soup = BeautifulSoup(page_response.text, "html.parser")
    public_records_panel = soup.find(id="public-records")
    region_select = soup.find(id="attorney-region-filter")

    assert public_records_panel is not None
    assert region_select is not None
    assert region_select.find("option", selected=True)["value"] == "New South Wales"
    public_records_text = public_records_panel.get_text(" ", strip=True)
    assert "New South Wales Attorney" in public_records_text
    assert "California Attorney" not in public_records_text


def test_directory_attorney_filters_json_ignores_untrusted_query_values(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    california_listing = PublicRecordListing(
        id="public-record-california",
        slug="public-record~california",
        name="California Attorney",
        website="https://california.example",
        description="California whistleblower attorney.",
        city="San Francisco",
        state="CA",
        practice_tags=("Whistleblowing",),
        source_label="Official source",
    )

    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: (california_listing,),
    )

    response = client.get(
        f"{url_for('directory_attorney_filters')}?country=%3Cscript%3E&region=%3Cimg%3E"
    )

    assert response.status_code == 200
    assert response.json == {
        "countries": [{"code": "United States", "label": "United States", "count": 1}],
        "regions": {"United States": [{"code": "CA", "label": "California", "count": 1}]},
    }


def test_directory_securedrop_render_only_in_securedrop_and_all(
    client: FlaskClient,
) -> None:
    listing = _first_securedrop_listing_or_skip()

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    securedrop_panel = soup.find(id="securedrop")
    all_panel = soup.find(id="all")

    assert securedrop_panel is not None
    assert all_panel is not None
    assert listing.name in securedrop_panel.text
    assert listing.name in all_panel.text
    assert listing.description in securedrop_panel.text
    assert listing.description in all_panel.text
    assert securedrop_panel.select_one('span.badge[aria-label="SecureDrop listing"]') is None
    assert securedrop_panel.select_one('span.badge[aria-label="Automated listing"]') is not None
    assert all_panel.select_one('span.badge[aria-label="SecureDrop listing"]') is not None
    assert all_panel.select_one('span.badge[aria-label="Automated listing"]') is not None
    assert public_records_panel is not None
    assert listing.name not in public_records_panel.text
    assert verified_panel is not None
    assert listing.name not in verified_panel.text


def test_directory_globaleaks_render_only_in_globaleaks_and_all(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listings",
        lambda: (listing,),
    )

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    globaleaks_panel = soup.find(id="globaleaks")
    securedrop_panel = soup.find(id="securedrop")
    all_panel = soup.find(id="all")

    assert globaleaks_panel is not None
    assert all_panel is not None
    assert listing.name in globaleaks_panel.text
    assert listing.name in all_panel.text
    assert listing.description in globaleaks_panel.text
    assert listing.description in all_panel.text
    assert globaleaks_panel.select_one('span.badge[aria-label="GlobaLeaks listing"]') is None
    assert globaleaks_panel.select_one('span.badge[aria-label="Automated listing"]') is not None
    assert all_panel.select_one('span.badge[aria-label="GlobaLeaks listing"]') is not None
    assert all_panel.select_one('span.badge[aria-label="Automated listing"]') is not None
    assert public_records_panel is not None
    assert listing.name not in public_records_panel.text
    assert securedrop_panel is not None
    assert listing.name not in securedrop_panel.text
    assert verified_panel is not None
    assert listing.name not in verified_panel.text


def test_directory_users_json_includes_globaleaks_rows(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listings",
        lambda: (listing,),
    )

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200

    row = next(row for row in (response.json or []) if row["display_name"] == listing.name)
    assert row["entry_type"] == "globaleaks"
    assert row["primary_username"] is None
    assert row["is_public_record"] is False
    assert row["is_globaleaks"] is True
    assert row["is_securedrop"] is False
    assert row["is_automated"] is True
    assert row["message_capable"] is False
    assert row["bio"] == listing.description
    assert "location" not in row
    assert row["city"] == listing.geography.city
    assert row["country"] == listing.geography.country
    assert row["subdivision"] == listing.geography.subdivision
    assert row["subdivision_code"] == listing.geography.subdivision_code
    assert row["countries"] == list(listing.geography.countries)
    assert row["practice_tags"] == []
    assert row["source_label"] == listing.source_label
    assert row["directory_section"] == "globaleaks_directory"


def test_directory_globaleaks_cards_do_not_show_location(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listings",
        lambda: (listing,),
    )

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    globaleaks_panel = soup.find(id="globaleaks")
    all_panel = soup.find(id="all")

    globaleaks_card = _find_directory_card(globaleaks_panel, listing.name)
    all_card = _find_directory_card(all_panel, listing.name)

    assert listing.location not in globaleaks_card.get_text(" ", strip=True)
    assert listing.location not in all_card.get_text(" ", strip=True)


def test_directory_users_json_includes_securedrop_rows(client: FlaskClient) -> None:
    listing = _first_securedrop_listing_or_skip()

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200

    row = next(row for row in (response.json or []) if row["display_name"] == listing.name)
    assert row["entry_type"] == "securedrop"
    assert row["primary_username"] is None
    assert row["is_public_record"] is False
    assert row["is_securedrop"] is True
    assert row["is_automated"] is True
    assert row["message_capable"] is False
    assert row["bio"] == listing.description
    assert "location" not in row
    assert row["city"] == listing.geography.city
    assert row["country"] == listing.geography.country
    assert row["subdivision"] == listing.geography.subdivision
    assert row["subdivision_code"] == listing.geography.subdivision_code
    assert row["countries"] == list(listing.geography.countries)
    assert row["practice_tags"] == list(listing.topics)
    assert row["source_label"] == listing.source_label
    assert row["directory_section"] == "securedrop_directory"


def test_directory_securedrop_cards_do_not_show_location(client: FlaskClient) -> None:
    listing = _first_securedrop_listing_or_skip()

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    securedrop_panel = soup.find(id="securedrop")
    all_panel = soup.find(id="all")

    securedrop_card = _find_directory_card(securedrop_panel, listing.name)
    all_card = _find_directory_card(all_panel, listing.name)

    assert listing.location not in securedrop_card.get_text(" ", strip=True)
    assert listing.location not in all_card.get_text(" ", strip=True)


def test_public_record_listing_normalizes_us_state_into_country_and_subdivision() -> None:
    listing = PublicRecordListing(
        id="public-record-usa",
        slug="public-record~usa",
        name="US Public Record Listing",
        website="https://example.org",
        description="US attorney listing.",
        city="Chicago",
        state="IL",
        practice_tags=("Labor",),
        source_label="Official source",
        source_url="https://example.org/source",
    )

    assert listing.geography.city == "Chicago"
    assert listing.geography.country == "United States"
    assert listing.geography.subdivision == "Illinois"
    assert listing.geography.subdivision_code == "IL"
    assert listing.geography.countries == ("United States",)
    assert listing.location == "Chicago, Illinois, United States"


def test_public_record_listing_normalizes_legacy_country_stored_in_state() -> None:
    listing = PublicRecordListing(
        id="public-record-legacy",
        slug="public-record~legacy",
        name="Legacy Public Record Listing",
        website="https://example.org",
        description="Legacy attorney listing.",
        city="Sydney",
        state="Australia",
        practice_tags=("Whistleblower",),
        source_label="Legacy source",
        source_url="https://example.org/source",
    )

    assert listing.geography.city == "Sydney"
    assert listing.geography.country == "Australia"
    assert listing.geography.subdivision is None
    assert listing.geography.subdivision_code is None
    assert listing.geography.countries == ("Australia",)
    assert listing.location == "Sydney, Australia"


def test_public_record_listing_preserves_non_us_subdivision_code() -> None:
    listing = PublicRecordListing(
        id="public-record-australia-state",
        slug="public-record~australia-state",
        name="Australia Public Record Listing",
        website="https://example.org",
        description="Australian attorney listing.",
        city="Sydney",
        state="Australia",
        country="Australia",
        subdivision="New South Wales",
        practice_tags=("Whistleblower",),
        source_label="Official source",
        source_url="https://example.org/source",
    )

    assert listing.geography.city == "Sydney"
    assert listing.geography.country == "Australia"
    assert listing.geography.subdivision == "New South Wales"
    assert listing.geography.subdivision_code == "New South Wales"
    assert listing.geography.countries == ("Australia",)
    assert listing.location == "Sydney, New South Wales, Australia"


def test_securedrop_listing_keeps_multi_country_scope_without_forcing_primary_country() -> None:
    listing = SecureDropDirectoryListing(
        id="securedrop-multi-country",
        slug="securedrop~multi-country",
        name="Multi-Country SecureDrop Listing",
        website="https://example.org",
        description="Multi-country listing.",
        directory_url="https://securedrop.org/directory/multi-country/",
        landing_page_url="https://example.org/landing",
        onion_address="sample1234567890sample1234567890sample1234567890sample12.onion",
        onion_name="Example",
        countries=("All countries", "USA"),
        languages=("English",),
        topics=("investigations",),
        source_label="SecureDrop directory",
        source_url="https://securedrop.org/api/v1/directory/",
    )

    assert listing.geography.country is None
    assert listing.geography.subdivision is None
    assert listing.geography.countries == ("All countries", "United States")
    assert listing.location == "All countries, United States"


def test_directory_all_tab_is_homogeneous_alpha_order_with_info_only_badge(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mocked_usernames = (
        SimpleNamespace(
            username="zulu",
            display_name="Zulu User",
            bio="zulu bio",
            is_verified=False,
            user=SimpleNamespace(is_admin=False, pgp_key="pgp-key"),
        ),
        SimpleNamespace(
            username="bravo",
            display_name="Bravo Info",
            bio="bravo bio",
            is_verified=True,
            user=SimpleNamespace(is_admin=False, pgp_key=""),
        ),
    )
    mocked_public_records = (
        SimpleNamespace(
            id="public-alpha",
            slug="public-alpha",
            name="Alpha Public Listing",
            website="https://alpha.example",
            description="alpha description",
            geography=SimpleNamespace(
                city=None,
                country="United States",
                subdivision="California",
                subdivision_code="CA",
                countries=("United States",),
                location="Global",
            ),
            location="Global",
            practice_tags=("Law",),
            source_label="Public records",
            source_url="https://records.example/alpha",
            directory_section="public_record",
            is_automated=True,
            message_capable=False,
        ),
    )
    mocked_securedrop_listings = (
        SimpleNamespace(
            id="securedrop-charlie",
            slug="securedrop-charlie",
            name="Charlie SecureDrop",
            website="https://charlie.example",
            description="charlie description",
            geography=SimpleNamespace(
                city=None,
                country="United States",
                subdivision=None,
                subdivision_code=None,
                countries=("United States",),
                location="Global",
            ),
            location="Global",
            topics=("Investigations",),
            source_label="SecureDrop directory",
            source_url="https://securedrop.org/api/v1/directory/",
            directory_section="securedrop_directory",
            is_automated=True,
            message_capable=False,
        ),
    )
    mocked_globaleaks_listings = (
        SimpleNamespace(
            id="globaleaks-delta",
            slug="globaleaks-delta",
            name="Delta GlobaLeaks",
            website="https://delta.example",
            description="delta description",
            geography=SimpleNamespace(
                city=None,
                country="Italy",
                subdivision=None,
                subdivision_code=None,
                countries=("Italy",),
                location="Global",
            ),
            location="Global",
            source_label="Automated GlobaLeaks discovery dataset",
            source_url="https://example.org/globaleaks",
            directory_section="globaleaks_directory",
            is_automated=True,
            message_capable=False,
        ),
    )

    monkeypatch.setattr(
        "hushline.routes.directory.get_directory_usernames", lambda: mocked_usernames
    )
    monkeypatch.setattr(
        "hushline.routes.directory.get_public_record_listings",
        lambda: mocked_public_records,
    )
    monkeypatch.setattr(
        "hushline.routes.directory.get_securedrop_directory_listings",
        lambda: mocked_securedrop_listings,
    )
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listings",
        lambda: mocked_globaleaks_listings,
    )

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    all_panel = soup.find(id="all")
    verified_panel = soup.find(id="verified")
    assert all_panel is not None
    assert verified_panel is not None

    assert all_panel.select("p.label") == []
    assert "Info-Only Accounts" not in all_panel.get_text(" ", strip=True)
    assert "Public Record Attorneys" not in all_panel.get_text(" ", strip=True)
    assert "GlobaLeaks Instances" not in all_panel.get_text(" ", strip=True)
    assert "SecureDrop Instances" not in all_panel.get_text(" ", strip=True)

    all_titles = [
        heading.get_text(" ", strip=True) for heading in all_panel.select("article.user h3")
    ]
    assert all_titles == [
        "Alpha Public Listing",
        "Bravo Info",
        "Charlie SecureDrop",
        "Delta GlobaLeaks",
        "Zulu User",
    ]

    info_only_card = next(
        card
        for card in all_panel.select("article.user")
        if card.select_one("h3") and card.select_one("h3").get_text(" ", strip=True) == "Bravo Info"
    )
    assert info_only_card.select_one('span.badge[aria-label="Info-only account"]') is not None
    assert verified_panel.select_one('span.badge[aria-label="Info-only account"]') is None


def test_public_record_seed_regions_have_coverage() -> None:
    listings = _strict_public_record_listings()

    allowed_states = {state for states in DEFAULT_REGION_STATE_MAP.values() for state in states}
    assert all(listing.state in allowed_states for listing in listings)

    if listings:
        us_covered = {listing.state for listing in listings if listing.state in US_STATE_CODES}
        assert us_covered
        assert {"AK", "AL", "AR", "AZ", "CA", "CO", "IL", "OH", "TN", "WA"}.issubset(us_covered)

    assert all(listing.source_url for listing in listings)
    assert all("chambers.com" not in (listing.source_url or "") for listing in listings)

    us_listings = [listing for listing in listings if listing.state in US_STATE_CODES]
    for listing in us_listings:
        source_rule = US_STATE_AUTHORITATIVE_SOURCES[listing.state]
        assert listing.source_label == source_rule["source_label"]
        assert listing.source_url is not None
        hostname = urlparse(listing.source_url).hostname
        assert hostname is not None
        normalized_host = hostname.casefold()
        assert any(
            normalized_host == domain or normalized_host.endswith(f".{domain}")
            for domain in source_rule["allowed_domains"]
        )
        parsed_source_url = urlparse(listing.source_url)
        source_query_pairs = parse_qsl(parsed_source_url.query, keep_blank_values=True)
        assert all(key.casefold() != "listing" for key, _value in source_query_pairs)
        source_fragment_fields = [
            field.strip() for field in parsed_source_url.fragment.split("&") if field.strip()
        ]
        assert all(
            field.split("=", 1)[0].strip().casefold() != "listing"
            for field in source_fragment_fields
        )

        normalized_source_no_fragment = (
            parsed_source_url._replace(fragment="").geturl().casefold().rstrip("/")
        )
        normalized_state_source_no_fragment = (
            urlparse(source_rule["source_url"])
            ._replace(fragment="")
            .geturl()
            .casefold()
            .rstrip("/")
        )
        if normalized_source_no_fragment == normalized_state_source_no_fragment:
            if listing.state == "OH":
                assert re.fullmatch(
                    r"/?\d+/attyinfo/?",
                    parsed_source_url.fragment.strip(),
                    flags=re.IGNORECASE,
                )
                continue
            raise AssertionError(
                "listing source_url points to a generic state source page",
            )


def test_public_record_listing_page_is_read_only(client: FlaskClient) -> None:
    listing = _first_public_record_listing_or_skip()

    response = client.get(url_for("public_record_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    assert soup.select_one('span.badge[aria-label="Attorney listing"]') is not None
    assert soup.select_one('span.badge[aria-label="Automated listing"]') is not None
    assert "🏛️ Public Record" not in page_text
    assert listing.description in page_text
    assert listing.website in response.text
    assert "Source" in page_text
    assert "Location" not in page_text
    assert listing.source_url is not None
    source_link = soup.find("a", href=listing.source_url)
    assert source_link is not None
    assert "Practice Areas" not in page_text
    if listing.geography.city:
        assert listing.geography.city in page_text
    if listing.geography.subdivision:
        assert "State / Region" in page_text
        assert listing.geography.subdivision in page_text
    if listing.geography.country:
        assert "Country" in page_text
        assert listing.geography.country in page_text
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


def test_securedrop_listing_page_is_read_only(client: FlaskClient) -> None:
    listing = _first_securedrop_listing_or_skip()

    response = client.get(url_for("securedrop_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    assert "🛡️ SecureDrop" in page_text
    assert "🤖 Automated" in page_text
    assert listing.description in page_text
    assert listing.onion_address in page_text
    assert listing.source_url in response.text
    assert "Location" not in page_text
    assert 'id="messageForm"' not in response.text
    assert "Send Message" not in response.text

    dir_meta = soup.select_one(".dirMeta")
    assert dir_meta is not None
    dir_meta_text = dir_meta.get_text(" ", strip=True)
    assert dir_meta_text.startswith("🧪 Beta:")
    assert "This listing is automated." in dir_meta_text
    assert "Onion addresses require" in dir_meta_text
    assert "Tor Browser" in dir_meta_text
    assert "risk in your jurisdiction" in dir_meta_text
    assert "Do your research before downloading." in dir_meta_text

    dir_meta_link = dir_meta.find("a")
    assert dir_meta_link is not None
    assert dir_meta_link.text.strip() == "Tor Browser"
    assert dir_meta_link.get("href") == "https://www.torproject.org/download/"


def test_globaleaks_listing_page_is_read_only(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listing",
        lambda _slug: listing,
    )

    response = client.get(url_for("globaleaks_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    assert "🌐 GlobaLeaks" in page_text
    assert "🤖 Automated" in page_text
    assert listing.description in page_text
    assert listing.submission_url in response.text
    assert listing.source_url in response.text
    assert "Location" not in page_text
    assert 'id="messageForm"' not in response.text
    assert "Send Message" not in response.text

    dir_meta = soup.select_one(".dirMeta")
    assert dir_meta is not None
    dir_meta_text = dir_meta.get_text(" ", strip=True)
    assert dir_meta_text.startswith("🧪 Beta:")
    assert "This listing is automated." in dir_meta_text
    assert "Onion addresses require" not in dir_meta_text
    assert "Tor Browser" not in dir_meta_text
    assert dir_meta.find("a") is None


def test_globaleaks_listing_page_mentions_tor_for_onion_submission(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_onion_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listing",
        lambda _slug: listing,
    )

    response = client.get(url_for("globaleaks_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")

    dir_meta = soup.select_one(".dirMeta")
    assert dir_meta is not None
    dir_meta_text = dir_meta.get_text(" ", strip=True)
    assert dir_meta_text.startswith("🧪 Beta:")
    assert "This listing is automated." in dir_meta_text
    assert "Onion addresses require" in dir_meta_text
    assert "Tor Browser" in dir_meta_text
    dir_meta_link = dir_meta.find("a")
    assert dir_meta_link is not None
    assert dir_meta_link.text.strip() == "Tor Browser"
    assert dir_meta_link.get("href") == "https://www.torproject.org/download/"


def test_globaleaks_listing_route_hidden_when_verified_tabs_disabled(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listing",
        lambda _slug: listing,
    )
    client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = False
    try:
        response = client.get(url_for("globaleaks_listing", slug=listing.slug))
    finally:
        client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = True

    assert response.status_code == 404


def test_securedrop_listing_page_omits_landing_page_link_when_missing(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = SecureDropDirectoryListing(
        id="securedrop-sample-without-landing-page",
        slug="securedrop~sample-without-landing-page",
        name="Sample SecureDrop Listing",
        website="https://example.org/securedrop",
        description="Test listing without landing page URL.",
        directory_url="https://securedrop.org/directory/sample-without-landing-page/",
        landing_page_url="",
        onion_address="sample1234567890sample1234567890sample1234567890sample12.onion",
        onion_name="",
        countries=("United States",),
        languages=("English",),
        topics=("investigations",),
        source_label="SecureDrop directory",
        source_url="https://securedrop.org/api/v1/directory/",
    )
    monkeypatch.setattr(
        "hushline.routes.directory.get_securedrop_directory_listing",
        lambda _slug: listing,
    )

    response = client.get(url_for("securedrop_listing", slug=listing.slug))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert "SecureDrop Landing Page" not in soup.get_text(" ", strip=True)
    assert soup.find("a", href="") is None


def test_securedrop_listing_route_hidden_when_verified_tabs_disabled(
    client: FlaskClient,
) -> None:
    listing = _first_securedrop_listing_or_skip()
    client.application.config["DIRECTORY_VERIFIED_TAB_ENABLED"] = False
    try:
        response = client.get(url_for("securedrop_listing", slug=listing.slug))
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


def test_globaleaks_listing_slug_cannot_be_messaged(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = _sample_globaleaks_listing()
    monkeypatch.setattr(
        "hushline.routes.directory.get_globaleaks_directory_listing",
        lambda _slug: listing,
    )

    response = client.get(
        url_for("redirect_submit_message", username=listing.slug),
        follow_redirects=True,
    )
    assert response.status_code == 404


@pytest.mark.local_only()
@pytest.mark.external_network()
def test_public_record_external_links_resolve() -> None:
    link_checker = build_requests_link_checker()
    checked: set[str] = set()
    failures: list[str] = []

    for listing in _strict_public_record_listings():
        for label, url in {
            "website": listing.website,
            "source": listing.source_url,
        }.items():
            if not url or url in checked:
                continue

            checked.add(url)
            check_result = link_checker(url)
            if check_result.definitive_failure:
                reason = check_result.reason or "unknown error"
                failures.append(f"{listing.name} {label} failed ({reason}): {url}")

    assert not failures, "Broken public record links:\n" + "\n".join(failures)

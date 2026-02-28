import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User, get_public_record_listings


def test_directory_accessible(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200
    assert "User Directory" in response.text
    assert "Public Records" in response.text


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
    listing = get_public_record_listings()[0]

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
    listing = get_public_record_listings()[0]

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


def test_public_record_listing_page_is_read_only(client: FlaskClient) -> None:
    listing = get_public_record_listings()[0]

    response = client.get(url_for("public_record_listing", slug=listing.slug))
    assert response.status_code == 200
    assert "🏛️ Public Record" in response.text
    assert "🤖 Automated" in response.text
    assert listing.description in response.text
    assert listing.website in response.text
    assert "Source" not in response.text
    assert "Practice Areas" not in response.text
    assert "cannot receive secure messages" in response.text
    assert 'id="messageForm"' not in response.text
    assert "Send Message" not in response.text


def test_public_record_listing_route_rejects_post(client: FlaskClient) -> None:
    listing = get_public_record_listings()[0]

    response = client.post(url_for("public_record_listing", slug=listing.slug))
    assert response.status_code == 405


def test_public_record_listing_slug_cannot_be_messaged(client: FlaskClient) -> None:
    listing = get_public_record_listings()[0]

    response = client.get(
        url_for("redirect_submit_message", username=listing.slug),
        follow_redirects=True,
    )
    assert response.status_code == 404

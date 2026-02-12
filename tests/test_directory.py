import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def test_directory_accessible(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200
    assert "User Directory" in response.text


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

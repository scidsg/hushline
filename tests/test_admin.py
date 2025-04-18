import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    User,
)
from conftest import make_user


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_shows_verified_on_managed_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["MANAGED_SERVICE"] = True

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Toggle Verified" in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_hides_verified_on_nonmanaged_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["MANAGED_SERVICE"] = False

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Toggle Verified" not in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_managed_service(app: Flask, client: FlaskClient, user: User) -> None:
    app.config["MANAGED_SERVICE"] = True

    response = client.post(
        url_for("admin.toggle_verified", user_id=user.id),
        follow_redirects=True,
    )
    assert response.status_code == 200


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_nonmanaged_service(app: Flask, client: FlaskClient, user: User) -> None:
    app.config["MANAGED_SERVICE"] = False

    response = client.post(
        url_for("admin.toggle_verified", user_id=user.id),
        follow_redirects=True,
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_only_admin(client: FlaskClient, user: User) -> None:
    # Make sure there is only one admin user
    user_count = db.session.query(User).filter_by(is_admin=True).count()
    assert user_count == 1

    # Make sure the user is an admin
    assert user.is_admin is True

    # Toggling admin on the user should return 400
    response = client.post(
        url_for("admin.toggle_admin", user_id=user.id),
        follow_redirects=True,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_multiple_admins(client: FlaskClient, user: User) -> None:
    # Make sure there is only one admin user
    user_count = db.session.query(User).filter_by(is_admin=True).count()
    assert user_count == 1

    # Make another admin
    another_admin = make_user("Test-testtesttesttest-1")
    another_admin.is_admin = True
    db.session.add(user)
    db.session.commit()

    # There should be multiple admins now
    user_count = db.session.query(User).filter_by(is_admin=True).count()
    assert user_count == 2

    # Toggling admin on the user should return 200
    response = client.post(
        url_for("admin.toggle_admin", user_id=user.id),
        follow_redirects=True,
    )
    assert response.status_code == 200

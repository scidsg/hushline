import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.model import (
    User,
)


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

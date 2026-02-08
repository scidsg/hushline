import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    User,
    Username,
)


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_shows_verified_on_managed_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Set Verified" in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_settings_hides_verified_on_nonmanaged_service(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = False

    response = client.get(url_for("settings.admin"), follow_redirects=True)
    assert response.status_code == 200
    assert "Set Verified" not in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_managed_service(
    app: Flask, client: FlaskClient, admin_user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    response = client.post(
        url_for("admin.toggle_verified", user_id=admin_user.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    refreshed_user = db.session.get(User, admin_user.id)
    assert refreshed_user is not None
    assert refreshed_user.primary_username.is_verified is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_on_nonmanaged_service(
    app: Flask, client: FlaskClient, admin_user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = False

    response = client.post(
        url_for("admin.toggle_verified", user_id=admin_user.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_only_admin(client: FlaskClient, admin_user: User) -> None:
    # Make sure there is only one admin user
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1

    # Make sure the user is an admin
    assert admin_user.is_admin is True

    # Toggling admin on the user should return 400
    response = client.post(
        url_for("admin.toggle_admin", user_id=admin_user.id),
        data={"is_admin": "false"},
        follow_redirects=True,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_admin_multiple_admins(
    client: FlaskClient, admin_user: User, admin_user2: User
) -> None:
    assert admin_user.is_admin is True
    assert admin_user2.is_admin is True

    # Make sure there are two admin users
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 2

    # Toggling admin on the user should return 302 (successfully redirect)
    response = client.post(
        url_for("admin.toggle_admin", user_id=admin_user.id), data={"is_admin": "false"}
    )
    assert response.status_code == 302

    # There should be only one admins now
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_toggle_verified_alias_on_managed_service(
    app: Flask, client: FlaskClient, user_alias: Username
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    assert user_alias.is_verified is False

    response = client.post(
        url_for("admin.toggle_verified_username", username_id=user_alias.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    refreshed_alias = db.session.get(Username, user_alias.id)
    assert refreshed_alias is not None
    assert refreshed_alias.is_verified is True


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_user_removes_user(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 302

    deleted_user = db.session.get(User, user.id)
    assert deleted_user is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_only_admin_blocked(client: FlaskClient, admin_user: User) -> None:
    admin_count = db.session.query(User).filter_by(is_admin=True).count()
    assert admin_count == 1

    response = client.post(url_for("admin.delete_user", user_id=admin_user.id))
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_self_blocked(client: FlaskClient, admin_user: User) -> None:
    response = client.post(url_for("admin.delete_user", user_id=admin_user.id))
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_alias_does_not_delete_user(client: FlaskClient, user_alias: Username) -> None:
    user_id = user_alias.user_id

    response = client.post(url_for("admin.delete_username", username_id=user_alias.id))
    assert response.status_code == 302

    remaining_user = db.session.get(User, user_id)
    assert remaining_user is not None

    deleted_alias = db.session.get(Username, user_alias.id)
    assert deleted_alias is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_delete_primary_deletes_aliases(client: FlaskClient, user_alias: Username) -> None:
    user = db.session.get(User, user_alias.user_id)
    assert user is not None

    response = client.post(url_for("admin.delete_user", user_id=user.id))
    assert response.status_code == 302

    remaining_alias = db.session.get(Username, user_alias.id)
    assert remaining_alias is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_admin_actions_require_csrf_token(
    app: Flask, client: FlaskClient, user_alias: Username
) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True

    app.config["USER_VERIFICATION_ENABLED"] = True
    response = client.post(
        url_for("admin.toggle_verified_username", username_id=user_alias.id),
        data={"is_verified": "true"},
    )
    assert response.status_code == 400

    response = client.post(
        url_for("admin.delete_username", username_id=user_alias.id),
    )
    assert response.status_code == 400

    app.config["WTF_CSRF_ENABLED"] = prior_setting

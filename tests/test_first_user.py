import os

from flask import url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session_register

from hushline.db import db
from hushline.model import OrganizationSetting, User, Username


def test_no_users_redirect_to_register(client: FlaskClient) -> None:
    user_count = db.session.query(User).count()
    assert user_count == 0

    response = client.get(url_for("index"))
    assert response.status_code == 302
    assert response.location == url_for("register")


def test_no_users_register_should_show_alert(client: FlaskClient) -> None:
    user_count = db.session.query(User).count()
    assert user_count == 0

    response = client.get(url_for("register"))
    assert response.status_code == 200

    assert "Create the Admin User" in response.text


def test_some_users_register_should_hide_alert(client: FlaskClient, user_password: str) -> None:
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=True,
    )

    user_count = db.session.query(User).count()
    assert user_count == 0

    user = User(password=user_password)
    user.tier_id = 1
    db.session.add(user)
    db.session.commit()
    assert db.session.query(User).count() == 1

    response = client.get(url_for("register"))
    assert response.status_code == 200

    assert "Create the Admin User" not in response.text


def test_first_user_is_admin(client: FlaskClient) -> None:
    user_count = db.session.query(User).count()
    assert user_count == 0

    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "test_user"

    captcha_answer = get_captcha_from_session_register(client)

    response = client.post(
        url_for("register"),
        data={
            "username": username,
            "password": "SecurePassword123!",
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration successful!" in response.text

    # The user should be an admin
    user = db.session.scalars(db.select(User)).one()
    assert user.is_admin
    assert user.primary_username.show_in_directory


def test_second_user_is_not_admin(client: FlaskClient, user_password: str) -> None:
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=True,
    )

    user_count = db.session.query(User).count()
    assert user_count == 0

    user = User(password=user_password)
    user.tier_id = 1
    user.is_admin = True
    db.session.add(user)
    db.session.commit()
    assert db.session.query(User).count() == 1

    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "test_user"

    captcha_answer = get_captcha_from_session_register(client)

    response = client.post(
        url_for("register"),
        data={
            "username": username,
            "password": "SecurePassword123!",
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration successful!" in response.text

    # The user should not be an admin
    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert not uname.user.is_admin
    assert not uname.show_in_directory

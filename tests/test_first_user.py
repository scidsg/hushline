from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


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

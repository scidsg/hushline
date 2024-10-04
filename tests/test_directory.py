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

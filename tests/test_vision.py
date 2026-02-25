import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def test_vision_requires_authentication(client: FlaskClient) -> None:
    response = client.get(url_for("vision"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


def test_vision_redirects_to_login_when_session_user_missing(client: FlaskClient) -> None:
    with client.session_transaction() as session:
        session["is_authenticated"] = True
        session["user_id"] = 999999
        session["session_id"] = "invalid-session-id"

    response = client.get(url_for("vision"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_vision_renders_for_free_user(client: FlaskClient, user: User) -> None:
    user.tier_id = None
    db.session.commit()

    response = client.get(url_for("vision"))
    assert response.status_code == 200
    assert "Vision Assistant" in response.text
    assert "Email Validation" in response.text
    assert 'aria-current="page"' in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_vision_renders_for_paid_user(client: FlaskClient) -> None:
    response = client.get(url_for("vision"))
    assert response.status_code == 200
    assert "Vision Assistant" in response.text

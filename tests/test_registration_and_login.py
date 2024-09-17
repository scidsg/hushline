import os

from flask import url_for
from flask.testing import FlaskClient

from hushline import db
from hushline.model import InviteCode, Username


def test_user_registration_with_invite_code_disabled(client: FlaskClient) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "test_user"
    response = client.post(
        url_for("register"),
        data={"username": username, "password": "SecurePassword123!"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == username


def test_user_registration_with_invite_code_enabled(client: FlaskClient) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "True"
    username = "newuser"

    code = InviteCode()
    db.session.add(code)
    db.session.commit()

    response = client.post(
        url_for("register"),
        data={
            "username": username,
            "password": "SecurePassword123!",
            "invite_code": code.code,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == "newuser"


def test_register_page_loads(client: FlaskClient) -> None:
    response = client.get(url_for("register"))
    assert response.status_code == 200
    assert "<h2>Register</h2>" in response.text


def test_login_link(client: FlaskClient) -> None:
    response = client.get(url_for("register"))
    assert response.status_code == 200

    assert 'href="/login"' in response.text

    login_response = client.get(url_for("login"))
    assert login_response.status_code == 200
    assert "<h2>Login</h2>" in login_response.text


def test_registration_link(client: FlaskClient) -> None:
    response = client.get(url_for("login"))
    assert response.status_code == 200
    assert 'href="/register"' in response.text

    register_response = client.get(url_for("register"))
    assert register_response.status_code == 200
    assert "<h2>Register</h2>" in register_response.text


def test_user_login_after_registration(client: FlaskClient) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    client.post(
        url_for("register"),
        data={"username": username, "password": password},
        follow_redirects=True,
    )

    login_response = client.post(
        url_for("login"), data={"username": username, "password": password}, follow_redirects=True
    )
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text
    assert 'href="/inbox?username=newuser"' in login_response.text


def test_user_login_with_incorrect_password(client: FlaskClient) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    client.post(
        url_for("register"),
        data={"username": username, "password": password},
        follow_redirects=True,
    )

    login_response = client.post(
        url_for("login"),
        data={"username": username, "password": password + "not correct"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Inbox" not in login_response.text
    assert 'href="/inbox?username=newuser"' not in login_response.text
    assert "Invalid username or password" in login_response.text

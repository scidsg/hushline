import os

from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import InviteCode, Username


def get_captcha_from_session(client: FlaskClient) -> str:
    """Retrieve the CAPTCHA answer from the session."""
    # Simulate loading the registration page to generate the CAPTCHA
    response = client.get(url_for("register"))
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer, "CAPTCHA answer not found in session"
        return captcha_answer


def test_user_registration_with_invite_code_disabled(client: FlaskClient) -> None:
    """Test registration without requiring an invite code."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "test_user"

    captcha_answer = get_captcha_from_session(client)

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
    assert "Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == username


def test_user_registration_with_invite_code_enabled(client: FlaskClient) -> None:
    """Test registration when an invite code is required."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "True"
    username = "newuser"

    # Generate an invite code
    code = InviteCode()
    db.session.add(code)
    db.session.commit()

    captcha_answer = get_captcha_from_session(client)

    response = client.post(
        url_for("register"),
        data={
            "username": username,
            "password": "SecurePassword123!",
            "invite_code": code.code,
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == "newuser"


def test_register_page_loads(client: FlaskClient) -> None:
    """Test if the registration page loads successfully."""
    response = client.get(url_for("register"))
    assert response.status_code == 200
    assert "<h2>Register</h2>" in response.text


def test_user_login_after_registration(client: FlaskClient) -> None:
    """Test successful login after user registration."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    captcha_answer = get_captcha_from_session(client)

    # Register the user
    response = client.post(
        url_for("register"),
        data={"username": username, "password": password, "captcha_answer": captcha_answer},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration successful!" in response.text

    # Attempt login
    login_response = client.post(
        url_for("login"), data={"username": username, "password": password}, follow_redirects=True
    )
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text


def test_user_login_with_incorrect_password(client: FlaskClient) -> None:
    """Test failed login with an incorrect password."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    captcha_answer = get_captcha_from_session(client)

    # Register the user
    response = client.post(
        url_for("register"),
        data={"username": username, "password": password, "captcha_answer": captcha_answer},
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Attempt login with incorrect password
    login_response = client.post(
        url_for("login"),
        data={"username": username, "password": password + "not correct"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Inbox" not in login_response.text
    assert "Invalid username or password" in login_response.text

import os

from flask import url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session_register

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User, Username


def test_user_registration_disabled(client: FlaskClient, user: User) -> None:
    """Make sure registration doesn't work when it's disabled."""
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=False,
    )
    db.session.commit()

    # The registration page should redirect to the index page
    response = client.get(
        url_for("register"),
    )
    assert response.status_code == 302
    assert response.headers["Location"] == url_for("index")

    # The index page should not have the registration link
    response = client.get(
        url_for("index"),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Register" not in response.text


def test_user_registration_disabled_first_user(client: FlaskClient) -> None:
    """When registration is disabled, the first user should be able to register."""
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=False,
    )
    db.session.commit()

    # Make sure there are zero users
    assert db.session.query(User).count() == 0

    # The registration page should load
    response = client.get(
        url_for("register"),
    )
    assert response.status_code == 200


def test_user_registration_with_invite_code_disabled(client: FlaskClient) -> None:
    """Test registration without requiring an invite code."""
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

    captcha_answer = get_captcha_from_session_register(client)

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


def test_user_registration_rejects_case_insensitive_duplicate(client: FlaskClient) -> None:
    """Usernames should be unique regardless of case."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=True,
    )
    db.session.commit()

    existing_user = User(password="SecurePassword123!")  # noqa: S106
    db.session.add(existing_user)
    db.session.flush()
    db.session.add(Username(user_id=existing_user.id, _username="CaseUser", is_primary=True))
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)

    response = client.post(
        url_for("register"),
        data={
            "username": "caseuser",
            "password": "SecurePassword123!",
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Username already taken." in response.text


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

    captcha_answer = get_captcha_from_session_register(client)

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


def test_user_login_case_insensitive(client: FlaskClient) -> None:
    """Login should accept username case-insensitively."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    captcha_answer = get_captcha_from_session_register(client)

    response = client.post(
        url_for("register"),
        data={"username": username, "password": password, "captcha_answer": captcha_answer},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Registration successful!" in response.text

    login_response = client.post(
        url_for("login"),
        data={"username": username.upper(), "password": password},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text


def test_user_login_with_incorrect_password(client: FlaskClient) -> None:
    """Test failed login with an incorrect password."""
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    username = "newuser"
    password = "SecurePassword123!"

    captcha_answer = get_captcha_from_session_register(client)

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

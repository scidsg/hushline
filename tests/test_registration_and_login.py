import os
from unittest.mock import MagicMock, patch

from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session_register
from sqlalchemy.exc import IntegrityError, MultipleResultsFound
from werkzeug.security import generate_password_hash

from hushline.config import (
    PASSWORD_HASH_REHASH_ON_AUTH_ENABLED,
    PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT,
)
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User, Username
from hushline.password_hasher import PINNED_WERKZEUG_SCRYPT_METHOD, verify_primary_password_hash


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
    assert "👍 Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == username
    assert uname.user.password_hash.startswith("$scrypt$")


def test_user_registration_writes_pinned_werkzeug_scrypt_hash_when_enabled(
    app: Flask, client: FlaskClient
) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    app.config[PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT] = True
    username = "test_user"
    password = "SecurePassword123!"

    captcha_answer = get_captcha_from_session_register(client)

    response = client.post(
        url_for("register"),
        data={
            "username": username,
            "password": password,
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration successful!" in response.text

    uname = db.session.scalars(db.select(Username).filter_by(_username=username)).one()
    assert uname.username == username
    assert uname.user.password_hash.startswith(f"{PINNED_WERKZEUG_SCRYPT_METHOD}$")

    login_response = client.post(
        url_for("login"),
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text

    client.get(url_for("logout"), follow_redirects=True)

    invalid_login_response = client.post(
        url_for("login"),
        data={"username": username, "password": f"{password}not correct"},
        follow_redirects=True,
    )
    assert invalid_login_response.status_code == 200
    assert "⛔️ Invalid username or password." in invalid_login_response.text


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
    assert "👍 Registration successful!" in response.text

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


def test_username_db_constraint_rejects_case_insensitive_duplicate(client: FlaskClient) -> None:
    user1 = User(password="SecurePassword123!")  # noqa: S106
    user2 = User(password="SecurePassword123!")  # noqa: S106
    db.session.add_all([user1, user2])
    db.session.flush()

    db.session.add(Username(user_id=user1.id, _username="CaseUser", is_primary=True))
    db.session.commit()

    db.session.add(Username(user_id=user2.id, _username="caseuser", is_primary=True))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return

    raise AssertionError("Expected case-insensitive duplicate to violate database uniqueness")


def test_user_registration_handles_case_insensitive_race_integrity_error(
    client: FlaskClient,
) -> None:
    os.environ["REGISTRATION_CODES_REQUIRED"] = "False"
    OrganizationSetting.upsert(
        key=OrganizationSetting.REGISTRATION_ENABLED,
        value=True,
    )
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)

    with (
        patch(
            "hushline.routes.auth.db.session.scalar",
            side_effect=[False, True],
        ),
        patch(
            "hushline.routes.auth.db.session.commit",
            side_effect=IntegrityError("stmt", "params", Exception("duplicate username")),
        ),
    ):
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
    assert 'data-submit-spinner="true"' in response.text


def test_login_page_loads(client: FlaskClient) -> None:
    """Test if the login page loads successfully."""
    response = client.get(url_for("login"))
    assert response.status_code == 200
    assert "<h2>Login</h2>" in response.text
    assert 'data-submit-spinner="true"' in response.text


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
    assert "👍 Registration successful!" in response.text

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
    assert "👍 Registration successful!" in response.text

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
    assert "⛔️ Invalid username or password." in login_response.text


def test_user_login_with_native_werkzeug_scrypt_hash(
    client: FlaskClient, user: User, user_password: str
) -> None:
    native_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = native_hash
    db.session.commit()

    login_response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=True,
    )

    db.session.refresh(user)
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text
    assert user.password_hash == native_hash


def test_user_login_rehashes_legacy_passlib_hash_when_enabled(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = True
    original_hash = user.password_hash

    with patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry_mock:
        login_response = client.post(
            url_for("login"),
            data={"username": user.primary_username.username, "password": user_password},
            follow_redirects=True,
        )

    db.session.refresh(user)
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text
    assert user.password_hash != original_hash
    assert user.password_hash.startswith(f"{PINNED_WERKZEUG_SCRYPT_METHOD}$")
    assert verify_primary_password_hash(user_password, user.password_hash) is True
    telemetry_mock.assert_called_once_with(original_hash, success=True)


def test_user_login_does_not_rehash_legacy_passlib_hash_when_disabled(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = False
    original_hash = user.password_hash

    with patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry_mock:
        login_response = client.post(
            url_for("login"),
            data={"username": user.primary_username.username, "password": user_password},
            follow_redirects=True,
        )

    db.session.refresh(user)
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text
    assert user.password_hash == original_hash
    telemetry_mock.assert_not_called()


def test_user_login_rehash_failure_preserves_legacy_passlib_hash(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = True
    original_hash = user.password_hash

    with (
        patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry_mock,
        patch("hushline.routes.auth.db.session.commit", side_effect=RuntimeError("boom")),
    ):
        response = client.post(
            url_for("login"),
            data={"username": user.primary_username.username, "password": user_password},
            follow_redirects=True,
        )

    db.session.refresh(user)
    assert response.status_code == 500
    assert user.password_hash == original_hash
    telemetry_mock.assert_called_once_with(original_hash, success=False)


def test_user_login_handles_case_insensitive_duplicate_rows(
    app: Flask, client: FlaskClient
) -> None:
    with (
        patch(
            "hushline.routes.auth.db.session.scalars",
            return_value=MagicMock(
                one_or_none=MagicMock(side_effect=MultipleResultsFound),
            ),
        ),
        patch("hushline.routes.auth.flash") as flash_mock,
        patch("hushline.routes.auth.render_template", return_value="login page"),
    ):
        response = client.post(
            url_for("login"),
            data={"username": "CaseUser", "password": "SecurePassword123!"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    flash_mock.assert_called_with("⛔️ Invalid username or password.")

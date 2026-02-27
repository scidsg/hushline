from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User
from tests.helpers import get_captcha_from_session_register


@pytest.mark.usefixtures("_authenticated_user")
def test_register_redirects_when_already_logged_in(client: FlaskClient) -> None:
    response = client.get(url_for("register"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


def test_register_rejects_incorrect_captcha(client: FlaskClient, user: User) -> None:
    _ = user
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, False)
    db.session.commit()

    _ = get_captcha_from_session_register(client)
    response = client.post(
        url_for("register"),
        data={
            "username": "new-user-captcha",
            "password": "SecurePassword123!",
            "captcha_answer": "9999",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "⛔️ Incorrect CAPTCHA. Please try again." in response.text


def test_register_rejects_invalid_invite_code(client: FlaskClient, user: User) -> None:
    _ = user
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, True)
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)
    response = client.post(
        url_for("register"),
        data={
            "username": "new-user-invalid-invite",
            "password": "SecurePassword123!",
            "invite_code": "not-a-valid-code",
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid or expired invite code" in response.text


def test_register_rejects_expired_invite_code(client: FlaskClient, user: User) -> None:
    _ = user
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, True)
    db.session.commit()

    invite_code = InviteCode()
    invite_code.expiration_date = datetime.now(UTC) - timedelta(days=1)
    db.session.add(invite_code)
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)
    response = client.post(
        url_for("register"),
        data={
            "username": "new-user-expired-invite",
            "password": "SecurePassword123!",
            "invite_code": invite_code.code,
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid or expired invite code" in response.text


def test_register_valid_invite_code_deletes_code(client: FlaskClient, user: User) -> None:
    _ = user
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, True)
    db.session.commit()

    invite_code = InviteCode()
    db.session.add(invite_code)
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)
    response = client.post(
        url_for("register"),
        data={
            "username": "new-user-valid-invite",
            "password": "SecurePassword123!",
            "invite_code": invite_code.code,
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration successful!" in response.text
    assert db.session.get(InviteCode, invite_code.id) is None


@pytest.mark.usefixtures("_authenticated_user")
def test_login_redirects_when_already_logged_in(client: FlaskClient) -> None:
    response = client.get(url_for("login"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


def test_login_redirects_to_select_tier_when_premium_enabled(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    user.onboarding_complete = True
    user.tier_id = None
    db.session.commit()

    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("premium.select_tier"))


def test_verify_2fa_login_redirects_to_login_and_clears_session_for_missing_user(
    client: FlaskClient,
) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = 999999
        sess["session_id"] = "invalid-session-id"
        sess["is_authenticated"] = False
        sess["username"] = "missing-user"

    response = client.get(url_for("verify_2fa_login"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))
    with client.session_transaction() as sess:
        assert "user_id" not in sess


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_login_redirects_to_inbox_when_already_authenticated(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("verify_2fa_login"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_login_rejects_when_user_has_no_totp_secret(
    client: FlaskClient, user: User
) -> None:
    user.totp_secret = None
    db.session.commit()
    with client.session_transaction() as sess:
        sess["is_authenticated"] = False

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": "123456"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_login_success_redirects_to_onboarding(client: FlaskClient, user: User) -> None:
    totp_secret = pyotp.random_base32()
    user.totp_secret = totp_secret
    user.onboarding_complete = False
    db.session.commit()
    with client.session_transaction() as sess:
        sess["is_authenticated"] = False

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(totp_secret).now()},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_login_success_redirects_to_select_tier_when_enabled(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    totp_secret = pyotp.random_base32()
    user.totp_secret = totp_secret
    user.onboarding_complete = True
    user.tier_id = None
    db.session.commit()
    with client.session_transaction() as sess:
        sess["is_authenticated"] = False

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(totp_secret).now()},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("premium.select_tier"))

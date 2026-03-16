from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pyotp
import pytest
from flask import Flask, session, url_for
from flask.testing import FlaskClient
from passlib.hash import scrypt
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from hushline.auth import (
    AUTH_SESSION_KEYS,
    PENDING_PASSWORD_REHASH_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY,
    POST_AUTH_REDIRECT_SESSION_KEY,
)
from hushline.config import PASSWORD_HASH_REHASH_ON_AUTH_ENABLED
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, User
from hushline.routes.auth import _apply_pending_password_rehash, _password_hash_digest
from tests.helpers import get_captcha_from_session_register

TOTP_SECRET = "KBOVHCCELV67CYGOQ2QYU5SCNYVAREMH"


def _assert_auth_session_cleared(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        for key in AUTH_SESSION_KEYS:
            assert key not in sess


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


def test_apply_pending_password_rehash_rejects_invalid_session_state(
    app: Flask, user: User
) -> None:
    with app.test_request_context("/verify-2fa-login", method="POST"):
        session[PENDING_PASSWORD_REHASH_SESSION_KEY] = 123
        session[PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY] = _password_hash_digest(
            user.password_hash
        )

        with pytest.raises(RuntimeError, match="Pending password rehash state was invalid"):
            _apply_pending_password_rehash(user, source_hash=user.password_hash)

        assert PENDING_PASSWORD_REHASH_SESSION_KEY not in session
        assert PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY not in session


def test_apply_pending_password_rehash_rejects_non_legacy_source_hash(
    app: Flask, user: User
) -> None:
    source_hash = generate_password_hash("SecurePassword123!", method="scrypt")

    with app.test_request_context("/verify-2fa-login", method="POST"):
        session[PENDING_PASSWORD_REHASH_SESSION_KEY] = "replacement-hash"
        session[PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY] = _password_hash_digest(
            source_hash
        )

        with pytest.raises(RuntimeError, match="Pending password rehash source was not legacy"):
            _apply_pending_password_rehash(user, source_hash=source_hash)

        assert PENDING_PASSWORD_REHASH_SESSION_KEY not in session
        assert PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY not in session


def test_apply_pending_password_rehash_rejects_mismatched_source_digest(
    app: Flask, user: User, user_password: str
) -> None:
    source_hash = scrypt.hash(user_password)

    with app.test_request_context("/verify-2fa-login", method="POST"):
        session[PENDING_PASSWORD_REHASH_SESSION_KEY] = "replacement-hash"
        session[PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY] = _password_hash_digest(
            f"{source_hash}-stale"
        )

        with pytest.raises(RuntimeError, match="Pending password rehash source no longer matched"):
            _apply_pending_password_rehash(user, source_hash=source_hash)

        assert PENDING_PASSWORD_REHASH_SESSION_KEY not in session
        assert PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY not in session


def test_register_handles_unexpected_integrity_error(
    app: Flask, client: FlaskClient, user: User
) -> None:
    _ = user
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, False)
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)

    with (
        patch("hushline.routes.auth.db.session.scalar", side_effect=[False, False]),
        patch(
            "hushline.routes.auth.db.session.commit",
            side_effect=IntegrityError("stmt", "params", Exception("boom")),
        ),
        patch.object(app.logger, "error") as logger_error,
    ):
        response = client.post(
            url_for("register"),
            data={
                "username": "new-user-int-error",
                "password": "SecurePassword123!",
                "captcha_answer": captcha_answer,
            },
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert "⛔️ Internal server error. Registration failed." in response.text
    logger_error.assert_called_once_with("Unexpected registration error", exc_info=True)


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


def test_login_redirects_to_original_protected_page(
    client: FlaskClient, user: User, user_password: str
) -> None:
    response = client.get(url_for("settings.profile"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))

    with client.session_transaction() as sess:
        assert sess[POST_AUTH_REDIRECT_SESSION_KEY] == url_for("settings.profile")

    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.profile"))

    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess


def test_login_clears_auth_session_when_2fa_commit_fails(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = True
    original_password_hash = scrypt.hash(user_password)
    original_session_id = user.session_id
    user._password_hash = original_password_hash
    user.totp_secret = TOTP_SECRET
    db.session.commit()

    with (
        patch("hushline.routes.auth.db.session.commit", side_effect=RuntimeError("boom")),
        patch(
            "hushline.routes.auth.db.session.rollback", wraps=db.session.rollback
        ) as rollback_mock,
        patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry_mock,
    ):
        response = client.post(
            url_for("login"),
            data={"username": user.primary_username.username, "password": user_password},
            follow_redirects=True,
        )

    db.session.refresh(user)
    assert response.status_code == 500
    assert user.password_hash == original_password_hash
    assert user.session_id == original_session_id
    rollback_mock.assert_called()
    telemetry_mock.assert_not_called()
    _assert_auth_session_cleared(client)


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


def test_verify_2fa_login_redirects_to_original_protected_page(
    client: FlaskClient, user: User, user_password: str
) -> None:
    totp_secret = pyotp.random_base32()
    user.totp_secret = totp_secret
    db.session.commit()

    response = client.get(url_for("settings.profile"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))

    with client.session_transaction() as sess:
        assert sess[POST_AUTH_REDIRECT_SESSION_KEY] == url_for("settings.profile")

    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("verify_2fa_login"))

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(totp_secret).now()},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.profile"))

    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess


def test_verify_2fa_login_failed_rehash_commit_clears_auth_session(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    app.config[PASSWORD_HASH_REHASH_ON_AUTH_ENABLED] = True
    original_password_hash = scrypt.hash(user_password)
    replacement_hash = generate_password_hash(user_password, method="scrypt")
    user._password_hash = original_password_hash
    user.totp_secret = TOTP_SECRET
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["session_id"] = user.session_id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = False
        sess[PENDING_PASSWORD_REHASH_SESSION_KEY] = replacement_hash
        sess[PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY] = _password_hash_digest(
            original_password_hash
        )

    with (
        patch("hushline.routes.auth.db.session.commit", side_effect=RuntimeError("boom")),
        patch(
            "hushline.routes.auth.db.session.rollback", wraps=db.session.rollback
        ) as rollback_mock,
        patch("hushline.routes.auth.emit_password_rehash_on_auth_telemetry") as telemetry_mock,
    ):
        response = client.post(
            url_for("verify_2fa_login"),
            data={"verification_code": pyotp.TOTP(TOTP_SECRET).now()},
            follow_redirects=True,
        )

    db.session.refresh(user)
    assert response.status_code == 500
    assert user.password_hash == original_password_hash
    rollback_mock.assert_called()
    telemetry_mock.assert_called_once_with(original_password_hash, success=False)
    _assert_auth_session_cleared(client)

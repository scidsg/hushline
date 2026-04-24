from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
    stash_post_auth_redirect,
)
from hushline.config import PASSWORD_HASH_REHASH_ON_AUTH_ENABLED
from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting, PasswordResetToken, User
from hushline.routes.auth import (
    PASSWORD_RESET_CONFIRMATION_MESSAGE,
    PASSWORD_RESET_INVALID_LINK_MESSAGE,
    _apply_pending_password_rehash,
    _lock_first_user_registration,
    _password_hash_digest,
)
from tests.helpers import (
    get_captcha_from_session_password_reset,
    get_captcha_from_session_register,
)

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


def test_register_requires_invite_code_by_default_for_first_user(client: FlaskClient) -> None:
    response = client.get(url_for("register"))

    assert response.status_code == 200
    assert "Invite Code" in response.text

    captcha_answer = get_captcha_from_session_register(client)
    response = client.post(
        url_for("register"),
        data={
            "username": "first-user-without-invite",
            "password": "SecurePassword123!",
            "captcha_answer": captcha_answer,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "This field is required." in response.text
    assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0


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


def _enable_password_reset_email(user: User) -> None:
    user.enable_email_notifications = True
    user.email = "recipient@example.com"
    db.session.commit()


def _extract_reset_token(email_body: str) -> str:
    marker = "/password-reset/"
    assert marker in email_body
    return email_body.split(marker, 1)[1].split()[0]


def test_password_reset_request_is_generic_and_sends_only_for_eligible_account(
    app: Flask, client: FlaskClient, user: User, user2: User
) -> None:
    app.config["PUBLIC_BASE_URL"] = "https://safe.example"
    user2.enable_email_notifications = False
    user2.email = "ineligible@example.com"
    _enable_password_reset_email(user)

    response = client.get(url_for("login"))
    assert response.status_code == 200
    assert url_for("request_password_reset") in response.text

    with patch("hushline.routes.auth.send_email_to_user_recipients") as send_email_mock:
        unknown_captcha = get_captcha_from_session_password_reset(client)
        unknown_response = client.post(
            url_for("request_password_reset"),
            data={"username": "not-a-real-user", "captcha_answer": unknown_captcha},
        )
        ineligible_captcha = get_captcha_from_session_password_reset(client)
        ineligible_response = client.post(
            url_for("request_password_reset"),
            data={
                "username": user2.primary_username.username,
                "captcha_answer": ineligible_captcha,
            },
        )
        eligible_captcha = get_captcha_from_session_password_reset(client)
        eligible_response = client.post(
            url_for("request_password_reset"),
            data={
                "username": user.primary_username.username.upper(),
                "captcha_answer": eligible_captcha,
            },
        )

    assert unknown_response.status_code == 200
    assert ineligible_response.status_code == 200
    assert eligible_response.status_code == 200
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in unknown_response.text
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in ineligible_response.text
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in eligible_response.text
    send_email_mock.assert_called_once()
    sent_user, subject, body = send_email_mock.call_args.args
    assert sent_user == user
    assert subject == "Hush Line password reset"
    assert "https://safe.example/password-reset/" in body
    assert "localhost" not in body
    raw_token = _extract_reset_token(body)
    token_hash = PasswordResetToken.hash_password_reset_token(raw_token)
    token_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == token_hash,
        )
    )
    assert token_count == 1


def test_password_reset_sets_new_password_and_consumes_token(
    client: FlaskClient, user: User, user_password: str
) -> None:
    _enable_password_reset_email(user)
    original_session_id = user.session_id

    with patch("hushline.routes.auth.send_email_to_user_recipients") as send_email_mock:
        captcha_answer = get_captcha_from_session_password_reset(client)
        client.post(
            url_for("request_password_reset"),
            data={"username": user.primary_username.username, "captcha_answer": captcha_answer},
        )

    raw_token = _extract_reset_token(send_email_mock.call_args.args[2])

    invalid_response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": "short"},
    )
    assert invalid_response.status_code == 400
    assert "Field must be between" in invalid_response.text

    repeat_response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": user_password},
    )
    assert repeat_response.status_code == 400
    assert "Cannot choose a repeat password." in repeat_response.text

    new_password = "ResetPassword123!!"
    response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": new_password},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))
    db.session.refresh(user)
    assert user.session_id != original_session_id
    assert user.check_password(new_password)
    assert not user.check_password(user_password)
    token = db.session.scalars(db.select(PasswordResetToken)).one()
    assert token.used_at is not None

    reused_response = client.get(url_for("reset_password", token=raw_token), follow_redirects=True)
    assert reused_response.status_code == 200
    assert PASSWORD_RESET_INVALID_LINK_MESSAGE in reused_response.text
    assert "Reset Password" in reused_response.text


def test_password_reset_rejects_expired_and_unknown_tokens(client: FlaskClient, user: User) -> None:
    reset_token, raw_token = PasswordResetToken.create_for_user(
        user.id,
        ttl=timedelta(minutes=-1),
    )
    db.session.add(reset_token)
    db.session.commit()

    response = client.get(url_for("reset_password", token=raw_token), follow_redirects=True)

    assert response.status_code == 200
    assert PASSWORD_RESET_INVALID_LINK_MESSAGE in response.text
    assert "Reset Password" in response.text

    response = client.get(
        url_for("reset_password", token="not-a-token"),  # noqa: S106
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert PASSWORD_RESET_INVALID_LINK_MESSAGE in response.text
    assert "Reset Password" in response.text


def test_password_reset_request_rate_limits_repeated_identifier(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["PASSWORD_RESET_RATE_LIMIT_IDENTIFIER_MAX"] = 1
    app.config["PASSWORD_RESET_RATE_LIMIT_IP_MAX"] = 100
    _enable_password_reset_email(user)

    with patch("hushline.routes.auth.send_email_to_user_recipients") as send_email_mock:
        first_captcha = get_captcha_from_session_password_reset(client)
        first = client.post(
            url_for("request_password_reset"),
            data={"username": user.primary_username.username, "captcha_answer": first_captcha},
        )
        second_captcha = get_captcha_from_session_password_reset(client)
        second = client.post(
            url_for("request_password_reset"),
            data={"username": user.primary_username.username, "captcha_answer": second_captcha},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in second.text
    send_email_mock.assert_called_once()


def test_password_reset_request_rejects_incorrect_captcha(client: FlaskClient, user: User) -> None:
    _enable_password_reset_email(user)
    response = client.get(url_for("request_password_reset"))

    assert response.status_code == 200
    assert "Solve the math problem to request reset instructions." in response.text

    with patch("hushline.routes.auth.send_email_to_user_recipients") as send_email_mock:
        response = client.post(
            url_for("request_password_reset"),
            data={"username": user.primary_username.username, "captcha_answer": "9999"},
        )

    assert response.status_code == 200
    assert "⛔️ Incorrect CAPTCHA. Please try again." in response.text
    send_email_mock.assert_not_called()


def test_stash_post_auth_redirect_skips_logout_and_preserves_session(app: Flask) -> None:
    with app.test_request_context("/logout", method="GET"):
        session["sentinel"] = "keep"
        session[POST_AUTH_REDIRECT_SESSION_KEY] = "/already-set"

        with patch(
            "hushline.auth.request",
            SimpleNamespace(method="GET", endpoint="logout", full_path="/logout"),
        ):
            stash_post_auth_redirect()

        assert session["sentinel"] == "keep"
        assert session[POST_AUTH_REDIRECT_SESSION_KEY] == "/already-set"


def test_stash_post_auth_redirect_rejects_unsafe_target_and_preserves_session(app: Flask) -> None:
    with app.test_request_context("/settings/profile", method="GET"):
        session["sentinel"] = "keep"
        session[POST_AUTH_REDIRECT_SESSION_KEY] = "/already-set"

        with patch(
            "hushline.auth.request",
            SimpleNamespace(
                method="GET",
                endpoint="settings.profile",
                full_path="https://example.com/phish",
            ),
        ):
            stash_post_auth_redirect()

        assert session["sentinel"] == "keep"
        assert session[POST_AUTH_REDIRECT_SESSION_KEY] == "/already-set"


@pytest.mark.parametrize(
    "bind",
    [
        None,
        SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
    ],
)
def test_lock_first_user_registration_noops_without_postgres_bind(bind: object) -> None:
    with (
        patch("hushline.routes.auth.db.session.get_bind", return_value=bind),
        patch("hushline.routes.auth.db.session.execute") as execute_mock,
    ):
        _lock_first_user_registration()

    execute_mock.assert_not_called()


def test_register_rejects_when_first_user_recheck_finds_existing_user(
    client: FlaskClient,
) -> None:
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_CODES_REQUIRED, False)
    db.session.commit()

    captcha_answer = get_captcha_from_session_register(client)

    query_counts = iter((0, 1))

    def _fake_query(model: type[User]) -> SimpleNamespace:
        assert model is User
        return SimpleNamespace(count=lambda: next(query_counts))

    with (
        patch("hushline.routes.auth._lock_first_user_registration") as lock_mock,
        patch("hushline.routes.auth.db.session.query", side_effect=_fake_query),
    ):
        response = client.post(
            url_for("register"),
            data={
                "username": "late-first-user",
                "password": "SecurePassword123!",
                "captcha_answer": captcha_answer,
            },
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("index"))
    lock_mock.assert_called_once_with()
    assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0
    with client.session_transaction() as sess:
        assert ["message", "⛔️ Registration is disabled."] in sess["_flashes"]


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
def test_verify_2fa_login_requires_csrf_token(app: Flask, client: FlaskClient, user: User) -> None:
    totp_secret = pyotp.random_base32()
    user.totp_secret = totp_secret
    db.session.commit()
    with client.session_transaction() as sess:
        sess["is_authenticated"] = False

    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("verify_2fa_login"),
            data={"verification_code": pyotp.TOTP(totp_secret).now()},
            follow_redirects=False,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("is_authenticated") is False


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

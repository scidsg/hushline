import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pyotp
import pytest
from flask import Flask, session, url_for
from flask.testing import FlaskClient
from passlib.hash import scrypt
from sqlalchemy.exc import IntegrityError, MultipleResultsFound
from werkzeug.security import generate_password_hash

from hushline.auth import (
    AUTH_SESSION_KEYS,
    CHAT_KEY_SESSION_ID_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SESSION_KEY,
    PENDING_PASSWORD_REHASH_SOURCE_DIGEST_SESSION_KEY,
    POST_AUTH_REDIRECT_SESSION_KEY,
    pop_post_auth_redirect,
    stash_post_auth_redirect,
    stash_post_auth_redirect_target,
)
from hushline.config import PASSWORD_HASH_REHASH_ON_AUTH_ENABLED
from hushline.db import db
from hushline.model import (
    ChatKey,
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    InviteCode,
    NotificationRecipient,
    OrganizationSetting,
    PasswordResetToken,
    User,
)
from hushline.routes.auth import (
    PASSWORD_RESET_CONFIRMATION_MESSAGE,
    PASSWORD_RESET_INVALID_LINK_MESSAGE,
    _apply_pending_password_rehash,
    _find_primary_username,
    _lock_first_user_registration,
    _password_hash_digest,
    _password_reset_ttl,
)
from tests.helpers import (
    get_captcha_from_session_password_reset,
    get_captcha_from_session_register,
)

TOTP_SECRET = "KBOVHCCELV67CYGOQ2QYU5SCNYVAREMH"


def _login_chat_key_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "public_key": '{"kty":"EC","crv":"P-256","x":"login-public-x","y":"login-public-y"}',
        "public_signing_key": (
            '{"kty":"EC","crv":"P-256","x":"login-signing-public-x","y":"login-signing-public-y"}'
        ),
        "encrypted_private_key": (
            '{"algorithm":"AES-GCM","iv":"bG9naW4tbm9uY2Uh",'
            '"ciphertext":"bG9naW4td3JhcHBlZC1wcml2YXRlLWtleQ=="}'
        ),
        "kdf_algorithm": "PBKDF2-SHA-256",
        "kdf_params": {"iterations": 310000, "hash": "SHA-256"},
        "kdf_salt": "bG9naW4tc2FsdC0xMjM0NQ==",
        "wrapping_algorithm": "AES-GCM",
    }
    payload.update(overrides)
    return payload


def _assert_auth_session_cleared(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        for key in AUTH_SESSION_KEYS:
            assert key not in sess


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["session_id"] = user.session_id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = True


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
        assert isinstance(sess[CHAT_KEY_SESSION_ID_SESSION_KEY], str)
        assert sess[CHAT_KEY_SESSION_ID_SESSION_KEY]


def test_login_next_redirects_after_auth(
    client: FlaskClient, user: User, user_password: str
) -> None:
    target = url_for("profile", username=user.primary_username.username, _external=False)

    response = client.get(url_for("login", next=target), follow_redirects=False)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess[POST_AUTH_REDIRECT_SESSION_KEY] == target

    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(target)

    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess


def test_register_next_stashes_post_auth_redirect(client: FlaskClient, user: User) -> None:
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    db.session.commit()
    target = url_for("profile", username=user.primary_username.username, _external=False)

    response = client.get(url_for("register", next=target), follow_redirects=False)

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess[POST_AUTH_REDIRECT_SESSION_KEY] == target


@pytest.mark.parametrize(
    "target",
    [
        r"/\attacker.example/path",
        "/%5Cattacker.example/path",
    ],
)
def test_login_next_rejects_backslash_redirect_target(
    client: FlaskClient, user: User, user_password: str, target: str
) -> None:
    response = client.get(url_for("login", next=target), follow_redirects=False)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess

    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


@pytest.mark.parametrize(
    "target",
    [
        r"/\attacker.example/path",
        "/%5Cattacker.example/path",
    ],
)
def test_register_next_rejects_backslash_redirect_target(
    client: FlaskClient, user: User, target: str
) -> None:
    OrganizationSetting.upsert(OrganizationSetting.REGISTRATION_ENABLED, True)
    db.session.commit()

    response = client.get(url_for("register", next=target), follow_redirects=False)

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess


def test_login_password_step_for_2fa_does_not_revoke_existing_sessions(
    app: Flask, client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = TOTP_SECRET
    db.session.commit()
    original_session_id = user.session_id

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["session_id"] = original_session_id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = True

    with app.test_client() as password_only_client:
        response = password_only_client.post(
            url_for("login"),
            data={"username": user.primary_username.username, "password": user_password},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"] == url_for("verify_2fa_login", _external=False)
    db.session.refresh(user)
    assert user.session_id == original_session_id

    response = client.get(url_for("settings.profile"), follow_redirects=False)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["session_id"] == original_session_id
        assert sess["is_authenticated"] is True


def test_login_with_chat_key_payload_creates_missing_chat_key(
    client: FlaskClient, user: User, user_password: str
) -> None:
    assert user.active_chat_key is None

    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
            "chat_key_payload": json.dumps(_login_chat_key_payload()),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    created_key = db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).one()
    assert created_key.key_version == 1
    assert created_key.disabled_at is None
    assert created_key.public_key == _login_chat_key_payload()["public_key"]
    assert created_key.public_signing_key == _login_chat_key_payload()["public_signing_key"]
    assert created_key.encrypted_private_key == _login_chat_key_payload()["encrypted_private_key"]
    assert created_key.kdf_salt == "bG9naW4tc2FsdC0xMjM0NQ=="


def test_login_ignores_malformed_chat_key_payload(
    client: FlaskClient, user: User, user_password: str
) -> None:
    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
            "chat_key_payload": "{not-json",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).all() == []


def test_login_ignores_invalid_chat_key_payload(
    client: FlaskClient, user: User, user_password: str
) -> None:
    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
            "chat_key_payload": json.dumps(_login_chat_key_payload(private_key="plaintext")),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).all() == []


def test_login_with_chat_key_payload_waits_for_successful_2fa(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = TOTP_SECRET
    db.session.commit()

    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
            "chat_key_payload": json.dumps(_login_chat_key_payload()),
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("verify_2fa_login"))
    assert db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).all() == []
    with client.session_transaction() as sess:
        assert CHAT_KEY_SESSION_ID_SESSION_KEY not in sess

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(TOTP_SECRET).now()},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert isinstance(sess[CHAT_KEY_SESSION_ID_SESSION_KEY], str)
        assert sess[CHAT_KEY_SESSION_ID_SESSION_KEY]
    created_key = db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).one()
    assert created_key.key_version == 1
    assert created_key.disabled_at is None
    assert created_key.public_key == _login_chat_key_payload()["public_key"]
    assert created_key.public_signing_key == _login_chat_key_payload()["public_signing_key"]


def _enable_password_reset_email(user: User) -> None:
    user.enable_email_notifications = True
    user.email = "recipient@example.com"
    db.session.commit()


def test_password_reset_request_is_generic_and_does_not_send_to_notification_recipients(
    client: FlaskClient, user: User, user2: User
) -> None:
    user2.enable_email_notifications = False
    user2.email = "ineligible@example.com"
    _enable_password_reset_email(user)

    response = client.get(url_for("login"))
    assert response.status_code == 200
    assert url_for("request_password_reset") in response.text

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
    notification_recipient_captcha = get_captcha_from_session_password_reset(client)
    notification_recipient_response = client.post(
        url_for("request_password_reset"),
        data={
            "username": user.primary_username.username.upper(),
            "captcha_answer": notification_recipient_captcha,
        },
    )

    assert unknown_response.status_code == 200
    assert ineligible_response.status_code == 200
    assert notification_recipient_response.status_code == 200
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in unknown_response.text
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in ineligible_response.text
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in notification_recipient_response.text
    assert db.session.scalar(db.select(db.func.count()).select_from(PasswordResetToken)) == 0


def test_find_primary_username_returns_none_and_logs_when_query_is_ambiguous(app: Flask) -> None:
    with (
        app.app_context(),
        patch(
            "hushline.routes.auth.db.session.scalars",
            side_effect=MultipleResultsFound("duplicate primary usernames"),
        ),
        patch.object(app.logger, "error") as logger_error,
    ):
        username = _find_primary_username(" ExampleUser ")

    assert username is None
    logger_error.assert_called_once()
    assert logger_error.call_args.args[0] == (
        "Multiple primary usernames matched case-insensitive password reset lookup"
    )
    assert logger_error.call_args.kwargs["extra"]["username_hash"]


def test_password_reset_sets_new_password_and_consumes_token(
    client: FlaskClient, user: User, user_password: str
) -> None:
    original_session_id = user.session_id
    reset_token, raw_token = PasswordResetToken.create_for_user(
        user.id,
        ttl=timedelta(hours=1),
    )
    db.session.add(reset_token)
    db.session.commit()

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


def test_password_reset_locks_active_chat_key_without_server_recovery(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user_id = user.id
    chat_key = ChatKey(
        user_id=user_id,
        key_version=1,
        public_key="public-chat-key",
        encrypted_private_key='{"algorithm":"AES-GCM","iv":"old","ciphertext":"old"}',
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000, "hash": "SHA-256"},
        kdf_salt="old-salt",
        wrapping_algorithm="AES-GCM",
    )
    reset_token, raw_token = PasswordResetToken.create_for_user(
        user_id,
        ttl=timedelta(hours=1),
    )
    db.session.add_all([chat_key, reset_token])
    db.session.commit()

    response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": "ResetPassword123!!"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(user)
    db.session.refresh(chat_key)
    assert ChatKey.active_for_user_id(user.id) is None
    assert user.check_password("ResetPassword123!!")
    assert not user.check_password(user_password)
    assert chat_key.disabled_at is not None
    assert chat_key.recovery_state == "password_reset_locked"
    assert chat_key.encrypted_private_key == (
        '{"algorithm":"AES-GCM","iv":"old","ciphertext":"old"}'
    )
    assert "recovery" not in chat_key.encrypted_private_key
    assert db.session.scalar(db.select(db.func.count()).select_from(ChatKey)) == 1


def test_password_reset_leaves_existing_conversation_history_locked(
    client: FlaskClient, user: User, user2: User
) -> None:
    user_id = user.id
    user2_id = user2.id
    chat_key = ChatKey(
        user_id=user_id,
        key_version=1,
        public_key='{"kty":"EC","crv":"P-256","x":"old-sender","y":"key"}',
        encrypted_private_key='{"algorithm":"AES-GCM","iv":"old","ciphertext":"old"}',
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000, "hash": "SHA-256"},
        kdf_salt="old-salt",
        wrapping_algorithm="AES-GCM",
    )
    recipient_chat_key = ChatKey(
        user_id=user2_id,
        key_version=1,
        public_key='{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}',
        encrypted_private_key='{"algorithm":"AES-GCM","iv":"recipient","ciphertext":"wrapped"}',
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000, "hash": "SHA-256"},
        kdf_salt="recipient-salt",
        wrapping_algorithm="AES-GCM",
    )
    conversation = Conversation()
    sender_participant = ConversationParticipant()
    sender_participant.conversation = conversation
    sender_participant.user_id = user_id
    sender_participant.has_usable_public_key = True
    recipient_participant = ConversationParticipant()
    recipient_participant.conversation = conversation
    recipient_participant.user_id = user2_id
    recipient_participant.has_usable_public_key = True
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = sender_participant
    sender_copy = ConversationMessageCopy()
    sender_copy.recipient_participant = sender_participant
    sender_copy.encrypted_payload = (
        '{"algorithm":"ECDH-P256-AES-GCM","iv":"old-copy","ciphertext":"old-history"}'
    )
    recipient_copy = ConversationMessageCopy()
    recipient_copy.recipient_participant = recipient_participant
    recipient_copy.encrypted_payload = (
        '{"algorithm":"ECDH-P256-AES-GCM","iv":"recipient-copy","ciphertext":"history"}'
    )
    conversation_message.encrypted_copies.extend([sender_copy, recipient_copy])
    reset_token, raw_token = PasswordResetToken.create_for_user(
        user_id,
        ttl=timedelta(hours=1),
    )
    db.session.add_all([chat_key, recipient_chat_key, conversation, reset_token])
    db.session.commit()

    response = client.post(
        url_for("reset_password", token=raw_token),
        data={"password": "ResetPassword123!!"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    db.session.refresh(user)
    db.session.refresh(chat_key)
    assert ChatKey.active_for_user_id(user.id) is None
    assert chat_key.recovery_state == "password_reset_locked"
    assert chat_key.encrypted_private_key == (
        '{"algorithm":"AES-GCM","iv":"old","ciphertext":"old"}'
    )

    _authenticate_as(client, user)
    chat_key_response = client.get(url_for("settings.chat_key"))
    assert chat_key_response.status_code == 200
    assert chat_key_response.get_json() == {"chat_key": None}

    conversation_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert conversation_response.status_code == 200
    assert "Secure chat unavailable" in conversation_response.text
    assert "conversation-chat-password" not in conversation_response.text
    assert "old-sender" not in conversation_response.text
    assert "old-history" in conversation_response.text
    assert chat_key.encrypted_private_key not in conversation_response.text

    reply_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": {}},
    )
    assert reply_response.status_code == 400
    assert reply_response.get_json() == {"error": "Conversation replies are unavailable."}
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_password_reset_request_never_emails_shared_notification_recipients(
    client: FlaskClient, user: User
) -> None:
    user.enable_email_notifications = True
    user.email = "owner@example.com"
    shared_recipient = NotificationRecipient(
        enabled=True,
        position=user.next_notification_recipient_position,
    )
    shared_recipient.email = "shared-alerts@example.com"
    user.notification_recipients.append(shared_recipient)
    db.session.commit()

    captcha_answer = get_captcha_from_session_password_reset(client)
    response = client.post(
        url_for("request_password_reset"),
        data={"username": user.primary_username.username, "captcha_answer": captcha_answer},
    )

    assert response.status_code == 200
    assert PASSWORD_RESET_CONFIRMATION_MESSAGE in response.text
    assert db.session.scalar(db.select(db.func.count()).select_from(PasswordResetToken)) == 0


def test_password_reset_get_renders_form_for_active_token(client: FlaskClient, user: User) -> None:
    reset_token, raw_token = PasswordResetToken.create_for_user(
        user.id,
        ttl=timedelta(hours=1),
    )
    db.session.add(reset_token)
    db.session.commit()

    response = client.get(url_for("reset_password", token=raw_token))

    assert response.status_code == 200
    assert "Reset Password" in response.text
    assert 'name="password"' in response.text


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


def test_password_reset_ttl_uses_configured_minutes(app: Flask) -> None:
    app.config["PASSWORD_RESET_TOKEN_TTL_MINUTES"] = 7

    with app.app_context():
        assert _password_reset_ttl() == timedelta(minutes=7)


def test_password_reset_request_rate_limits_repeated_identifier(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["PASSWORD_RESET_RATE_LIMIT_IDENTIFIER_MAX"] = 1
    app.config["PASSWORD_RESET_RATE_LIMIT_IP_MAX"] = 100
    _enable_password_reset_email(user)

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
    assert db.session.scalar(db.select(db.func.count()).select_from(PasswordResetToken)) == 0


def test_password_reset_request_rejects_incorrect_captcha(client: FlaskClient, user: User) -> None:
    _enable_password_reset_email(user)
    response = client.get(url_for("request_password_reset"))

    assert response.status_code == 200
    assert "Solve the math problem to request reset instructions." in response.text

    response = client.post(
        url_for("request_password_reset"),
        data={"username": user.primary_username.username, "captcha_answer": "9999"},
    )

    assert response.status_code == 200
    assert "⛔️ Incorrect CAPTCHA. Please try again." in response.text
    assert db.session.scalar(db.select(db.func.count()).select_from(PasswordResetToken)) == 0


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


def test_stash_post_auth_redirect_target_rejects_unsafe_target(app: Flask) -> None:
    with app.test_request_context("/login", method="GET"):
        session["sentinel"] = "keep"
        session[POST_AUTH_REDIRECT_SESSION_KEY] = "/already-set"

        stash_post_auth_redirect_target("//example.com/phish")
        stash_post_auth_redirect_target("https://example.com/phish")
        stash_post_auth_redirect_target(r"/\example.com/phish")
        stash_post_auth_redirect_target("/%5Cexample.com/phish")
        stash_post_auth_redirect_target(None)

        assert session["sentinel"] == "keep"
        assert session[POST_AUTH_REDIRECT_SESSION_KEY] == "/already-set"


@pytest.mark.parametrize(
    "target",
    [
        "//example.com/phish",
        "https://example.com/phish",
        r"/\example.com/phish",
        "/%5Cexample.com/phish",
        "/safe-path\r\nLocation: https://example.com/phish",
    ],
)
def test_pop_post_auth_redirect_rejects_unsafe_target(app: Flask, target: str) -> None:
    with app.test_request_context("/login", method="POST"):
        session[POST_AUTH_REDIRECT_SESSION_KEY] = target

        assert pop_post_auth_redirect() == url_for("inbox")
        assert POST_AUTH_REDIRECT_SESSION_KEY not in session


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
    original_session_id = user.session_id

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

    db.session.refresh(user)
    assert user.session_id != original_session_id
    with client.session_transaction() as sess:
        assert POST_AUTH_REDIRECT_SESSION_KEY not in sess
        assert sess["session_id"] == user.session_id


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

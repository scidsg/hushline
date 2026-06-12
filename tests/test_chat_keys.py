import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import ChatKey, User

ROOT = Path(__file__).resolve().parents[1]


def _chat_key_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "public_key": '{"kty":"EC","crv":"P-256","x":"public-x","y":"public-y"}',
        "encrypted_private_key": (
            '{"algorithm":"AES-GCM","iv":"nonce","ciphertext":"wrapped-private-key"}'
        ),
        "kdf_algorithm": "PBKDF2-SHA-256",
        "kdf_params": {"iterations": 310000, "hash": "SHA-256"},
        "kdf_salt": "salt",
        "wrapping_algorithm": "AES-GCM",
    }
    payload.update(overrides)
    return payload


def _chat_key_columns() -> set[str]:
    return {column.name for column in db.metadata.tables["chat_keys"].columns}


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_encryption_shows_chat_key_provisioner(client: FlaskClient) -> None:
    response = client.get(url_for("settings.encryption"))

    assert response.status_code == 200
    assert 'id="chat-key-provision-form"' in response.text
    assert f'data-chat-key-url="{url_for("settings.chat_key")}"' in response.text
    assert 'id="chat-key-password"' in response.text
    assert 'autocomplete="current-password"' in response.text
    assert 'name="chat_key_password"' not in response.text
    assert url_for("static", filename="js/chat-key-lifecycle.js") in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_encryption_shows_locked_chat_key_state(client: FlaskClient, user: User) -> None:
    chat_key = ChatKey(
        user=user,
        key_version=1,
        public_key="public-chat-key",
        encrypted_private_key="wrapped-private-chat-key",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="salt",
        wrapping_algorithm="AES-GCM",
        disabled_at=datetime.now(UTC),
        recovery_state="password_reset_locked",
    )
    db.session.add(chat_key)
    db.session.commit()

    response = client.get(url_for("settings.encryption"))

    assert response.status_code == 200
    assert "Chat history encrypted to key version 1 is locked" in response.text
    assert "Hush Line cannot recover the private key." in response.text
    assert 'id="chat-key-provision-form"' in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_authenticated_user_can_provision_chat_key(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("settings.chat_key"), json=_chat_key_payload())

    assert response.status_code == 201
    created_key = db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).one()
    assert created_key.key_version == 1
    assert created_key.public_key == _chat_key_payload()["public_key"]
    assert created_key.encrypted_private_key == _chat_key_payload()["encrypted_private_key"]
    assert created_key.kdf_algorithm == "PBKDF2-SHA-256"
    assert created_key.kdf_params == {"iterations": 310000, "hash": "SHA-256"}
    assert created_key.kdf_salt == "salt"
    assert created_key.wrapping_algorithm == "AES-GCM"
    assert created_key.disabled_at is None

    response_payload = response.get_json()
    assert response_payload is not None
    assert response_payload["chat_key"]["public_key"] == created_key.public_key
    assert response_payload["chat_key"]["encrypted_private_key"] == (
        created_key.encrypted_private_key
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_authenticated_user_can_provision_new_chat_key_after_locked_key(
    client: FlaskClient, user: User
) -> None:
    locked_key = ChatKey(
        user=user,
        key_version=1,
        public_key="locked-public",
        encrypted_private_key="locked-wrapped-private",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="locked-salt",
        wrapping_algorithm="AES-GCM",
        disabled_at=datetime.now(UTC),
        recovery_state="password_reset_locked",
    )
    db.session.add(locked_key)
    db.session.commit()

    response = client.post(url_for("settings.chat_key"), json=_chat_key_payload())

    assert response.status_code == 201
    keys = db.session.scalars(
        db.select(ChatKey).filter_by(user_id=user.id).order_by(ChatKey.key_version.asc())
    ).all()
    assert [key.key_version for key in keys] == [1, 2]
    assert keys[0].recovery_state == "password_reset_locked"
    assert keys[1].disabled_at is None
    assert keys[1].public_key == _chat_key_payload()["public_key"]


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_payload_rejects_plaintext_private_key_material(
    client: FlaskClient,
) -> None:
    response = client.post(
        url_for("settings.chat_key"),
        json=_chat_key_payload(private_key="plain-private-key"),
    )

    assert response.status_code == 400
    assert "Plaintext chat key material is not accepted." in response.text
    assert db.session.scalars(db.select(ChatKey)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_cannot_be_provisioned_for_another_user(client: FlaskClient, user2: User) -> None:
    response = client.post(
        url_for("settings.chat_key"),
        json=_chat_key_payload(user_id=user2.id),
    )

    assert response.status_code == 403
    assert db.session.scalars(db.select(ChatKey)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_post_requires_csrf_when_enabled(app: Flask, client: FlaskClient) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(url_for("settings.chat_key"), json=_chat_key_payload())
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert db.session.scalars(db.select(ChatKey)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_post_accepts_csrf_header_when_enabled(app: Flask, client: FlaskClient) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        settings_response = client.get(url_for("settings.encryption"))
        token_match = re.search(r'data-csrf-token="([^"]+)"', settings_response.text)
        assert token_match is not None

        response = client.post(
            url_for("settings.chat_key"),
            json=_chat_key_payload(),
            headers={"X-CSRFToken": token_match.group(1)},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 201


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_rotation_versions_new_key_and_disables_old_key(
    client: FlaskClient, user: User
) -> None:
    first_response = client.post(url_for("settings.chat_key"), json=_chat_key_payload())
    second_response = client.post(
        url_for("settings.chat_key"),
        json=_chat_key_payload(public_key='{"kty":"EC","x":"rotated"}'),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    keys = db.session.scalars(
        db.select(ChatKey).filter_by(user_id=user.id).order_by(ChatKey.key_version.asc())
    ).all()
    assert [key.key_version for key in keys] == [1, 2]
    assert keys[0].disabled_at is not None
    assert keys[0].recovery_state == "rotated"
    assert keys[1].disabled_at is None
    assert keys[1].rotated_at is not None
    assert user.chat_public_key == '{"kty":"EC","x":"rotated"}'


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_get_returns_only_authenticated_users_key(
    client: FlaskClient, user: User, user2: User
) -> None:
    owned_key = ChatKey(
        user=user,
        key_version=1,
        public_key="owned-public",
        encrypted_private_key="owned-wrapped-private",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="salt",
        wrapping_algorithm="AES-GCM",
    )
    other_key = ChatKey(
        user=user2,
        key_version=1,
        public_key="other-public",
        encrypted_private_key="other-wrapped-private",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="salt",
        wrapping_algorithm="AES-GCM",
    )
    db.session.add_all([owned_key, other_key])
    db.session.commit()

    response = client.get(url_for("settings.chat_key"))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["chat_key"]["public_key"] == "owned-public"
    assert "other-public" not in response.text


def test_chat_key_schema_has_no_plaintext_private_key_columns(app: Flask) -> None:
    assert _chat_key_columns().isdisjoint(
        {
            "private_key",
            "plaintext_private_key",
            "derived_key",
            "unlock_key",
            "decrypted_message_text",
        }
    )


def test_chat_key_lifecycle_js_exposes_unlock_rewrap_and_cleanup() -> None:
    lifecycle_js = (ROOT / "hushline/static/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    assert "window.HushLineChatKeys" in lifecycle_js
    assert "unlockFromPassword" in lifecycle_js
    assert "rewrapForPasswordChange" in lifecycle_js
    assert "clearChatKeyMaterial" in lifecycle_js
    assert "document.body?.dataset.authenticated" in lifecycle_js
    assert "Chat key unlock failed." in lifecycle_js


@pytest.mark.usefixtures("_pgp_user")
def test_profile_exposes_public_chat_key_only(client: FlaskClient, user: User) -> None:
    chat_key = ChatKey(
        user=user,
        key_version=1,
        public_key="public-chat-key",
        encrypted_private_key="wrapped-private-chat-key",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="salt",
        wrapping_algorithm="AES-GCM",
    )
    db.session.add(chat_key)
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))

    assert response.status_code == 200
    assert 'id="recipientChatPublicKey"' in response.text
    assert 'id="senderChatPublicKey"' in response.text
    assert "public-chat-key" in response.text
    assert "wrapped-private-chat-key" not in response.text

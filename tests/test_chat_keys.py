import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.chat_key_lifecycle import (
    CHAT_KEY_METADATA_MAX_LENGTH,
    CHAT_KEY_RECOVERY_STATE_MAX_LENGTH,
    payload_contains_forbidden_secret_field,
    validate_chat_key_payload,
)
from hushline.db import db
from hushline.model import ChatKey, User

ROOT = Path(__file__).resolve().parents[1]


def _chat_key_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "public_key": '{"kty":"EC","crv":"P-256","x":"public-x","y":"public-y"}',
        "public_signing_key": (
            '{"kty":"EC","crv":"P-256","x":"signing-public-x","y":"signing-public-y"}'
        ),
        "encrypted_private_key": (
            '{"algorithm":"AES-GCM","iv":"bm9uY2UtMTIzNDU2",'
            '"ciphertext":"d3JhcHBlZC1wcml2YXRlLWtleQ=="}'
        ),
        "kdf_algorithm": "PBKDF2-SHA-256",
        "kdf_params": {"iterations": 310000, "hash": "SHA-256"},
        "kdf_salt": "c2FsdC1zYWx0LXNhbHQtIQ==",
        "wrapping_algorithm": "AES-GCM",
    }
    payload.update(overrides)
    return payload


def _chat_key_columns() -> set[str]:
    return {column.name for column in db.metadata.tables["chat_keys"].columns}


def test_forbidden_secret_field_detection_recurses_through_nested_lists() -> None:
    assert payload_contains_forbidden_secret_field(
        {"safe": [{"nested": [{"plaintext-private-key": "secret"}]}]}
    )
    assert not payload_contains_forbidden_secret_field({"safe": [{"nested": ["metadata"]}]})


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ([], "Expected a JSON object."),
        ({"public_key": "not-json"}, "public_key must be a P-256 ECDH public JWK."),
        ({"public_key": "[]"}, "public_key must be a P-256 ECDH public JWK."),
        (
            {"public_key": '{"kty":"OKP","crv":"Ed25519","x":"public-x","y":"public-y"}'},
            "public_key must be a P-256 ECDH public JWK.",
        ),
        (
            {"public_key": '{"kty":"EC","crv":"P-256","x":"public-x"}'},
            "public_key must be a P-256 ECDH public JWK.",
        ),
        (
            {
                "public_key": (
                    '{"kty":"EC","crv":"P-256","x":"public-x","y":"public-y",' '"key_ops":[1]}'
                )
            },
            "public_key must be a P-256 ECDH public JWK.",
        ),
        (
            {
                "public_key": (
                    '{"kty":"EC","crv":"P-256","x":"public-x","y":"public-y",'
                    '"key_ops":["encrypt"]}'
                )
            },
            "public_key must be a P-256 ECDH public JWK.",
        ),
        (
            {
                "public_signing_key": (
                    '{"kty":"EC","crv":"P-256","x":"signing-public-x",'
                    '"y":"signing-public-y","key_ops":["sign"]}'
                )
            },
            "public_signing_key must be a P-256 ECDSA public JWK.",
        ),
        ({"public_key": ""}, "public_key is required."),
        ({"public_signing_key": ""}, "public_signing_key is required."),
        ({"encrypted_private_key": ""}, "encrypted_private_key is required."),
        ({"kdf_algorithm": ""}, "kdf_algorithm is required."),
        ({"kdf_salt": ""}, "kdf_salt is required."),
        ({"kdf_params": {}}, "kdf_params must be a non-empty object."),
        (
            {"kdf_params": {"iterations": True, "hash": "SHA-256"}},
            "kdf_params.iterations must be an integer.",
        ),
        (
            {"kdf_params": {"iterations": 310000, "hash": "SHA-256", "bad": object()}},
            "kdf_params must be JSON serializable.",
        ),
        (
            {
                "kdf_params": {
                    "iterations": 310000,
                    "hash": "SHA-256",
                    "metadata": "x" * CHAT_KEY_METADATA_MAX_LENGTH,
                }
            },
            "kdf_params is too large.",
        ),
        (
            {"recovery_state": "x" * (CHAT_KEY_RECOVERY_STATE_MAX_LENGTH + 1)},
            "recovery_state is too large.",
        ),
        (
            {"encrypted_private_key": "[]"},
            "encrypted_private_key must be a JSON object.",
        ),
    ],
)
def test_validate_chat_key_payload_rejects_malformed_edges(
    payload: object, expected_error: str
) -> None:
    if isinstance(payload, dict):
        submitted_payload_dict = _chat_key_payload()
        submitted_payload_dict.update(payload)
        submitted_payload: object = submitted_payload_dict
    else:
        submitted_payload = payload

    cleaned_payload, error = validate_chat_key_payload(submitted_payload, current_user_id=1)

    assert cleaned_payload == {}
    assert error == expected_error


def test_validate_chat_key_payload_accepts_nested_kdf_fields() -> None:
    payload = _chat_key_payload()
    payload.pop("kdf_algorithm")
    payload.pop("kdf_salt")
    payload.pop("kdf_params")
    payload["kdf"] = {
        "algorithm": "PBKDF2-SHA-256",
        "salt": "c2FsdC1zYWx0LXNhbHQtIQ==",
        "params": {"iterations": 310000, "hash": "SHA-256"},
    }

    cleaned_payload, error = validate_chat_key_payload(payload, current_user_id=1)

    assert error == ""
    assert cleaned_payload["kdf_algorithm"] == "PBKDF2-SHA-256"
    assert cleaned_payload["kdf_salt"] == "c2FsdC1zYWx0LXNhbHQtIQ=="
    assert cleaned_payload["kdf_params"] == {"iterations": 310000, "hash": "SHA-256"}


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_encryption_explains_automatic_chat_key_creation(client: FlaskClient) -> None:
    response = client.get(url_for("settings.encryption"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    heading = soup.find("h3", string="Encryption")
    assert heading is not None
    intro = heading.find_next_sibling("p")
    assert intro is not None
    assert "meta" not in (intro.get("class") or [])
    assert "This public key is used on your tip line." in intro.get_text()
    assert "Your chat key encrypts and decrypts two-way conversation replies" in response.text
    assert "Hush Line stores only the public key and a password-encrypted copy" in response.text
    assert "creates and unlocks this key automatically when you log in" in response.text
    assert "Your chat key will be created automatically the next time you log in." in response.text
    assert 'id="chat-key-provision-form"' not in response.text
    assert 'data-chat-key-action="create"' not in response.text
    assert 'id="chat-key-password"' not in response.text
    assert "Create Chat Key" not in response.text
    assert 'name="chat_key_password"' not in response.text
    assert url_for("static", filename="js/chat-key-lifecycle.js") in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_encryption_shows_active_chat_key_rotation_warning(
    client: FlaskClient, user: User
) -> None:
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

    response = client.get(url_for("settings.encryption"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", id="chat-key-provision-form")
    assert form is not None
    assert form.get("data-chat-key-action") == "rotate"
    assert form.get("data-chat-key-url") == url_for("settings.chat_key")
    confirm_message = (
        "Rotating your chat key will make old conversations encrypted to earlier chat keys "
        "unreadable. Continue?"
    )
    assert form.get("data-confirm-message") == confirm_message
    assert form.find(id="chat-key-password") is not None
    button = form.find("button", string="Rotate Chat Key")
    assert button is not None
    assert "btn-danger" in (button.get("class") or [])
    assert "Chat key version 1 is active." in response.text
    assert "Old conversations encrypted to earlier chat keys will" in response.text
    assert "be unreadable after rotation." in response.text


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
    assert "Your chat key will be created automatically the next time you log in." in response.text
    assert 'id="chat-key-provision-form"' not in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_authenticated_user_can_provision_chat_key(client: FlaskClient, user: User) -> None:
    response = client.post(url_for("settings.chat_key"), json=_chat_key_payload())

    assert response.status_code == 201
    created_key = db.session.scalars(db.select(ChatKey).filter_by(user_id=user.id)).one()
    assert created_key.key_version == 1
    assert created_key.public_key == _chat_key_payload()["public_key"]
    assert created_key.public_signing_key == _chat_key_payload()["public_signing_key"]
    assert created_key.encrypted_private_key == _chat_key_payload()["encrypted_private_key"]
    assert created_key.kdf_algorithm == "PBKDF2-SHA-256"
    assert created_key.kdf_params == {"iterations": 310000, "hash": "SHA-256"}
    assert created_key.kdf_salt == "c2FsdC1zYWx0LXNhbHQtIQ=="
    assert created_key.wrapping_algorithm == "AES-GCM"
    assert created_key.disabled_at is None

    response_payload = response.get_json()
    assert response_payload is not None
    assert response_payload["chat_key"]["public_key"] == created_key.public_key
    assert response_payload["chat_key"]["public_signing_key"] == created_key.public_signing_key
    assert response_payload["chat_key"]["public_key_fingerprint"]
    assert response_payload["chat_key"]["public_signing_key_fingerprint"]
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
def test_chat_key_post_requires_signing_public_key(client: FlaskClient) -> None:
    payload = _chat_key_payload()
    payload.pop("public_signing_key")

    response = client.post(url_for("settings.chat_key"), json=payload)

    assert response.status_code == 400
    assert "public_signing_key is required." in response.text
    assert db.session.scalars(db.select(ChatKey)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        (
            {"kdf_algorithm": "PBKDF2-SHA-1"},
            "kdf_algorithm must be PBKDF2-SHA-256.",
        ),
        (
            {"kdf_params": {"iterations": 309999, "hash": "SHA-256"}},
            "kdf_params.iterations is below the minimum.",
        ),
        (
            {"kdf_params": {"iterations": 310000, "hash": "SHA-1"}},
            "kdf_params.hash must be SHA-256.",
        ),
        (
            {"kdf_salt": "not base64"},
            "kdf_salt must be non-empty base64.",
        ),
        (
            {"kdf_salt": "QUE="},
            "kdf_salt must be 16 bytes.",
        ),
        (
            {"wrapping_algorithm": "AES-CBC"},
            "wrapping_algorithm must be AES-GCM.",
        ),
        (
            {"encrypted_private_key": "x" * 200_001},
            "Chat key payload is too large.",
        ),
        (
            {"encrypted_private_key": "wrapped-private-key"},
            "encrypted_private_key must be a JSON object.",
        ),
        (
            {
                "encrypted_private_key": (
                    '{"algorithm":"AES-GCM","iv":"bm9uY2UtMTIzNDU2",'
                    '"ciphertext":"d3JhcHBlZC1wcml2YXRlLWtleQ==",'
                    '"private_key":"plaintext-private-key"}'
                )
            },
            "encrypted_private_key contains unsupported fields.",
        ),
        (
            {
                "encrypted_private_key": (
                    '{"algorithm":"AES-CBC","iv":"bm9uY2UtMTIzNDU2",'
                    '"ciphertext":"d3JhcHBlZC1wcml2YXRlLWtleQ=="}'
                )
            },
            "encrypted_private_key algorithm must be AES-GCM.",
        ),
        (
            {
                "encrypted_private_key": (
                    '{"algorithm":"AES-GCM","iv":"not base64",'
                    '"ciphertext":"d3JhcHBlZC1wcml2YXRlLWtleQ=="}'
                )
            },
            "encrypted_private_key iv must be non-empty base64.",
        ),
        (
            {
                "encrypted_private_key": (
                    '{"algorithm":"AES-GCM","iv":"QUE=",'
                    '"ciphertext":"d3JhcHBlZC1wcml2YXRlLWtleQ=="}'
                )
            },
            "encrypted_private_key iv must be 12 bytes.",
        ),
        (
            {
                "encrypted_private_key": (
                    '{"algorithm":"AES-GCM","iv":"bm9uY2UtMTIzNDU2","ciphertext":""}'
                )
            },
            "encrypted_private_key ciphertext must be non-empty base64.",
        ),
    ],
)
def test_chat_key_payload_rejects_weak_or_malformed_wrapping_policy(
    client: FlaskClient,
    overrides: dict[str, object],
    expected_error: str,
) -> None:
    response = client.post(
        url_for("settings.chat_key"),
        json=_chat_key_payload(**overrides),
    )

    assert response.status_code == 400
    assert expected_error in response.text
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
        token_match = re.search(
            r'<meta name="csrf-token" content="([^"]+)"', settings_response.text
        )
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
        json=_chat_key_payload(public_key='{"kty":"EC","crv":"P-256","x":"rotated","y":"key"}'),
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
    assert user.chat_public_key == '{"kty":"EC","crv":"P-256","x":"rotated","y":"key"}'


@pytest.mark.usefixtures("_authenticated_user")
def test_chat_key_signing_upgrade_preserves_chat_public_key(
    client: FlaskClient, user: User
) -> None:
    public_key = '{"kty":"EC","crv":"P-256","x":"legacy","y":"key"}'
    legacy_key = ChatKey(
        user=user,
        key_version=1,
        public_key=public_key,
        encrypted_private_key="legacy-wrapped-private-chat-key",
        kdf_algorithm="PBKDF2-SHA-256",
        kdf_params={"iterations": 310000},
        kdf_salt="salt",
        wrapping_algorithm="AES-GCM",
    )
    db.session.add(legacy_key)
    db.session.commit()

    response = client.post(
        url_for("settings.chat_key"),
        json=_chat_key_payload(public_key=public_key),
    )

    assert response.status_code == 201
    keys = db.session.scalars(
        db.select(ChatKey).filter_by(user_id=user.id).order_by(ChatKey.key_version.asc())
    ).all()
    assert [key.key_version for key in keys] == [1, 2]
    assert keys[0].disabled_at is not None
    assert keys[0].recovery_state == "rotated"
    assert keys[1].disabled_at is None
    assert keys[1].public_key == public_key
    assert keys[1].public_signing_key == _chat_key_payload()["public_signing_key"]
    assert user.chat_public_key == public_key
    assert user.chat_public_signing_key == _chat_key_payload()["public_signing_key"]


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
    lifecycle_source = (ROOT / "assets/js/chat-key-lifecycle.js").read_text(encoding="utf-8")

    assert "window.HushLineChatKeys" in lifecycle_js
    assert "unlockFromPassword" in lifecycle_source
    assert "ensureChatKeyUnlockedAfterAuth" in lifecycle_source
    assert "provisionChatKey" in lifecycle_source
    assert "createChatKeyPayload" in lifecycle_source
    assert "pendingLoginPassword" in lifecycle_source
    assert "form[action$='/verify-2fa-login']" in lifecycle_source
    assert "rewrapForPasswordChange" in lifecycle_source
    assert "clearChatKeyMaterial" in lifecycle_source
    assert "signChatEnvelope" in lifecycle_source
    assert "verifyChatEnvelope" in lifecycle_source
    assert "additionalData" in lifecycle_source
    assert "restoreConversationFromSession" in lifecycle_source
    assert "restoreUnlockedChatKeyFromOtherTab" in lifecycle_source
    assert "BroadcastChannel" in lifecycle_source
    assert "hushline:chat-private-jwk" in lifecycle_js
    assert "hushline:chat-private-jwk:browser-session" in lifecycle_js
    assert "localStorage.setItem" not in lifecycle_js
    assert "localStorage.getItem" not in lifecycle_js
    assert "sendConversationPresence" in lifecycle_source
    assert 'document.visibilityState === "visible"' in lifecycle_source
    assert "document.body?.dataset.authenticated" in lifecycle_source
    assert "Log out and log back in to unlock chat" not in lifecycle_js


def test_settings_chat_key_rotation_uses_signing_capable_provisioner() -> None:
    settings_js = (ROOT / "assets/js/settings.js").read_text(encoding="utf-8")

    assert "HushLineChatKeys?.provisionChatKey" in settings_js
    assert "HushLineChatKeys.provisionChatKey" in settings_js
    assert "This browser cannot create a chat key." not in settings_js
    assert "bytesToBase64" not in settings_js


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

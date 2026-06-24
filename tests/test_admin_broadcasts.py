import json
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import ChatKey, Message, User
from hushline.settings.broadcast import _send_broadcast_notification_emails

ARMORED_BROADCAST = (
    "-----BEGIN PGP MESSAGE-----\n" "\n" "encrypted admin message\n" "-----END PGP MESSAGE-----"
)


def _enable_notification_email(user: User, email: str) -> None:
    user.enable_email_notifications = True
    recipient = user.ensure_primary_notification_recipient()
    recipient.enabled = True
    recipient.email = email


def _add_chat_key(user: User) -> None:
    db.session.add(
        ChatKey(
            user_id=user.id,
            key_version=1,
            public_key="public-chat-key",
            public_signing_key="public-signing-key",
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000, "hash": "SHA-256"},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_broadcasts_requires_admin(client: FlaskClient) -> None:
    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 403


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_lists_default_audience_counts(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    _add_chat_key(user2)
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    summary_text = " ".join(
        summary.get_text(" ", strip=True) for summary in soup.select(".broadcast-summary .metric")
    )
    assert "Audience Users 1" in summary_text
    assert "Encrypted Submissions 1" in summary_text
    assert "Notification Emails 1" in summary_text
    nav = soup.select_one("nav.settings-tabs")
    assert nav is not None
    assert nav.find("a", href=url_for("settings.broadcasts")) is not None
    status = soup.select_one("#broadcast_status[role='status'][aria-live='polite']")
    assert status is not None
    assert soup.find("select", {"name": "audience"}) is None
    assert soup.find("input", {"name": "subject"}) is None
    assert soup.find("textarea", {"name": "body"}) is None


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_uses_one_e2ee_targeting_behavior(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    user2.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _add_chat_key(user2)
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    summary_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    assert "Audience Users 2" in summary_text
    assert "Encrypted Submissions 2" in summary_text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_includes_recipient_key_only_users(
    client: FlaskClient,
    user: User,
) -> None:
    recipient = user.ensure_primary_notification_recipient()
    recipient.enabled = True
    recipient.email = "primary@example.com"
    recipient.pgp_key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nrecipient\n-----END PGP PUBLIC KEY BLOCK-----"
    )
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    summary_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    assert "Audience Users 1" in summary_text
    assert "Encrypted Submissions 1" in summary_text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_excludes_suspended_users(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    user.is_suspended = True
    user2.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    summary_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    assert "Audience Users 1" in summary_text
    assert "Encrypted Submissions 1" in summary_text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_excludes_users_without_enabled_message_fields(
    client: FlaskClient,
    user: User,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    user.primary_username.create_default_field_defs()
    for field in user.primary_username.message_fields:
        field.enabled = False
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    summary_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    assert "Audience Users 1" in summary_text
    assert "Encrypted Submissions 0" in summary_text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_send_requires_confirmation(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert "Confirm before submitting these encrypted messages." in response.text
    send_email.assert_not_called()
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_rejects_missing_encrypted_payloads(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": "",
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert "No recipient messages could be encrypted." in response.text
    send_email.assert_not_called()
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_rejects_conflicting_encryption_failures(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "encryption_failures": json.dumps([user.id]),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert "Encrypted payloads conflict with reported encryption failures." in response.text
    send_email.assert_not_called()
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_submit_encrypted_inbox_messages_for_pgp_targets(
    client: FlaskClient,
    user: User,
    user2: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    _add_chat_key(user2)
    db.session.commit()
    send_notifications = MagicMock()
    monkeypatch.setattr(
        "hushline.settings.broadcast._send_broadcast_notification_emails",
        send_notifications,
    )

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 302
    messages = db.session.scalars(db.select(Message).order_by(Message.id)).all()
    assert len(messages) == 1
    assert messages[0].username_id == user.primary_username.id
    assert messages[0].field_values[0].encrypted is True
    assert messages[0].field_values[0].value == ARMORED_BROADCAST
    send_notifications.assert_called_once_with((user.id,))


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_submit_encrypted_chunk(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_notifications = MagicMock()
    monkeypatch.setattr(
        "hushline.settings.broadcast._send_broadcast_notification_emails",
        send_notifications,
    )

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "broadcast_chunk": "1",
            "broadcast_completed_user_ids": json.dumps([user.id]),
            "broadcast_expected_user_ids": json.dumps([user.id]),
            "broadcast_final_chunk": "1",
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"submitted_count": 1, "skipped_count": 0}
    messages = db.session.scalars(db.select(Message).order_by(Message.id)).all()
    assert len(messages) == 1
    assert messages[0].username_id == user.primary_username.id
    assert messages[0].field_values[0].encrypted is True
    assert messages[0].field_values[0].value == ARMORED_BROADCAST
    send_notifications.assert_called_once_with((user.id,))


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_chunk_accepts_failure_only_batch(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_notifications = MagicMock()
    monkeypatch.setattr(
        "hushline.settings.broadcast._send_broadcast_notification_emails",
        send_notifications,
    )

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "broadcast_chunk": "1",
            "broadcast_completed_user_ids": json.dumps([user.id]),
            "broadcast_expected_user_ids": json.dumps([user.id]),
            "broadcast_final_chunk": "1",
            "encrypted_payloads": json.dumps({}),
            "encryption_failures": json.dumps([user.id]),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {"submitted_count": 0, "skipped_count": 1}
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0
    send_notifications.assert_not_called()


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_chunk_rejects_unknown_recipients(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "broadcast_chunk": "1",
            "broadcast_completed_user_ids": json.dumps([user.id + 1000]),
            "broadcast_expected_user_ids": json.dumps([user.id]),
            "broadcast_final_chunk": "1",
            "encrypted_payloads": json.dumps({str(user.id + 1000): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Encrypted payloads include unknown recipients."}
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0
    send_email.assert_not_called()


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_final_chunk_rejects_incomplete_completion(
    client: FlaskClient,
    user: User,
    user2: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    user2.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "broadcast_chunk": "1",
            "broadcast_completed_user_ids": json.dumps([user.id]),
            "broadcast_expected_user_ids": json.dumps([user.id, user2.id]),
            "broadcast_final_chunk": "1",
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Broadcast batches are incomplete. Refresh and try again."
    }
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0
    send_email.assert_not_called()


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_chunk_rejects_stale_expected_audience(
    client: FlaskClient,
    user: User,
    user2: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    user2.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "broadcast_chunk": "1",
            "broadcast_completed_user_ids": json.dumps([user.id]),
            "broadcast_expected_user_ids": json.dumps([user.id]),
            "broadcast_final_chunk": "1",
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Broadcast audience changed. Refresh and try again."}
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0
    send_email.assert_not_called()


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_submits_successes_when_some_recipients_fail_browser_encryption(
    client: FlaskClient,
    user: User,
    user2: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user, "primary@example.com")
    user2.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    _enable_notification_email(user2, "secondary@example.com")
    db.session.commit()
    send_notifications = MagicMock()
    monkeypatch.setattr(
        "hushline.settings.broadcast._send_broadcast_notification_emails",
        send_notifications,
    )

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "encryption_failures": json.dumps([user2.id]),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Encrypted messages submitted to 1 users. Skipped 1 users" in response.text
    messages = db.session.scalars(db.select(Message).order_by(Message.id)).all()
    assert len(messages) == 1
    assert messages[0].username_id == user.primary_username.id
    assert messages[0].field_values[0].encrypted is True
    assert messages[0].field_values[0].value == ARMORED_BROADCAST
    send_notifications.assert_called_once_with((user.id,))


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_submit_to_recipient_key_only_users(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipient = user.ensure_primary_notification_recipient()
    recipient.enabled = True
    recipient.email = "primary@example.com"
    recipient.pgp_key = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nrecipient\n-----END PGP PUBLIC KEY BLOCK-----"
    )
    db.session.commit()
    send_notifications = MagicMock()
    monkeypatch.setattr(
        "hushline.settings.broadcast._send_broadcast_notification_emails",
        send_notifications,
    )

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 302
    messages = db.session.scalars(db.select(Message).order_by(Message.id)).all()
    assert len(messages) == 1
    assert messages[0].username_id == user.primary_username.id
    assert messages[0].field_values[0].encrypted is True
    assert messages[0].field_values[0].value == ARMORED_BROADCAST
    send_notifications.assert_called_once_with((user.id,))


def test_send_broadcast_notification_emails_sends_generic_email(
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_notification_email(user, "primary@example.com")
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    _send_broadcast_notification_emails((user.id,))

    send_email.assert_called_once_with(
        user, "You have a new Hush Line message! Please log in to read it."
    )


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_excludes_chat_key_only_users_until_chat_broadcasts_exist(
    client: FlaskClient,
    user: User,
) -> None:
    _add_chat_key(user)
    db.session.commit()

    response = client.get(url_for("settings.broadcasts"))

    assert response.status_code == 200
    summary_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    assert "Audience Users 0" in summary_text
    assert "Encrypted Submissions 0" in summary_text
    assert "Chat Key Only" not in summary_text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_broadcasts_send_rejects_disabled_message_fields(
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.pgp_key = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----"
    user.primary_username.create_default_field_defs()
    for field in user.primary_username.message_fields:
        field.enabled = False
    db.session.commit()
    send_email = MagicMock()
    monkeypatch.setattr("hushline.settings.broadcast.do_send_email", send_email)

    response = client.post(
        url_for("settings.broadcasts"),
        data={
            "encrypted_payloads": json.dumps({str(user.id): ARMORED_BROADCAST}),
            "confirm_send": "y",
            "send_broadcast": "Send Broadcast",
        },
    )

    assert response.status_code == 400
    assert "No eligible encrypted message recipients match this audience." in response.text
    send_email.assert_not_called()
    assert db.session.scalar(db.select(db.func.count(Message.id))) == 0

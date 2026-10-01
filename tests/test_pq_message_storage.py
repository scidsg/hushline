import base64
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.auth import CHAT_KEY_SESSION_ID_SESSION_KEY
from hushline.chat_key_lifecycle import (
    PQ_CHAT_ARCHIVE_SUITE,
    PQ_CHAT_PROTOCOL,
    PQ_CHAT_SIGNATURE_DOMAIN,
    PQ_CHAT_TRANSPORT_SUITE,
    PQ_CHAT_ZERO_DEVICE_ID,
    canonical_chat_json,
    chat_session_binding,
)
from hushline.db import db
from hushline.model import (
    ChatAccount,
    ChatArchiveEpoch,
    ChatDevice,
    ChatOneTimePrekey,
    ChatPrekeyClaim,
    Conversation,
    ConversationMessage,
    ConversationMessageArchiveCopy,
    ConversationMessageTransportCopy,
    ConversationParticipant,
    NotificationRecipient,
    User,
)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _authenticate(client: FlaskClient, user: User, chat_session_id: str) -> None:
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = user.id
        browser_session["session_id"] = user.session_id
        browser_session["username"] = user.primary_username.username
        browser_session["is_authenticated"] = True
        browser_session[CHAT_KEY_SESSION_ID_SESSION_KEY] = chat_session_id
        browser_session["math_answer"] = "7"


def _initial_headers(app: Flask, recipient: User) -> dict[str, str]:
    nonce = "initial-pq-owner-guard"
    signature = hmac.new(
        key=(app.secret_key or "").encode(),
        msg=f"{recipient.primary_username.username}:{recipient.id}:{nonce}".encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {
        "X-Hushline-Owner-Guard-Nonce": nonce,
        "X-Hushline-Owner-Guard-Signature": signature,
        "X-Hushline-Captcha-Answer": "7",
    }


def _account_state(  # noqa: PLR0913
    user: User,
    *,
    account_id: str,
    device_id: str,
    session_id: str,
    membership_sequence: int,
    key_version: int,
    epoch: int,
    signing_key: Ed25519PrivateKey | None = None,
) -> tuple[ChatAccount, ChatDevice, Ed25519PrivateKey]:
    signing_key = signing_key or Ed25519PrivateKey.generate()
    signing_public_key = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    account = ChatAccount(
        user=user,
        public_id=account_id,
        identity_version=1,
        membership_sequence=membership_sequence,
        identity_public_key=_b64url(b"i" * 32),
    )
    device = ChatDevice(
        account=account,
        public_id=device_id,
        session_id_hash=chat_session_binding(session_id),
        membership_sequence=membership_sequence,
        key_version=key_version,
        membership_sha256=hashlib.sha256(device_id.encode()).hexdigest(),
        signing_public_key=_b64url(signing_public_key),
        protocol_identity_public_key=_b64url(b"p" * 32),
        account_identity_public_key=account.identity_public_key,
        membership={"device_id": device_id},
        membership_signature=_b64url(b"m" * 64),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    account.archive_epochs.append(
        ChatArchiveEpoch(
            epoch=epoch,
            public_key=_b64url(b"a" * 1216),
            encrypted_private_key=_b64url(b"w" * 64),
        )
    )
    db.session.add(account)
    return account, device, signing_key


def _conversation(sender: User, recipient: User, *, public_id: str | None = None) -> Conversation:
    thread = Conversation(public_id=public_id or str(uuid4()))
    thread.participants.extend(
        [
            ConversationParticipant(user=sender, has_usable_public_key=True),
            ConversationParticipant(user=recipient, has_usable_public_key=True),
        ]
    )
    db.session.add(thread)
    db.session.commit()
    return thread


def _protected_package(  # noqa: PLR0913
    thread_id: str,
    sender_account: ChatAccount,
    sender_device: ChatDevice,
    sender_signing_key: Ed25519PrivateKey,
    recipient_account: ChatAccount,
    recipient_device: ChatDevice,
    *,
    message_id: str | None = None,
) -> dict[str, Any]:
    message_id = message_id or str(uuid4())
    contexts = []
    for account in (sender_account, recipient_account):
        epoch = account.archive_epochs[0]
        contexts.append(
            {
                "account_recipient_id": account.public_id,
                "archive_epoch": epoch.epoch,
                "capability_offer": [PQ_CHAT_PROTOCOL],
                "capability_selection": PQ_CHAT_PROTOCOL,
                "conversation_id": thread_id,
                "device_recipient_id": PQ_CHAT_ZERO_DEVICE_ID,
                "key_version": epoch.epoch,
                "message_id": message_id,
                "protocol": PQ_CHAT_PROTOCOL,
                "purpose": "archive",
                "recipient_membership_sequence": account.membership_sequence,
                "sender_account_id": sender_account.public_id,
                "sender_device_id": sender_device.public_id,
                "sender_membership_sequence": sender_account.membership_sequence,
                "suite": PQ_CHAT_ARCHIVE_SUITE,
            }
        )
    contexts.append(
        {
            "account_recipient_id": recipient_account.public_id,
            "archive_epoch": 0,
            "capability_offer": [PQ_CHAT_PROTOCOL],
            "capability_selection": PQ_CHAT_PROTOCOL,
            "conversation_id": thread_id,
            "device_recipient_id": recipient_device.public_id,
            "key_version": recipient_device.key_version,
            "message_id": message_id,
            "protocol": PQ_CHAT_PROTOCOL,
            "purpose": "transport",
            "recipient_membership_sequence": recipient_account.membership_sequence,
            "sender_account_id": sender_account.public_id,
            "sender_device_id": sender_device.public_id,
            "sender_membership_sequence": sender_account.membership_sequence,
            "suite": PQ_CHAT_TRANSPORT_SUITE,
        }
    )
    contexts.sort(
        key=lambda context: (
            context["purpose"],
            context["account_recipient_id"],
            context["device_recipient_id"],
        )
    )

    copies = []
    manifest_copies = []
    for index, context in enumerate(contexts):
        ciphertext_bytes = (
            bytes([index + 1]) * 1136 if context["purpose"] == "archive" else b"transport-copy"
        )
        ciphertext = _b64url(ciphertext_bytes)
        context_sha256 = hashlib.sha256(canonical_chat_json(context)).hexdigest()
        ciphertext_sha256 = hashlib.sha256(ciphertext_bytes).hexdigest()
        copies.append({"context": context, "ciphertext": ciphertext})
        manifest_copies.append(
            {
                "account_recipient_id": context["account_recipient_id"],
                "archive_epoch": context["archive_epoch"],
                "ciphertext_length": len(ciphertext_bytes),
                "ciphertext_sha256": ciphertext_sha256,
                "context_sha256": context_sha256,
                "device_recipient_id": context["device_recipient_id"],
                "key_version": context["key_version"],
                "purpose": context["purpose"],
            }
        )
    manifest = {
        "capability_offer": [PQ_CHAT_PROTOCOL],
        "capability_selection": PQ_CHAT_PROTOCOL,
        "conversation_id": thread_id,
        "copies": manifest_copies,
        "created_at": "2026-09-29T12:00:00Z",
        "message_id": message_id,
        "protocol": PQ_CHAT_PROTOCOL,
        "sender_account_id": sender_account.public_id,
        "sender_device_id": sender_device.public_id,
        "sender_membership_sha256": sender_device.membership_sha256,
    }
    signature = sender_signing_key.sign(
        PQ_CHAT_SIGNATURE_DOMAIN + b"\x00" + canonical_chat_json(manifest)
    )
    return {"manifest": manifest, "signature": _b64url(signature), "copies": copies}


def _protected_state(
    sender: User, recipient: User
) -> tuple[
    ChatAccount,
    ChatDevice,
    Ed25519PrivateKey,
    ChatAccount,
    ChatDevice,
]:
    sender_account, sender_device, signing_key = _account_state(
        sender,
        account_id="33333333-3333-4333-8333-333333333333",
        device_id="44444444-4444-4444-8444-444444444444",
        session_id="sender-session",
        membership_sequence=12,
        key_version=9,
        epoch=7,
    )
    recipient_account, recipient_device, _ = _account_state(
        recipient,
        account_id="55555555-5555-4555-8555-555555555555",
        device_id="66666666-6666-4666-8666-666666666666",
        session_id="recipient-session",
        membership_sequence=18,
        key_version=14,
        epoch=11,
    )
    db.session.commit()
    return sender_account, sender_device, signing_key, recipient_account, recipient_device


def test_protected_reply_commits_complete_copy_set_and_replay_is_idempotent(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    sender_device.revoked_at = datetime.now(UTC)
    sender_account.membership_sequence += 1
    db.session.commit()
    _authenticate(client, user, "replacement-session")
    replay = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    stale_new_package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    stale_new_send = client.post(
        url_for("append_conversation_message", public_id=thread.public_id),
        json=stale_new_package,
    )

    assert response.status_code == 201
    assert replay.status_code == 200
    assert stale_new_send.status_code == 409
    assert stale_new_send.get_json() == {"error": "STALE_MEMBERSHIP"}
    assert replay.get_json()["message_id"] == response.get_json()["message_id"]
    db.session.refresh(thread)
    assert thread.minimum_protocol_version == 1
    assert thread.version == 1
    messages = db.session.scalars(
        db.select(ConversationMessage).where(ConversationMessage.conversation_id == thread.id)
    ).all()
    assert len(messages) == 1
    assert messages[0].conversation_version == 1
    assert len(messages[0].archive_copies) == 2
    assert len(messages[0].transport_copies) == 1


def test_protected_commit_atomically_consumes_reserved_transport_prekey(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    message_id = str(uuid4())
    prekey = ChatOneTimePrekey(
        device=recipient_device,
        key_id=1,
        membership_sequence=recipient_device.membership_sequence,
        classical_public_key=_b64url(b"\x05" + b"c" * 32),
        pq_public_key=_b64url(b"\x08" + b"p" * 1568),
        pq_signature=_b64url(b"s" * 64),
        publication_signature=_b64url(b"d" * 64),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    claim = ChatPrekeyClaim(
        claim_id=str(uuid5(UUID(message_id), recipient_device.public_id)),
        prekey=prekey,
        claimed_by_device=sender_device,
        reservation_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        tombstone_expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.session.add(claim)
    db.session.commit()
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
        message_id=message_id,
    )
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    replay = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )

    assert response.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()["idempotent"] is True
    db.session.refresh(claim)
    db.session.refresh(prekey)
    assert claim.consumed_at is not None
    assert prekey.consumed_at is not None
    assert prekey.tombstone_expires_at == claim.tombstone_expires_at


def test_concurrent_protected_replays_commit_one_logical_message(
    app: Flask, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    endpoint = url_for("append_conversation_message", public_id=thread.public_id)
    user_id = user.id
    user_session_id = user.session_id
    username = user.primary_username.username

    def send() -> int:
        with app.test_client() as concurrent_client:
            with concurrent_client.session_transaction() as browser_session:
                browser_session["user_id"] = user_id
                browser_session["session_id"] = user_session_id
                browser_session["username"] = username
                browser_session["is_authenticated"] = True
                browser_session[CHAT_KEY_SESSION_ID_SESSION_KEY] = "sender-session"
            return concurrent_client.post(endpoint, json=package).status_code

    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send) for _ in range(2)]
        statuses = sorted(future.result() for future in futures)

    assert statuses == [200, 201]
    assert db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage)) == 1


def test_protected_reply_rejects_missing_copy_without_partial_commit(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    package["copies"].pop(0)
    package["manifest"]["copies"].pop(0)
    package["signature"] = _b64url(
        signing_key.sign(
            PQ_CHAT_SIGNATURE_DOMAIN + b"\x00" + canonical_chat_json(package["manifest"])
        )
    )
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "STATE_CONFLICT"}
    assert db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage)) == 0
    assert (
        db.session.scalar(db.select(db.func.count()).select_from(ConversationMessageArchiveCopy))
        == 0
    )
    assert (
        db.session.scalar(db.select(db.func.count()).select_from(ConversationMessageTransportCopy))
        == 0
    )
    db.session.refresh(thread)
    assert thread.minimum_protocol_version == 0
    assert thread.version == 0


def test_protected_reply_rejects_tampered_ciphertext(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    package["copies"][0]["ciphertext"] = _b64url(b"x" * 1136)
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "AUTHENTICATION_FAILED"}
    assert db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage)) == 0


def test_protected_conversation_refuses_legacy_writer(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    thread.minimum_protocol_version = 1
    db.session.commit()
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id),
        json={"encrypted_copies": {}},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "Conversation requires protected messages."}
    assert db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage)) == 0


@pytest.mark.parametrize(
    ("include_content", "encrypt_entire_body"),
    [(False, False), (True, False), (True, True)],
)
def test_protected_reply_preserves_generic_notification_modes(  # noqa: PLR0913
    client: FlaskClient,
    user: User,
    user2: User,
    mocker: MockFixture,
    include_content: bool,
    encrypt_entire_body: bool,
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    notification_recipient = NotificationRecipient(
        position=user2.next_notification_recipient_position,
        enabled=True,
    )
    notification_recipient.email = "recipient@example.com"
    notification_recipient.pgp_key = "notification-public-key"
    user2.notification_recipients.append(notification_recipient)
    user2.enable_email_notifications = True
    user2.email_include_message_content = include_content
    user2.email_encrypt_entire_body = encrypt_entire_body
    db.session.commit()
    send_notification = mocker.patch("hushline.routes.message.send_email_to_user_recipients")
    encrypt_notification = mocker.patch(
        "hushline.routes.message.encrypt_message",
        return_value="-----BEGIN PGP MESSAGE-----\n\nencrypted\n-----END PGP MESSAGE-----",
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )

    assert response.status_code == 201
    send_notification.assert_called_once()
    body = send_notification.call_args.args[2]
    if include_content and encrypt_entire_body:
        assert body == "-----BEGIN PGP MESSAGE-----\n\nencrypted\n-----END PGP MESSAGE-----"
        encrypt_notification.assert_called_once()
    else:
        assert body == (
            "You have new Hush Line conversation activity. "
            "Log in and unlock your Hush Line chat key to read it."
        )
        encrypt_notification.assert_not_called()


def test_protected_message_read_returns_only_authenticated_accounts_copies(
    client: FlaskClient, user: User, user2: User, admin_user: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")
    created = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    message_id = created.get_json()["message_id"]
    sender_identity_at_send = sender_device.account_identity_public_key
    sender_account.identity_public_key = None
    sender_device.revoked_at = datetime.now(UTC)
    db.session.commit()

    _authenticate(client, user2, "recipient-session")
    response = client.get(
        url_for(
            "pq_conversation_message",
            public_id=thread.public_id,
            message_public_id=message_id,
        ),
        headers={"X-Hushline-Device-ID": recipient_device.public_id},
    )

    assert response.status_code == 200
    returned_copies = response.get_json()["copies"]
    assert response.get_json()["sender"] == {
        "account_identity_public_key": sender_identity_at_send,
        "device": {
            "membership": sender_device.membership,
            "membership_sha256": sender_device.membership_sha256,
            "membership_signature": sender_device.membership_signature,
        },
    }
    assert {copy["context"]["purpose"] for copy in returned_copies} == {
        "archive",
        "transport",
    }
    assert all(
        copy["context"]["account_recipient_id"] == recipient_account.public_id
        for copy in returned_copies
    )

    _authenticate(client, admin_user, "admin-session")
    denied = client.get(
        url_for(
            "pq_conversation_message",
            public_id=thread.public_id,
            message_public_id=message_id,
        ),
        headers={"X-Hushline-Device-ID": recipient_device.public_id},
    )
    assert denied.status_code == 404


def test_deletion_removes_unreferenced_retired_archive_key_but_keeps_current(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")
    created = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    assert created.status_code == 201

    old_epoch = sender_account.archive_epochs[0]
    old_epoch_id = old_epoch.id
    old_epoch.retired_at = datetime.now(UTC)
    current_epoch = ChatArchiveEpoch(
        account=sender_account,
        epoch=old_epoch.epoch + 1,
        public_key=_b64url(b"n" * 1216),
        encrypted_private_key=_b64url(b"z" * 64),
    )
    db.session.add(current_epoch)
    db.session.commit()

    deleted = client.post(url_for("delete_conversation", public_id=thread.public_id))

    assert deleted.status_code == 302
    assert db.session.get(ChatArchiveEpoch, old_epoch_id) is None
    assert db.session.get(ChatArchiveEpoch, current_epoch.id) is not None
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ChatArchiveEpoch)
            .where(ChatArchiveEpoch.account_id == recipient_account.id)
        )
        == 1
    )


def test_account_deletion_removes_own_pq_state_without_corrupting_recipient_history(
    client: FlaskClient, user: User, user2: User
) -> None:
    thread = _conversation(user, user2)
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    package = _protected_package(
        thread.public_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")
    created = client.post(
        url_for("append_conversation_message", public_id=thread.public_id), json=package
    )
    assert created.status_code == 201
    message_id = created.get_json()["message_id"]
    sender_user_id = user.id
    sender_account_id = sender_account.id
    sender_device_id = sender_device.id
    thread_id = thread.id

    deleted = client.post(url_for("settings.delete_account"))

    assert deleted.status_code == 302
    assert db.session.get(User, sender_user_id) is None
    sender_participant = db.session.scalars(
        db.select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == thread.id,
            ConversationParticipant.user_id.is_(None),
        )
    ).one()
    assert db.session.get(ChatAccount, sender_account_id) is None
    assert db.session.get(ChatDevice, sender_device_id) is None
    assert sender_participant.deleted_at is not None
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ChatArchiveEpoch)
            .where(ChatArchiveEpoch.account_id == sender_account_id)
        )
        == 0
    )
    message = db.session.scalars(
        db.select(ConversationMessage).where(ConversationMessage.public_id == message_id)
    ).one()
    assert message.archive_copies == []
    assert message.transport_copies == []

    _authenticate(client, user2, "recipient-session")
    inbox = client.get(url_for("inbox", type="conversations"))
    assert inbox.status_code == 200
    assert "Deleted participant" in inbox.text
    retained = client.get(url_for("conversation", public_id=thread.public_id))
    assert retained.status_code == 200
    assert "Deleted participant" in retained.text
    assert "This message was deleted." in retained.text
    assert message_id not in retained.text

    final_deletion = client.post(url_for("settings.delete_account"))
    assert final_deletion.status_code == 302
    assert db.session.get(Conversation, thread_id) is None


def test_initial_protected_endpoint_creates_one_conversation(
    app: Flask, client: FlaskClient, user: User, user2: User
) -> None:
    sender_account, sender_device, signing_key, recipient_account, recipient_device = (
        _protected_state(user, user2)
    )
    conversation_id = str(uuid4())
    package = _protected_package(
        conversation_id,
        sender_account,
        sender_device,
        signing_key,
        recipient_account,
        recipient_device,
    )
    _authenticate(client, user, "sender-session")

    response = client.post(
        url_for(
            "create_pq_conversation_message",
            username=user2.primary_username.username,
        ),
        json=package,
        headers=_initial_headers(app, user2),
    )

    assert response.status_code == 201
    thread = db.session.scalars(
        db.select(Conversation).where(Conversation.public_id == conversation_id)
    ).one()
    assert {participant.user_id for participant in thread.participants} == {user.id, user2.id}
    assert len(thread.messages) == 1
    assert thread.minimum_protocol_version == 1
    assert thread.initial_message is not None
    assert thread.messages[0].encrypted_copies == []
    assert all(
        field_value.value == "Stored in encrypted conversation."
        for field_value in thread.initial_message.field_values
    )

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from flask import Flask, url_for
from flask.testing import FlaskClient
from sqlalchemy import text

from hushline.db import db
from hushline.model import (
    ChatKey,
    ChatRateLimitAttempt,
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    FieldValue,
    Message,
    NotificationRecipient,
    User,
)
from hushline.routes.message import (
    _as_utc,
    _canonical_chat_signature_payload,
    _chat_ciphertext_context,
    _chat_ciphertext_context_is_bound,
    _chat_ciphertext_signature_is_valid,
    _chat_ciphertext_signatures_are_valid,
    _chat_signing_public_key,
    _consume_conversation_message_rate_limit,
    _conversation_activity_timeout,
    _conversation_notification_body,
    _conversation_presence_heartbeat_ms,
    _decode_jwk_coordinate,
    _is_chat_ciphertext_envelope,
)

_SENDER_SIGNING_PRIVATE_KEY = ec.derive_private_key(1, ec.SECP256R1())
_RECIPIENT_SIGNING_PRIVATE_KEY = ec.derive_private_key(2, ec.SECP256R1())


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _public_signing_jwk(private_key: ec.EllipticCurvePrivateKey) -> str:
    public_numbers = private_key.public_key().public_numbers()
    return json.dumps(
        {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(public_numbers.x.to_bytes(32, "big")),
            "y": _b64url(public_numbers.y.to_bytes(32, "big")),
            "key_ops": ["verify"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


_SENDER_PUBLIC_SIGNING_KEY = _public_signing_jwk(_SENDER_SIGNING_PRIVATE_KEY)
_RECIPIENT_PUBLIC_SIGNING_KEY = _public_signing_jwk(_RECIPIENT_SIGNING_PRIVATE_KEY)


def _canonical_chat_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sign_chat_envelope(
    envelope: dict[str, object],
    private_key: ec.EllipticCurvePrivateKey,
) -> str:
    signed_payload = {
        "v": envelope["v"],
        "algorithm": envelope["algorithm"],
        "ephemeral_public_key": envelope["ephemeral_public_key"],
        "iv": envelope["iv"],
        "ciphertext": envelope["ciphertext"],
        "context": envelope["context"],
    }
    der_signature = private_key.sign(
        _canonical_chat_json(signed_payload).encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    r_value, s_value = decode_dss_signature(der_signature)
    return base64.b64encode(r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big")).decode(
        "ascii"
    )


def _signing_private_key_for_participant(
    conversation: Conversation,
    participant: ConversationParticipant,
) -> ec.EllipticCurvePrivateKey:
    participant_ids = [thread_participant.id for thread_participant in conversation.participants]
    return (
        _SENDER_SIGNING_PRIVATE_KEY
        if participant_ids.index(participant.id) == 0
        else _RECIPIENT_SIGNING_PRIVATE_KEY
    )


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True


def _add_chat_key(
    user: User,
    public_key: str,
    *,
    public_signing_key: str | None = None,
) -> None:
    db.session.add(
        ChatKey(
            user=user,
            key_version=1,
            public_key=public_key,
            public_signing_key=public_signing_key,
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )


def _add_reply_capable_chat_keys(sender: User, recipient: User) -> None:
    _add_chat_key(
        sender,
        '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}',
        public_signing_key=_SENDER_PUBLIC_SIGNING_KEY,
    )
    _add_chat_key(
        recipient,
        '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}',
        public_signing_key=_RECIPIENT_PUBLIC_SIGNING_KEY,
    )


def _enable_conversation_notifications(
    user: User,
    *,
    email: str,
    include_content: bool,
    encrypt_entire_body: bool,
    pgp_key: str = "notification-pgp-key",
) -> None:
    recipient = NotificationRecipient(position=user.next_notification_recipient_position)
    recipient.email = email
    recipient.pgp_key = pgp_key
    recipient.enabled = True
    user.notification_recipients.append(recipient)
    user.enable_email_notifications = True
    user.email_include_message_content = include_content
    user.email_encrypt_entire_body = encrypt_entire_body


def _ciphertext(label: str) -> str:
    return json.dumps(
        {
            "algorithm": "ECDH-P256-AES-GCM",
            "ephemeral_public_key": '{"kty":"EC","crv":"P-256","x":"ephemeral","y":"key"}',
            "iv": f"iv-{label}",
            "ciphertext": f"ciphertext-{label}",
        }
    )


def _context_bound_ciphertext(
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    recipient_participant: ConversationParticipant,
    label: str,
    *,
    context_overrides: dict[str, str] | None = None,
) -> str:
    context = {
        "purpose": "hushline.chat.message",
        "conversation_public_id": conversation.public_id,
        "sender_participant_id": str(sender_participant.id),
        "recipient_participant_id": str(recipient_participant.id),
    }
    if context_overrides:
        context.update(context_overrides)
    return _bound_ciphertext(
        context=context,
        label=label,
        signing_private_key=_signing_private_key_for_participant(conversation, sender_participant),
    )


def _bound_ciphertext(
    *,
    context: dict[str, str],
    label: str,
    signing_private_key: ec.EllipticCurvePrivateKey,
) -> str:
    envelope: dict[str, object] = {
        "v": 2,
        "algorithm": "ECDH-P256-AES-GCM",
        "ephemeral_public_key": '{"kty":"EC","crv":"P-256","x":"ephemeral","y":"key"}',
        "iv": f"iv-{label}",
        "ciphertext": f"ciphertext-{label}",
        "context": context,
    }
    envelope["signature"] = _sign_chat_envelope(envelope, signing_private_key)
    return json.dumps(envelope)


def _make_conversation(
    sender: User,
    recipient: User,
    *,
    include_initial_copy: bool = True,
) -> Conversation:
    conversation = Conversation()
    sender_participant = ConversationParticipant()
    sender_participant.conversation = conversation
    sender_participant.user = sender
    sender_participant.has_usable_public_key = True
    recipient_participant = ConversationParticipant()
    recipient_participant.conversation = conversation
    recipient_participant.user = recipient
    recipient_participant.has_usable_public_key = True
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = sender_participant
    if include_initial_copy:
        sender_copy = ConversationMessageCopy()
        sender_copy.recipient_participant = sender_participant
        sender_copy.encrypted_payload = _ciphertext("sender-initial")
        recipient_copy = ConversationMessageCopy()
        recipient_copy.recipient_participant = recipient_participant
        recipient_copy.encrypted_payload = _ciphertext("recipient-initial")
        conversation_message.encrypted_copies.extend(
            [
                sender_copy,
                recipient_copy,
            ]
        )
    db.session.add(conversation)
    db.session.commit()
    return conversation


def _copies_for(conversation: Conversation, label: str) -> dict[str, str]:
    return {
        str(participant.id): _ciphertext(f"{label}-{participant.id}")
        for participant in conversation.participants
    }


def _bound_context(
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    recipient_participant: ConversationParticipant,
    *,
    use_legacy_conversation_id: bool,
) -> dict[str, str]:
    context = {
        "purpose": "hushline.chat.message",
        "sender_participant_id": str(sender_participant.id),
        "recipient_participant_id": str(recipient_participant.id),
    }
    if use_legacy_conversation_id:
        context["conversation_id"] = str(conversation.id)
    else:
        context["conversation_public_id"] = conversation.public_id
    return context


def _bound_copies_for(
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    label: str,
    *,
    use_legacy_conversation_id: bool = False,
    signing_private_key: ec.EllipticCurvePrivateKey | None = None,
) -> dict[str, str]:
    signing_private_key = signing_private_key or _signing_private_key_for_participant(
        conversation,
        sender_participant,
    )
    return {
        str(participant.id): _bound_ciphertext(
            context=_bound_context(
                conversation,
                sender_participant,
                participant,
                use_legacy_conversation_id=use_legacy_conversation_id,
            ),
            label=f"{label}-{participant.id}",
            signing_private_key=signing_private_key,
        )
        for participant in conversation.participants
    }


def _reply_copies_for(conversation: Conversation, sender: User, label: str) -> dict[str, str]:
    return _bound_copies_for(conversation, _participant_for(conversation, sender), label)


def _participant_for(conversation: Conversation, user: User) -> ConversationParticipant:
    participant = conversation.participant_for_user_id(user.id)
    assert participant is not None
    return participant


def _set_initial_message_created_at(conversation: Conversation, created_at: datetime) -> None:
    conversation.messages[0].created_at = created_at
    db.session.commit()


def _add_conversation_message(
    conversation: Conversation,
    sender_participant: ConversationParticipant,
    *,
    created_at: datetime,
    label: str,
) -> ConversationMessage:
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = sender_participant
    conversation_message.created_at = created_at
    db.session.add(conversation_message)
    for recipient_participant in conversation.participants:
        encrypted_copy = ConversationMessageCopy()
        encrypted_copy.message = conversation_message
        encrypted_copy.recipient_participant = recipient_participant
        encrypted_copy.encrypted_payload = _ciphertext(f"{label}-{recipient_participant.id}")
        db.session.add(encrypted_copy)
    db.session.commit()
    return conversation_message


def test_conversation_timing_helpers_fall_back_to_safe_defaults(app: Flask) -> None:
    app.config["CONVERSATION_ACTIVITY_TIMEOUT_SECONDS"] = "not-a-number"
    app.config["CONVERSATION_PRESENCE_HEARTBEAT_SECONDS"] = "not-a-number"

    assert _conversation_activity_timeout() == timedelta(seconds=120)
    assert _conversation_presence_heartbeat_ms() == 60_000


def test_as_utc_treats_naive_datetimes_as_utc() -> None:
    naive_datetime = datetime(2026, 1, 1, 12, 0)

    assert _as_utc(naive_datetime) == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "{not-json",
        "[]",
        json.dumps({"algorithm": "ECDH-P256-AES-GCM"}),
        json.dumps(
            {
                "algorithm": "AES-GCM",
                "ephemeral_public_key": "ephemeral",
                "iv": "iv",
                "ciphertext": "ciphertext",
            }
        ),
        json.dumps(
            {
                "v": 3,
                "algorithm": "ECDH-P256-AES-GCM",
                "ephemeral_public_key": "ephemeral",
                "iv": "iv",
                "ciphertext": "ciphertext",
            }
        ),
        json.dumps(
            {
                "v": 2,
                "algorithm": "ECDH-P256-AES-GCM",
                "ephemeral_public_key": "ephemeral",
                "iv": "iv",
                "ciphertext": "ciphertext",
                "context": {},
            }
        ),
    ],
)
def test_chat_ciphertext_envelope_rejects_malformed_values(app: Flask, value: str) -> None:
    _ = app

    assert not _is_chat_ciphertext_envelope(value)


def test_chat_ciphertext_context_rejects_malformed_values(app: Flask) -> None:
    _ = app

    assert _chat_ciphertext_context("{not-json") is None
    assert _chat_ciphertext_context("[]") is None
    assert _chat_ciphertext_context(json.dumps({"v": 1, "context": {"safe": "metadata"}})) is None


def test_canonical_chat_signature_payload_rejects_missing_fields() -> None:
    assert _canonical_chat_signature_payload({"v": 2}) is None


@pytest.mark.parametrize(
    "value",
    ["", "not-base64", base64.urlsafe_b64encode(b"short").decode()],
)
def test_decode_jwk_coordinate_rejects_invalid_values(value: str) -> None:
    assert _decode_jwk_coordinate(value) is None


@pytest.mark.parametrize(
    "public_signing_key",
    [
        None,
        "{not-json",
        "[]",
        '{"kty":"OKP","crv":"Ed25519","x":"x","y":"y"}',
        '{"kty":"EC","crv":"P-256","x":"not-base64","y":"not-base64"}',
        json.dumps(
            {
                "kty": "EC",
                "crv": "P-256",
                "x": _b64url((0).to_bytes(32, "big")),
                "y": _b64url((0).to_bytes(32, "big")),
            }
        ),
    ],
)
def test_chat_signing_public_key_rejects_invalid_jwks(
    app: Flask, public_signing_key: str | None
) -> None:
    _ = app

    assert _chat_signing_public_key(public_signing_key) is None


def test_chat_ciphertext_signature_rejects_invalid_payloads(app: Flask) -> None:
    _ = app

    valid_payload = _bound_ciphertext(
        context={
            "purpose": "hushline.chat.message",
            "conversation_public_id": "thread-public-id",
            "sender_participant_id": "1",
            "recipient_participant_id": "2",
        },
        label="signature-branches",
        signing_private_key=_SENDER_SIGNING_PRIVATE_KEY,
    )
    valid_envelope = json.loads(valid_payload)

    assert not _chat_ciphertext_signature_is_valid(valid_payload, None)
    assert not _chat_ciphertext_signature_is_valid("{not-json", _SENDER_PUBLIC_SIGNING_KEY)
    assert not _chat_ciphertext_signature_is_valid(json.dumps({"v": 1}), _SENDER_PUBLIC_SIGNING_KEY)

    missing_payload_field = dict(valid_envelope)
    missing_payload_field.pop("ciphertext")
    assert not _chat_ciphertext_signature_is_valid(
        json.dumps(missing_payload_field), _SENDER_PUBLIC_SIGNING_KEY
    )

    non_string_signature = dict(valid_envelope)
    non_string_signature["signature"] = 123
    assert not _chat_ciphertext_signature_is_valid(
        json.dumps(non_string_signature), _SENDER_PUBLIC_SIGNING_KEY
    )

    invalid_base64_signature = dict(valid_envelope)
    invalid_base64_signature["signature"] = "not base64"
    assert not _chat_ciphertext_signature_is_valid(
        json.dumps(invalid_base64_signature), _SENDER_PUBLIC_SIGNING_KEY
    )

    wrong_length_signature = dict(valid_envelope)
    wrong_length_signature["signature"] = base64.b64encode(b"short").decode("ascii")
    assert not _chat_ciphertext_signature_is_valid(
        json.dumps(wrong_length_signature), _SENDER_PUBLIC_SIGNING_KEY
    )

    bogus_signature = dict(valid_envelope)
    bogus_signature["signature"] = base64.b64encode(b"0" * 64).decode("ascii")
    assert not _chat_ciphertext_signature_is_valid(
        json.dumps(bogus_signature), _SENDER_PUBLIC_SIGNING_KEY
    )


def test_chat_ciphertext_signatures_reject_non_string_copy(app: Flask) -> None:
    _ = app

    assert not _chat_ciphertext_signatures_are_valid(
        {"1": object()},
        public_signing_key=_SENDER_PUBLIC_SIGNING_KEY,
    )


@pytest.mark.parametrize(
    "context_overrides",
    [
        {"purpose": "wrong-purpose"},
        {"conversation_public_id": "wrong-conversation"},
        {"sender_participant_id": "999999"},
        {"recipient_participant_id": "999999"},
    ],
)
def test_chat_ciphertext_context_binding_rejects_mismatches(
    user: User,
    user2: User,
    context_overrides: dict[str, str],
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)

    assert not _chat_ciphertext_context_is_bound(
        {
            str(recipient_participant.id): _context_bound_ciphertext(
                conversation,
                sender_participant,
                recipient_participant,
                "context-mismatch",
                context_overrides=context_overrides,
            )
        },
        conversation=conversation,
        sender_participant_id=sender_participant.id,
    )


def test_chat_ciphertext_context_binding_rejects_non_string_payload(
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)

    assert not _chat_ciphertext_context_is_bound(
        {"1": object()},
        conversation=conversation,
        sender_participant_id=sender_participant.id,
    )


def test_chat_ciphertext_context_binding_rejects_legacy_conversation_id_mismatch(
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    encrypted_payload = _bound_ciphertext(
        context={
            "purpose": "hushline.chat.message",
            "conversation_id": "999999",
            "sender_participant_id": str(sender_participant.id),
            "recipient_participant_id": str(recipient_participant.id),
        },
        label="legacy-conversation-id-mismatch",
        signing_private_key=_SENDER_SIGNING_PRIVATE_KEY,
    )

    assert not _chat_ciphertext_context_is_bound(
        {str(recipient_participant.id): encrypted_payload},
        conversation=conversation,
        sender_participant_id=sender_participant.id,
    )


def test_conversation_notification_body_is_generic_without_encryption_target(user: User) -> None:
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True

    body = _conversation_notification_body(user)

    assert body == (
        "You have new Hush Line conversation activity. "
        "Log in and unlock your Hush Line chat key to read it."
    )


@patch("hushline.routes.message.encrypt_message")
def test_conversation_notification_body_falls_back_when_encryption_fails(
    mock_encrypt_message: MagicMock,
    user: User,
) -> None:
    _enable_conversation_notifications(
        user,
        email="recipient@example.com",
        include_content=True,
        encrypt_entire_body=True,
        pgp_key="recipient-pgp-key",
    )
    mock_encrypt_message.side_effect = RuntimeError("encryption failed")

    body = _conversation_notification_body(user)

    assert body == (
        "You have new Hush Line conversation activity. "
        "Log in and unlock your Hush Line chat key to read it."
    )


def test_conversation_route_authorizes_only_participants(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    conversation = _make_conversation(user, user2)

    _authenticate_as(client, user)
    sender_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert sender_response.status_code == 200
    assert "Secure chat unavailable" in sender_response.text
    assert "conversation-chat-password" not in sender_response.text

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert recipient_response.status_code == 200
    assert "Secure chat unavailable" in recipient_response.text
    assert "conversation-chat-password" not in recipient_response.text

    _authenticate_as(client, admin_user)
    unrelated_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert unrelated_response.status_code == 404

    with client.session_transaction() as session:
        session.clear()
    unauthenticated_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert unauthenticated_response.status_code == 302
    assert unauthenticated_response.headers["Location"].endswith(url_for("login"))


def test_conversation_header_names_other_participant(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert recipient_response.status_code == 200
    assert f"<h1>{user.primary_username.username}</h1>" in recipient_response.text
    assert f"@{user.primary_username.username}" in recipient_response.text
    assert f"<h1>{user2.primary_username.username}</h1>" not in recipient_response.text


def test_conversation_view_shows_locked_chat_key_state(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    recipient_participant = _participant_for(conversation, user2)
    _add_conversation_message(
        conversation,
        recipient_participant,
        created_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        label="recipient-reply",
    )
    _authenticate_as(client, user)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    assert 'class="conversation-thread"' in response.text
    assert 'class="conversation-composer"' in response.text
    assert 'class="conversation-chat"' in response.text
    assert response.text.count("is-own-message") == 1
    assert response.text.count("is-other-message") == 1
    assert 'rows="1"' in response.text
    assert 'placeholder="Message"' in response.text
    assert re.search(
        r'<button(?=[^>]*\bid="conversation-compose-submit")'
        r'(?=[^>]*\bdisabled="disabled")[^>]*>',
        response.text,
    )
    assert 'data-participant-id="' in response.text
    assert "Messages are encrypted until your browser chat key unlocks." in response.text
    assert "JavaScript is required for end-to-end encrypted chat." in response.text
    assert "server-side chat fallback for conversations" in response.text
    assert "Encrypted message. Waiting for browser chat key." in response.text
    assert (
        "Replies are unavailable until every participant has an active signing-capable"
        in response.text
    )
    assert "conversation-chat-password" not in response.text
    assert "Unlock Chat" not in response.text
    assert "Proton" not in response.text
    assert "PGP" not in response.text
    assert url_for("conversation_presence", public_id=conversation.public_id) in response.text


def test_conversation_header_includes_actions_menu(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    assert 'class="conversation-actions action-menu"' in response.text
    assert 'class="conversation-actions-button action-menu-button"' in response.text
    assert 'aria-label="Conversation actions"' in response.text
    assert "&#8942;" not in response.text
    assert 'aria-haspopup="menu"' in response.text
    assert 'id="conversation-actions-menu"' in response.text
    assert 'role="menu"' in response.text
    assert url_for("delete_conversation", public_id=conversation.public_id) in response.text
    assert "Delete this conversation from your inbox?" in response.text
    assert 'role="menuitem"' in response.text
    assert ">Delete</button>" in response.text


def test_conversation_view_disables_composer_when_participant_key_cannot_sign(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(
        user2,
        '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}',
        public_signing_key='{"kty":"EC","crv":"P-256","x":"recipient-sign","y":"key"}',
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    assert 'data-can-compose="false"' in response.text
    assert "active signing-capable" in response.text
    participant_keys_match = re.search(
        r'<script id="conversationParticipantPublicKeys" type="application/json">\s*'
        r"([\s\S]*?)</script>",
        response.text,
    )
    assert participant_keys_match is not None
    participant_keys = json.loads(participant_keys_match.group(1))
    assert [participant_key["participant_id"] for participant_key in participant_keys] == [
        _participant_for(conversation, user2).id
    ]


def test_conversation_view_exposes_historical_signing_keys_for_initial_message_verification(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    old_signing_key = '{"kty":"EC","crv":"P-256","x":"old-signing","y":"key"}'
    new_signing_key = '{"kty":"EC","crv":"P-256","x":"new-signing","y":"key"}'
    db.session.add_all(
        [
            ChatKey(
                user=user,
                key_version=1,
                public_key='{"kty":"EC","crv":"P-256","x":"old-sender","y":"key"}',
                public_signing_key=old_signing_key,
                encrypted_private_key="wrapped-old-private-chat-key",
                kdf_algorithm="PBKDF2-SHA-256",
                kdf_params={"iterations": 310000},
                kdf_salt="salt",
                wrapping_algorithm="AES-GCM",
                disabled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            ChatKey(
                user=user,
                key_version=2,
                public_key='{"kty":"EC","crv":"P-256","x":"new-sender","y":"key"}',
                public_signing_key=new_signing_key,
                encrypted_private_key="wrapped-new-private-chat-key",
                kdf_algorithm="PBKDF2-SHA-256",
                kdf_params={"iterations": 310000},
                kdf_salt="salt",
                wrapping_algorithm="AES-GCM",
            ),
        ]
    )
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    db.session.commit()
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user2)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    signing_keys_match = re.search(
        r'<script id="conversationParticipantSigningPublicKeys" type="application/json">\s*'
        r"([\s\S]*?)</script>",
        response.text,
    )
    assert signing_keys_match is not None
    signing_keys = json.loads(signing_keys_match.group(1))
    sender_participant_id = _participant_for(conversation, user).id
    assert {
        signing_key["public_signing_key"]
        for signing_key in signing_keys
        if signing_key["participant_id"] == sender_participant_id
    } == {old_signing_key, new_signing_key}


def test_conversation_view_hides_message_metadata_from_page_payload(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    recipient_participant = _participant_for(conversation, user2)
    message_created_at = datetime(2026, 2, 1, 12, 5, tzinfo=timezone.utc)
    _add_conversation_message(
        conversation,
        recipient_participant,
        created_at=message_created_at,
        label="timestamp-leak-check",
    )

    _authenticate_as(client, user)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    payload_match = re.search(
        r'<script id="conversationMessageCopies" type="application/json">\s*([\s\S]*?)</script>',
        response.text,
    )
    assert payload_match is not None

    message_copy_payloads = json.loads(payload_match.group(1))
    assert isinstance(message_copy_payloads, list)
    assert all(
        {
            "message_id",
            "encrypted_payload",
        }
        == set(message_copy_payload.keys())
        for message_copy_payload in message_copy_payloads
    )
    assert all(
        "created_at" not in message_copy_payload
        and "sender_participant_id" not in message_copy_payload
        for message_copy_payload in message_copy_payloads
    )
    assert f"{message_created_at.isoformat()}" not in response.text
    assert '<time datetime="' not in response.text


def test_conversation_view_marks_participant_active(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    participant = _participant_for(conversation, user)
    _authenticate_as(client, user)

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    db.session.refresh(participant)
    assert participant.last_active_at is not None


def test_conversation_presence_requires_participant(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    conversation = _make_conversation(user, user2)
    participant = _participant_for(conversation, user)
    _authenticate_as(client, admin_user)

    response = client.post(url_for("conversation_presence", public_id=conversation.public_id))

    assert response.status_code == 404
    db.session.refresh(participant)
    assert participant.last_active_at is None


def test_conversation_presence_heartbeat_marks_participant_active(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    participant = _participant_for(conversation, user)
    _authenticate_as(client, user)

    response = client.post(url_for("conversation_presence", public_id=conversation.public_id))

    assert response.status_code == 200
    db.session.refresh(participant)
    assert participant.last_active_at is not None


def test_conversation_presence_accepts_rendered_csrf_token(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    participant = _participant_for(conversation, user)
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        page_response = client.get(url_for("conversation", public_id=conversation.public_id))
        token_match = re.search(r'data-csrf-token="([^"]+)"', page_response.text)
        assert token_match is not None

        response = client.post(
            url_for("conversation_presence", public_id=conversation.public_id),
            headers={"X-CSRFToken": token_match.group(1)},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 200
    db.session.refresh(participant)
    assert participant.last_active_at is not None


def test_conversation_presence_requires_csrf_when_enabled(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(url_for("conversation_presence", public_id=conversation.public_id))
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text


def test_participant_delete_removes_only_their_side_of_conversation(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    conversation_id = conversation.id
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    initial_message = Message(username_id=user2.primary_username.id)
    initial_message.conversation = conversation
    db.session.add(initial_message)
    db.session.commit()
    initial_message_id = initial_message.id
    conversation_message_ids = [message.id for message in conversation.messages]
    conversation_copy_ids = [
        encrypted_copy.id
        for message in conversation.messages
        for encrypted_copy in message.encrypted_copies
    ]
    _authenticate_as(client, user)

    response = client.post(
        url_for("delete_conversation", public_id=conversation.public_id),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox", type="conversations"))
    retained_conversation = db.session.get(Conversation, conversation_id)
    assert retained_conversation is not None
    db.session.refresh(sender_participant)
    assert sender_participant.deleted_at is not None
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
        )
        == 2
    )
    assert all(
        db.session.get(ConversationMessage, message_id) is not None
        for message_id in conversation_message_ids
    )
    assert all(
        db.session.get(ConversationMessageCopy, copy_id) is None
        for copy_id in conversation_copy_ids
    )
    assert db.session.scalars(Conversation.for_user_id(user.id)).all() == []
    assert db.session.scalars(Conversation.for_user_id(user2.id)).all() == [retained_conversation]
    retained_message = db.session.get(Message, initial_message_id)
    assert retained_message is not None
    assert retained_message.conversation_id is None

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", public_id=conversation.public_id))
    inbox_response = client.get(url_for("inbox"))

    assert recipient_response.status_code == 200
    assert "This message was deleted." in recipient_response.text
    assert inbox_response.status_code == 200
    assert url_for("message", public_id=retained_message.public_id) in inbox_response.text
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessageCopy)
            .where(ConversationMessageCopy.recipient_participant_id == recipient_participant.id)
        )
        == 0
    )


def test_delete_conversation_removes_chat_only_placeholder_after_all_participants_delete(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    conversation_id = conversation.id
    initial_message = Message(username_id=user2.primary_username.id)
    initial_message.conversation = conversation
    db.session.add(initial_message)
    db.session.flush()
    placeholder_value = FieldValue(
        user2.primary_username.message_fields[-1],
        initial_message,
        "Stored in encrypted conversation.",
        False,
    )
    db.session.add(placeholder_value)
    db.session.commit()
    initial_message_id = initial_message.id
    placeholder_value_id = placeholder_value.id
    _authenticate_as(client, user)

    response = client.post(
        url_for("delete_conversation", public_id=conversation.public_id),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert db.session.get(Conversation, conversation_id) is not None
    assert db.session.get(Message, initial_message_id) is not None
    assert db.session.get(FieldValue, placeholder_value_id) is not None

    _authenticate_as(client, user2)
    response = client.post(
        url_for("delete_conversation", public_id=conversation.public_id),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert db.session.get(Conversation, conversation_id) is None
    assert db.session.get(Message, initial_message_id) is None
    assert db.session.get(FieldValue, placeholder_value_id) is None


def test_delete_conversation_detaches_initial_message_for_owner(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    initial_message = Message(username_id=user2.primary_username.id)
    initial_message.conversation = conversation
    db.session.add(initial_message)
    db.session.commit()
    initial_message_id = initial_message.id
    _authenticate_as(client, user2)

    response = client.post(
        url_for("delete_conversation", public_id=conversation.public_id),
        follow_redirects=False,
    )
    inbox_response = client.get(url_for("inbox"))

    assert response.status_code == 302
    retained_message = db.session.get(Message, initial_message_id)
    assert retained_message is not None
    assert retained_message.conversation_id is None
    assert db.session.get(Conversation, conversation.id) is not None
    assert db.session.scalars(Conversation.for_user_id(user2.id)).all() == []
    assert inbox_response.status_code == 200
    assert url_for("message", public_id=retained_message.public_id) in inbox_response.text


def test_delete_conversation_cleans_up_when_other_participant_already_deleted(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    conversation_id = conversation.id
    other_participant = _participant_for(conversation, user2)
    other_participant.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    _authenticate_as(client, user)

    response = client.post(
        url_for("delete_conversation", public_id=conversation.public_id),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert db.session.get(Conversation, conversation_id) is None


def test_delete_conversation_requires_participant(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    conversation = _make_conversation(user, user2)
    conversation_id = conversation.id
    _authenticate_as(client, admin_user)

    response = client.post(url_for("delete_conversation", public_id=conversation.public_id))

    assert response.status_code == 404
    assert db.session.get(Conversation, conversation_id) is not None


def test_delete_conversation_redirects_unauthenticated_user(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)

    response = client.post(url_for("delete_conversation", public_id=conversation.public_id))

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))
    assert db.session.get(Conversation, conversation.id) is not None


def test_delete_conversation_requires_csrf_when_enabled(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(url_for("delete_conversation", public_id=conversation.public_id))
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    assert db.session.get(Conversation, conversation.id) is not None


def test_delete_conversation_accepts_rendered_csrf_token(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    conversation_id = conversation.id
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        page_response = client.get(url_for("conversation", public_id=conversation.public_id))
        assert page_response.text.count('id="csrf_token"') == 1
        assert 'id="delete_conversation_csrf_token"' in page_response.text
        token_match = re.search(
            (
                r'<input\s+[^>]*id="delete_conversation_csrf_token"'
                r'[^>]*name="csrf_token"[^>]*value="([^"]+)"'
            ),
            page_response.text,
        )
        assert token_match is not None

        response = client.post(
            url_for("delete_conversation", public_id=conversation.public_id),
            data={"csrf_token": token_match.group(1)},
            follow_redirects=False,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 302
    assert db.session.get(Conversation, conversation_id) is not None
    participant = db.session.scalar(
        db.select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user.id,
        )
    )
    assert participant is not None
    assert participant.deleted_at is not None


def test_append_conversation_message_rejects_when_participant_deleted_their_side(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    sender_participant.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    _authenticate_as(client, user2)

    page_response = client.get(url_for("conversation", public_id=conversation.public_id))
    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user2, "after-delete")},
    )

    assert page_response.status_code == 200
    assert 'data-can-compose="false"' in page_response.text
    assert response.status_code == 400
    assert response.get_json() == {"error": "Conversation replies are unavailable."}


def test_append_conversation_message_rejects_non_object_payload(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json=[],
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_rejects_non_object_encrypted_copies(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": []},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_participant_can_append_encrypted_conversation_message(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    plaintext = "plaintext follow-up must not be stored"
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "follow-up")},
    )

    assert response.status_code == 201
    messages = db.session.scalars(
        db.select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.asc())
    ).all()
    assert len(messages) == 2
    assert messages[-1].sender_participant.user_id == user.id
    assert len(messages[-1].encrypted_copies) == 2
    for encrypted_copy in messages[-1].encrypted_copies:
        assert "ECDH-P256-AES-GCM" in encrypted_copy.encrypted_payload
        assert plaintext not in encrypted_copy.encrypted_payload


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_rate_limits_participant_without_persistence_or_notification(
    mock_send_email_to_user_recipients: MagicMock,
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 20
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    first_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "first-rate-limited")},
    )
    mock_send_email_to_user_recipients.reset_mock()
    second_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "second-rate-limited")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.get_json() == {
        "error": "Too many chat messages. Please wait before sending another reply."
    }
    message_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
    )
    copy_count = db.session.scalar(
        db.select(db.func.count())
        .select_from(ConversationMessageCopy)
        .join(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
    )
    attempt_count = db.session.scalar(db.select(db.func.count()).select_from(ChatRateLimitAttempt))
    assert message_count == 2
    assert copy_count == 4
    assert attempt_count == 1
    mock_send_email_to_user_recipients.assert_not_called()


def test_append_conversation_message_rate_limit_is_scoped_to_sender_participant(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 20
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    first_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "sender-one")},
    )
    _authenticate_as(client, user2)
    second_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user2, "sender-two")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_append_conversation_message_rate_limits_user_across_conversations(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 1
    _add_reply_capable_chat_keys(user, user2)
    first_conversation = _make_conversation(user, user2)
    second_conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    first_response = client.post(
        url_for("append_conversation_message", public_id=first_conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(first_conversation, user, "first-chat")},
    )
    second_response = client.post(
        url_for("append_conversation_message", public_id=second_conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(second_conversation, user, "second-chat")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 429


def test_append_conversation_message_rate_limits_conversation_bursts(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 20
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    first_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "first-burst")},
    )
    _authenticate_as(client, user2)
    second_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user2, "second-burst")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 429


def test_append_conversation_message_rate_limit_resets_after_window(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_WINDOW_SECONDS"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_WINDOW_SECONDS"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_WINDOW_SECONDS"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 20
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 20
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    first_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "old-window")},
    )
    db.session.execute(
        db.update(ChatRateLimitAttempt).values(
            created_at=datetime.now(timezone.utc) - timedelta(seconds=5)
        )
    )
    db.session.commit()
    second_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "new-window")},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_append_conversation_message_invalid_payload_does_not_burn_send_quota(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_PARTICIPANT_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_CONVERSATION_MAX"] = 1
    app.config["CONVERSATION_MESSAGE_RATE_LIMIT_USER_MAX"] = 1
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    invalid_copies = _reply_copies_for(conversation, user, "invalid-retry")
    recipient_participant = conversation.participant_for_user_id(user2.id)
    assert recipient_participant is not None
    invalid_copies[str(recipient_participant.id)] = "{}"

    invalid_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": invalid_copies},
    )
    corrected_response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "corrected-retry")},
    )

    assert invalid_response.status_code == 400
    assert corrected_response.status_code == 201
    attempt_count = db.session.scalar(db.select(db.func.count()).select_from(ChatRateLimitAttempt))
    assert attempt_count == 1


def test_chat_rate_limit_reservation_takes_postgres_advisory_locks(
    user: User,
    user2: User,
) -> None:
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory locks are only available with the PostgreSQL dialect.")

    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    participant = conversation.participant_for_user_id(user.id)
    assert participant is not None

    limited = _consume_conversation_message_rate_limit(
        thread=conversation,
        participant=participant,
        user=user,
    )

    advisory_lock_count = db.session.scalar(
        text(
            "SELECT count(*) "
            "FROM pg_locks "
            "WHERE locktype = 'advisory' "
            "AND pid = pg_backend_pid() "
            "AND granted"
        )
    )
    assert not limited
    assert advisory_lock_count is not None
    assert advisory_lock_count >= 3


def test_append_conversation_message_rejects_unsigned_legacy_envelopes(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _copies_for(conversation, "legacy-follow-up")},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_rejects_bogus_signature_before_persistence(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    encrypted_copies = _reply_copies_for(conversation, user, "bogus-signature")
    for recipient_participant_id, encrypted_payload in encrypted_copies.items():
        envelope = json.loads(encrypted_payload)
        envelope["signature"] = base64.b64encode(b"0" * 64).decode("ascii")
        encrypted_copies[recipient_participant_id] = json.dumps(envelope)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": encrypted_copies},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 1
    )
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessageCopy)
            .join(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 2
    )
    mock_send_email_to_user_recipients.assert_not_called()


def test_append_conversation_message_rejects_signature_from_other_participant_key(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={
            "encrypted_copies": _bound_copies_for(
                conversation,
                sender_participant,
                "wrong-signing-key",
                signing_private_key=_RECIPIENT_SIGNING_PRIVATE_KEY,
            )
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 1
    )


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_rejects_legacy_participant_with_bogus_signature(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(
        user2,
        '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}',
        public_signing_key='{"kty":"EC","crv":"P-256","x":"recipient-sign","y":"key"}',
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "bogus-signature")},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Conversation replies are unavailable."}
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 1
    )
    mock_send_email_to_user_recipients.assert_not_called()


def test_append_conversation_message_rejects_mismatched_bound_context(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    encrypted_copies = _bound_copies_for(conversation, sender_participant, "follow-up")
    first_recipient_id = next(iter(encrypted_copies))
    parsed_copy = json.loads(encrypted_copies[first_recipient_id])
    parsed_copy["context"]["recipient_participant_id"] = "999999"
    encrypted_copies[first_recipient_id] = json.dumps(parsed_copy)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": encrypted_copies},
    )

    assert response.status_code == 400
    assert "Invalid encrypted message payload." in response.text
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 1
    )


def test_participant_can_append_context_bound_conversation_message(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={
            "encrypted_copies": _bound_copies_for(
                conversation,
                sender_participant,
                "bound-follow-up",
            )
        },
    )

    assert response.status_code == 201
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 2
    )


def test_participant_can_append_legacy_context_bound_conversation_message(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={
            "encrypted_copies": _bound_copies_for(
                conversation,
                sender_participant,
                "legacy-bound-follow-up",
                use_legacy_conversation_id=True,
            )
        },
    )

    assert response.status_code == 201
    assert (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
        )
        == 2
    )


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_sends_generic_notification_to_other_participant(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user,
        email="sender@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "generic-notification")},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_called_once()
    notified_user, subject, body = mock_send_email_to_user_recipients.call_args.args
    assert notified_user.id == user2.id
    assert subject == "New Hush Line Conversation Activity"
    assert body == (
        "You have new Hush Line conversation activity. "
        "Log in and unlock your Hush Line chat key to read it."
    )
    assert all(
        call.args[0].id != user.id for call in mock_send_email_to_user_recipients.call_args_list
    )


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_suppresses_notification_for_active_recipient(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    recipient_participant = _participant_for(conversation, user2)
    recipient_participant.last_active_at = datetime.now(timezone.utc)
    db.session.commit()
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "active-recipient")},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_not_called()


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_suppresses_notification_for_active_recipients(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    target_conversation = _make_conversation(user, user2)
    active_conversation = _make_conversation(user, user2)
    active_participant = _participant_for(active_conversation, user2)
    active_participant.last_active_at = datetime.now(timezone.utc)
    db.session.commit()
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=target_conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(target_conversation, user, "active-recipient")},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_not_called()


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_notifies_after_stale_recipient_activity(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    recipient_participant = _participant_for(conversation, user2)
    recipient_participant.last_active_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.session.commit()
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "stale-recipient")},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_called_once()
    assert mock_send_email_to_user_recipients.call_args.args[0].id == user2.id


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_does_not_notify_sender(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user,
        email="sender@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "sender-notification")},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_not_called()


@patch("hushline.routes.message.encrypt_message")
@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_include_content_mode_still_sends_safe_generic_body(
    mock_send_email_to_user_recipients: MagicMock,
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=True,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    encrypted_copies = _reply_copies_for(conversation, user, "include-content")

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": encrypted_copies},
    )

    assert response.status_code == 201
    mock_send_email_to_user_recipients.assert_called_once()
    body = mock_send_email_to_user_recipients.call_args.args[2]
    assert body == (
        "You have new Hush Line conversation activity. "
        "Log in and unlock your Hush Line chat key to read it."
    )
    assert "ciphertext-include-content" not in body
    assert "ECDH-P256-AES-GCM" not in body
    mock_encrypt_message.assert_not_called()


@patch("hushline.routes.message.encrypt_message")
@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_encrypts_generic_body_for_full_body_mode(
    mock_send_email_to_user_recipients: MagicMock,
    mock_encrypt_message: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=True,
        encrypt_entire_body=True,
        pgp_key="recipient-notification-pgp-key",
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    encrypted_body = (
        "-----BEGIN PGP MESSAGE-----\n\nencrypted generic body\n-----END PGP MESSAGE-----"
    )
    mock_encrypt_message.return_value = encrypted_body

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "full-body")},
    )

    assert response.status_code == 201
    mock_encrypt_message.assert_called_once_with(
        (
            "You have new Hush Line conversation activity. "
            "Log in and unlock your Hush Line chat key to read it."
        ),
        "recipient-notification-pgp-key",
    )
    mock_send_email_to_user_recipients.assert_called_once()
    assert mock_send_email_to_user_recipients.call_args.args[2] == encrypted_body


@patch("hushline.routes.message.send_email_to_user_recipients")
def test_append_conversation_message_notification_failure_does_not_rollback_message(
    mock_send_email_to_user_recipients: MagicMock,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    _enable_conversation_notifications(
        user2,
        email="recipient@example.com",
        include_content=False,
        encrypt_entire_body=False,
    )
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    mock_send_email_to_user_recipients.side_effect = RuntimeError("smtp unavailable")

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "failed-notification")},
    )

    assert response.status_code == 201
    messages = db.session.scalars(
        db.select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.asc())
    ).all()
    assert len(messages) == 2
    assert messages[-1].sender_participant.user_id == user.id


def test_append_conversation_message_rejects_invalid_payload_without_leaking_content(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    leaked_content = "plaintext disclosure"

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={
            "encrypted_copies": {
                str(participant.id): leaked_content for participant in conversation.participants
            }
        },
    )

    assert response.status_code == 400
    assert "Invalid encrypted message payload." in response.text
    assert leaked_content not in response.text
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_requires_encrypted_copy_for_every_participant(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    participant = _participant_for(conversation, user)
    encrypted_copies = _reply_copies_for(conversation, user, "missing-recipient")
    encrypted_copies = {str(participant.id): encrypted_copies[str(participant.id)]}
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": encrypted_copies},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid encrypted message payload."}
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    copy_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessageCopy))
    assert message_count == 1
    assert copy_count == 2


def test_append_conversation_message_ignores_extra_plaintext_fields(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    plaintext = "plaintext reply must never be stored or rendered"
    _authenticate_as(client, user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={
            "body": plaintext,
            "message": plaintext,
            "plaintext": plaintext,
            "encrypted_copies": _reply_copies_for(conversation, user, "plaintext-extra-field"),
        },
    )

    assert response.status_code == 201
    messages = db.session.scalars(
        db.select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.id.asc())
    ).all()
    assert len(messages) == 2
    assert len(messages[-1].encrypted_copies) == 2
    assert plaintext not in response.text
    for encrypted_copy in messages[-1].encrypted_copies:
        assert "ECDH-P256-AES-GCM" in encrypted_copy.encrypted_payload
        assert plaintext not in encrypted_copy.encrypted_payload

    thread_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert thread_response.status_code == 200
    assert plaintext not in thread_response.text


def test_append_conversation_message_requires_csrf_when_enabled(
    app: Flask,
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, user)
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("append_conversation_message", public_id=conversation.public_id),
            json={"encrypted_copies": _reply_copies_for(conversation, user, "csrf")},
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_rejects_non_participant(
    client: FlaskClient,
    user: User,
    user2: User,
    admin_user: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)
    _authenticate_as(client, admin_user)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "unrelated")},
    )

    assert response.status_code == 404
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_append_conversation_message_redirects_unauthenticated_user(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    _add_reply_capable_chat_keys(user, user2)
    conversation = _make_conversation(user, user2)

    response = client.post(
        url_for("append_conversation_message", public_id=conversation.public_id),
        json={"encrypted_copies": _reply_copies_for(conversation, user, "unauthenticated")},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))
    message_count = db.session.scalar(db.select(db.func.count()).select_from(ConversationMessage))
    assert message_count == 1


def test_recipient_unread_indicator_clears_when_locked_thread_loads(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    initial_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _set_initial_message_created_at(conversation, initial_created_at)
    recipient_participant.last_read_at = initial_created_at
    db.session.commit()
    latest_message = _add_conversation_message(
        conversation,
        sender_participant,
        created_at=initial_created_at + timedelta(minutes=5),
        label="recipient-unread",
    )
    _authenticate_as(client, user2)

    unread_response = client.get(url_for("inbox"))

    assert unread_response.status_code == 200
    assert 'aria-label="Unread conversation"' in unread_response.text

    thread_response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert thread_response.status_code == 200
    assert "Messages are encrypted until your browser chat key unlocks." in thread_response.text
    db.session.refresh(recipient_participant)
    assert recipient_participant.last_read_at == latest_message.created_at
    assert recipient_participant.last_read_message_id == latest_message.id

    read_response = client.get(url_for("inbox"))
    assert read_response.status_code == 200
    assert 'aria-label="Unread conversation"' not in read_response.text


def test_background_thread_refresh_does_not_clear_inbox_unread_indicator(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    initial_message = conversation.messages[0]
    initial_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    initial_message.created_at = initial_created_at
    recipient_participant.last_read_at = initial_created_at
    recipient_participant.last_read_message = initial_message
    db.session.commit()
    latest_message = _add_conversation_message(
        conversation,
        sender_participant,
        created_at=initial_created_at + timedelta(minutes=5),
        label="background-refresh-unread",
    )
    _authenticate_as(client, user2)

    refresh_response = client.get(
        url_for("conversation", public_id=conversation.public_id),
        headers={"X-Hushline-Conversation-Refresh": "true"},
    )

    assert refresh_response.status_code == 200
    db.session.refresh(recipient_participant)
    assert recipient_participant.last_read_message_id == initial_message.id
    assert recipient_participant.last_read_message_id != latest_message.id

    inbox_response = client.get(url_for("inbox"))
    assert inbox_response.status_code == 200
    assert 'aria-label="Unread conversation"' in inbox_response.text

    thread_response = client.get(url_for("conversation", public_id=conversation.public_id))
    assert thread_response.status_code == 200
    db.session.refresh(recipient_participant)
    assert recipient_participant.last_read_message_id == latest_message.id


def test_inbox_unread_indicator_uses_message_cursor_when_timestamps_match(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    sender_participant = _participant_for(conversation, user)
    recipient_participant = _participant_for(conversation, user2)
    shared_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    initial_message = conversation.messages[0]
    initial_message.created_at = shared_created_at
    recipient_participant.last_read_at = shared_created_at
    recipient_participant.last_read_message = initial_message
    db.session.commit()
    _add_conversation_message(
        conversation,
        sender_participant,
        created_at=shared_created_at,
        label="same-timestamp-incoming",
    )
    _authenticate_as(client, user2)

    response = client.get(url_for("inbox"))

    assert response.status_code == 200
    assert 'aria-label="Unread conversation"' in response.text


def test_inbox_unread_indicator_uses_latest_message_for_each_participant(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_conversation(user, user2)
    user_participant = _participant_for(conversation, user)
    user2_participant = _participant_for(conversation, user2)
    initial_created_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _set_initial_message_created_at(conversation, initial_created_at)
    user_participant.last_read_at = initial_created_at
    user2_participant.last_read_at = initial_created_at
    db.session.commit()
    _add_conversation_message(
        conversation,
        user2_participant,
        created_at=initial_created_at + timedelta(minutes=5),
        label="incoming",
    )
    _add_conversation_message(
        conversation,
        user_participant,
        created_at=initial_created_at + timedelta(minutes=10),
        label="own-latest",
    )

    _authenticate_as(client, user)
    sender_response = client.get(url_for("inbox"))

    assert sender_response.status_code == 200
    assert 'aria-label="Unread conversation"' not in sender_response.text

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("inbox"))

    assert recipient_response.status_code == 200
    assert 'aria-label="Unread conversation"' in recipient_response.text

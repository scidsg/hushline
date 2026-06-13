import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_profile_submission_data
from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import MultipleResultsFound
from werkzeug.exceptions import NotFound

from hushline.db import db
from hushline.model import (
    AccountCategory,
    ChatKey,
    Conversation,
    ConversationMessageCopy,
    Message,
    NotificationRecipient,
    OrganizationSetting,
    StripeSubscriptionStatusEnum,
    User,
    Username,
)

msg_contact_method = "I prefer Signal."
msg_content = "This is a test message."
suspended_message = "This account is suspended. New messages cannot be sent at this time."

pgp_message_sig = "-----BEGIN PGP MESSAGE-----\n\n"
chat_message_algorithm = "ECDH-P256-AES-GCM"


def _set_pgp_key(user: User) -> None:
    user.pgp_key = Path("tests/test_pgp_key.txt").read_text()


def _add_chat_key(user: User, public_key: str) -> None:
    db.session.add(
        ChatKey(
            user=user,
            key_version=1,
            public_key=public_key,
            encrypted_private_key="wrapped-private-chat-key",
            kdf_algorithm="PBKDF2-SHA-256",
            kdf_params={"iterations": 310000, "hash": "SHA-256"},
            kdf_salt="salt",
            wrapping_algorithm="AES-GCM",
        )
    )


def _chat_ciphertext(label: str) -> str:
    return json.dumps(
        {
            "algorithm": chat_message_algorithm,
            "ephemeral_public_key": '{"kty":"EC","crv":"P-256","x":"ephemeral","y":"key"}',
            "iv": f"iv-{label}",
            "ciphertext": f"ciphertext-{label}",
        }
    )


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True


def _make_current_paid_super_user(user: User) -> None:
    user.set_business_tier()
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE


def _enable_embeds_globally() -> None:
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)


def _configure_embed(username: Username, origin: str = "https://tips.example") -> None:
    username.embed_enabled = True
    username.set_embed_allowed_origins([origin])


def _embed_post_headers(**extra_headers: str) -> dict[str, str]:
    return {"Origin": "http://localhost:8080", **extra_headers}


def _embed_submission_data(response_text: str) -> dict[str, str]:
    page = BeautifulSoup(response_text, "html.parser")
    label = page.find("label", attrs={"for": "captcha_answer"})
    assert label is not None
    left, right = label.get_text(strip=True).replace("=", "").split("+")

    data = {"captcha_answer": str(int(left.strip()) + int(right.strip()))}
    for name in ["owner_guard_nonce", "owner_guard_signature", "embed_captcha_token"]:
        field = page.find("input", attrs={"name": name})
        assert field is not None
        value = field.get("value")
        assert value
        data[name] = str(value)
    data["csrf_token"] = data["embed_captcha_token"]
    return data


@pytest.mark.usefixtures("_pgp_user")
def test_profile_header(client: FlaskClient, user: User) -> None:
    assert (
        db.session.scalars(
            db.select(OrganizationSetting).filter_by(
                key=OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE
            )
        ).one_or_none()
        is None
    )  # precondition

    resp = client.get(url_for("profile", username=user.primary_username.username))
    assert resp.status_code == 200
    assert (
        "Submit a message to "
        + (user.primary_username.display_name or user.primary_username.username)
        in resp.text
    )

    rand = str(uuid4())
    template = rand + " {{ display_name_or_username }} {{ username }} {{ display_name }}"
    OrganizationSetting.upsert(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE, template)
    db.session.commit()

    expected = (
        f"{rand} {user.primary_username.display_name or user.primary_username.username} "
        f"{user.primary_username.username} {user.primary_username.display_name or ''}"
    )
    resp = client.get(url_for("profile", username=user.primary_username.username))
    assert resp.status_code == 200
    assert expected in resp.text


def test_profile_accepts_case_insensitive_username(
    client: FlaskClient, user_alias: Username
) -> None:
    alt_username = user_alias.username.upper()
    response = client.get(url_for("profile", username=alt_username))
    assert response.status_code == 200
    assert user_alias.username in response.text


@pytest.mark.parametrize("display_name", ["Admin of Hush Line", "Ｈｕｓｈ Ｌｉｎｅ"])
def test_profile_shows_caution_badge_for_suspicious_non_admin_display_name(
    client: FlaskClient, user: User, display_name: str
) -> None:
    user.primary_username.display_name = display_name
    user.primary_username.is_verified = False
    user.is_admin = False
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    caution_badge = soup.select_one(
        'span.badge.badgeCaution[aria-label="Caution: display name may be mistaken for admin"]'
    )
    assert caution_badge is not None
    trigger = soup.select_one('button.badgeHelpTrigger[aria-describedby="caution-badge-info"]')
    assert trigger is not None
    assert trigger.get_text(strip=True) == "What's this?"
    tooltip = soup.select_one("span#caution-badge-info[role='tooltip']")
    assert tooltip is not None
    assert (
        tooltip.get_text(strip=True)
        == "Visitors should be cautious of interacting with this account."
    )


def test_profile_shows_caution_badge_for_suspicious_username_when_display_name_missing(
    client: FlaskClient, user: User
) -> None:
    user.primary_username.username = "admin"
    user.primary_username.display_name = None
    user.primary_username.is_verified = False
    user.is_admin = False
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    assert (
        soup.select_one(
            'span.badge.badgeCaution[aria-label="Caution: display name may be mistaken for admin"]'
        )
        is not None
    )
    assert (
        soup.select_one('button.badgeHelpTrigger[aria-describedby="caution-badge-info"]')
        is not None
    )


def test_profile_404_for_unknown_username(client: FlaskClient) -> None:
    response = client.get(url_for("profile", username="does-not-exist"), follow_redirects=True)
    assert response.status_code == 404
    assert "404: Not Found" in response.text


def test_profile_404s_when_case_insensitive_lookup_is_ambiguous(app: Flask) -> None:
    with (
        patch(
            "hushline.routes.profile.db.session.scalars",
            return_value=MagicMock(
                one_or_none=MagicMock(side_effect=MultipleResultsFound),
            ),
        ),
        app.test_request_context("/to/CaseUser"),
        pytest.raises(NotFound),
    ):
        app.view_functions["profile"]("CaseUser")


@pytest.mark.usefixtures("_pgp_user")
def test_profile_does_not_expose_owner_user_id(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    assert soup.find("input", attrs={"name": "username_user_id"}) is None
    assert soup.find("input", attrs={"name": "encrypted_email_body", "type": "hidden"}) is not None
    assert soup.find("script", attrs={"id": "recipientPublicKeys", "type": "application/json"})
    assert soup.find("input", attrs={"id": "publicKey"}) is None

    nonce_input = soup.find("input", attrs={"name": "owner_guard_nonce"})
    signature_input = soup.find("input", attrs={"name": "owner_guard_signature"})
    captcha_input = soup.find("input", attrs={"name": "captcha_answer", "id": "captcha_answer"})
    assert nonce_input is not None
    assert signature_input is not None
    assert captcha_input is not None
    assert nonce_input.get("value")
    assert signature_input.get("value")
    assert captcha_input.get("value") in (None, "")


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_submit_message(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_pgp_user")
def test_anonymous_profile_submit_message_keeps_reply_success_flow(
    client: FlaskClient, user: User
) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text
    assert "Reply Address" in response.text
    assert "/conversation/" not in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert message.conversation is None
    assert db.session.scalars(db.select(Conversation)).all() == []
    assert db.session.scalars(db.select(ConversationMessageCopy)).all() == []

    _authenticate_as(client, user)
    inbox_response = client.get(url_for("inbox"))
    assert inbox_response.status_code == 200
    assert f'href="{url_for("message", public_id=message.public_id)}"' in inbox_response.text
    assert 'id="conversation-list-heading"' not in inbox_response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_logged_in_profile_submit_message_creates_conversation_for_distinct_recipient(
    client: FlaskClient, user: User, user2: User, admin_user: User
) -> None:
    _set_pgp_key(user)
    _set_pgp_key(user2)
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    db.session.commit()

    response = client.post(
        url_for("profile", username=user2.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_conversation_copies": json.dumps(
                {
                    "sender": _chat_ciphertext("sender-initial"),
                    "recipient": _chat_ciphertext("recipient-initial"),
                }
            ),
            **get_profile_submission_data(client, user2.primary_username.username),
        },
        follow_redirects=False,
    )

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user2.primary_username.id)
    ).one()
    conversation = message.conversation
    assert conversation is not None
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        url_for("conversation", conversation_id=conversation.id)
    )
    assert {participant.user_id for participant in conversation.participants} == {
        user.id,
        user2.id,
    }
    participants_by_user_id = {
        participant.user_id: participant for participant in conversation.participants
    }
    assert participants_by_user_id[user.id].has_usable_public_key is True
    assert participants_by_user_id[user2.id].has_usable_public_key is True
    [conversation_message] = conversation.messages
    assert conversation_message.sender_participant.user_id == user.id
    assert len(conversation_message.encrypted_copies) == 2
    for encrypted_copy in conversation_message.encrypted_copies:
        assert chat_message_algorithm in encrypted_copy.encrypted_payload
        assert msg_contact_method not in encrypted_copy.encrypted_payload
        assert msg_content not in encrypted_copy.encrypted_payload
        assert "wrapped-private-chat-key" not in encrypted_copy.encrypted_payload

    sender_response = client.get(
        url_for("conversation", conversation_id=conversation.id), follow_redirects=True
    )
    assert sender_response.status_code == 200
    assert "Unlock your Hush Line chat key" in sender_response.text
    assert "Locked message. Unlock chat to read." in sender_response.text

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert recipient_response.status_code == 200
    assert "Unlock your Hush Line chat key" in recipient_response.text
    assert "Locked message. Unlock chat to read." in recipient_response.text
    message_response = client.get(url_for("message", public_id=message.public_id))
    assert url_for("conversation", conversation_id=conversation.id) in message_response.text

    _authenticate_as(client, admin_user)
    other_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert other_response.status_code == 404


@pytest.mark.usefixtures("_authenticated_user")
def test_logged_in_profile_submit_message_creates_conversation_without_sender_key(
    client: FlaskClient, user: User, user2: User
) -> None:
    _set_pgp_key(user2)
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    db.session.commit()

    response = client.post(
        url_for("profile", username=user2.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_conversation_copies": json.dumps(
                {"recipient": _chat_ciphertext("recipient-initial")}
            ),
            **get_profile_submission_data(client, user2.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "No encrypted copy is available for your account." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user2.primary_username.id)
    ).one()
    conversation = message.conversation
    assert conversation is not None
    assert {participant.user_id for participant in conversation.participants} == {
        user.id,
        user2.id,
    }
    participants_by_user_id = {
        participant.user_id: participant for participant in conversation.participants
    }
    assert participants_by_user_id[user.id].has_usable_public_key is False
    assert participants_by_user_id[user2.id].has_usable_public_key is True
    copies = db.session.scalars(db.select(ConversationMessageCopy)).all()
    assert len(copies) == 1
    assert copies[0].recipient_participant.user_id == user2.id
    assert chat_message_algorithm in copies[0].encrypted_payload
    assert msg_contact_method not in copies[0].encrypted_payload
    assert msg_content not in copies[0].encrypted_payload

    _authenticate_as(client, user2)
    recipient_response = client.get(url_for("conversation", conversation_id=conversation.id))
    assert recipient_response.status_code == 200
    assert "Unlock your Hush Line chat key" in recipient_response.text
    assert "Locked message. Unlock chat to read." in recipient_response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_logged_in_profile_submit_message_with_invalid_chat_ciphertext_skips_conversation(
    client: FlaskClient, user: User, user2: User
) -> None:
    _set_pgp_key(user)
    _set_pgp_key(user2)
    _add_chat_key(user, '{"kty":"EC","crv":"P-256","x":"sender","y":"key"}')
    _add_chat_key(user2, '{"kty":"EC","crv":"P-256","x":"recipient","y":"key"}')
    db.session.commit()

    response = client.post(
        url_for("profile", username=user2.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_conversation_copies": json.dumps(
                {
                    "recipient": msg_content,
                    "private_key": "plain-private-key",
                    "derived_wrapping_key": "plain-derived-key",
                }
            ),
            **get_profile_submission_data(client, user2.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text
    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user2.primary_username.id)
    ).one()
    assert message.conversation is None
    assert db.session.scalars(db.select(Conversation)).all() == []
    assert db.session.scalars(db.select(ConversationMessageCopy)).all() == []
    assert "plain-private-key" not in response.text
    assert "plain-derived-key" not in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_self_profile_submit_message_keeps_reply_success_flow(
    client: FlaskClient, user: User
) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Reply Address" in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert message.conversation is None
    assert db.session.scalars(db.select(Conversation)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
def test_logged_in_profile_submit_message_requires_recipient_encryption_target(
    client: FlaskClient, user2: User
) -> None:
    response = client.post(
        url_for("profile", username=user2.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user2.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "do not have any usable recipient PGP keys" in response.text
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user2.primary_username.id)
        ).first()
        is None
    )
    assert db.session.scalars(db.select(Conversation)).all() == []


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_submit_message_to_alias(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    response = client.post(
        url_for("profile", username=user_alias.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user_alias.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(db.select(Message).filter_by(username_id=user_alias.id)).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in field_value.value

    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200
    assert pgp_message_sig in response.text, response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_failed_submit_preserves_input(client: FlaskClient, user: User) -> None:
    username = user.primary_username.username
    submission_data = get_profile_submission_data(client, username)
    submission_data["captcha_answer"] = "0"

    response = client.post(
        url_for("profile", username=username),
        data={
            "field_0": "Contact info preserved",
            "field_1": "Message preserved",
            **submission_data,
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "Invalid CAPTCHA answer" in response.text
    assert "Contact info preserved" in response.text
    assert "Message preserved" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_rejects_owner_guard_mismatch(client: FlaskClient, user: User) -> None:
    username = user.primary_username.username
    submission_data = get_profile_submission_data(client, username)
    submission_data["owner_guard_signature"] = "tampered-signature"

    response = client.post(
        url_for("profile", username=username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **submission_data,
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "tip line changed" in response.text


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_non_numeric_captcha(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)
    submission_data["captcha_answer"] = "abc"

    response = client.post(
        url_for("embed_profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **submission_data,
        },
        headers=_embed_post_headers(),
    )

    assert response.status_code == 400
    assert "Invalid CAPTCHA answer" in response.text


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_expired_captcha_token(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)

    with patch(
        "hushline.routes.profile.URLSafeTimedSerializer.loads",
        side_effect=SignatureExpired("expired"),
    ):
        response = client.post(
            url_for("embed_profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **submission_data,
            },
            headers=_embed_post_headers(),
        )

    assert response.status_code == 400
    assert "CAPTCHA expired" in response.text


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_bad_captcha_token(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)

    with patch(
        "hushline.routes.profile.URLSafeTimedSerializer.loads",
        side_effect=BadData("bad token"),
    ):
        response = client.post(
            url_for("embed_profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **submission_data,
            },
            headers=_embed_post_headers(),
        )

    assert response.status_code == 400
    assert "Incorrect CAPTCHA" in response.text


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_captcha_token_for_different_profile(
    app: Flask, client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)
    bad_token = URLSafeTimedSerializer(app.secret_key or "", salt="embed-profile-captcha").dumps(
        {
            "v": 1,
            "username": "different-user",
            "user_id": user.id,
            "nonce": "nonce",
            "math_problem": "1 + 1 =",
            "answer_signature": "not-checked-before-profile-mismatch",
        }
    )
    submission_data["captcha_answer"] = "2"
    submission_data["embed_captcha_token"] = bad_token
    submission_data["csrf_token"] = bad_token

    response = client.post(
        url_for("embed_profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **submission_data,
        },
        headers=_embed_post_headers(),
    )

    assert response.status_code == 400
    assert "Incorrect CAPTCHA" in response.text


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_post_404s_if_account_is_suspended_after_render(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)

    def suspend_after_embed_eligibility_check(*_args: object, **_kwargs: object) -> str:
        user.is_suspended = True
        return "Submit a message"

    with patch(
        "hushline.routes.profile.safe_render_template",
        side_effect=suspend_after_embed_eligibility_check,
    ):
        response = client.post(
            url_for("embed_profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **submission_data,
            },
            headers=_embed_post_headers(),
        )

    assert response.status_code == 404
    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert "frame-ancestors 'none'" in csp


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_if_account_is_suspended_during_submission(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)
    rate_limit_result = MagicMock(
        limited=False,
        profile_hash="profile-hash",
        source_bucket_hash="source-bucket-hash",
    )

    def suspend_after_initial_block_check(_username: Username) -> MagicMock:
        user.is_suspended = True
        return rate_limit_result

    with (
        patch(
            "hushline.routes.profile.check_embed_rate_limit",
            side_effect=suspend_after_initial_block_check,
        ),
        patch("hushline.routes.profile.emit_embed_abuse_counter") as emit_counter,
    ):
        response = client.post(
            url_for("embed_profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **submission_data,
            },
            headers=_embed_post_headers(),
        )

    assert response.status_code == 400
    assert suspended_message in response.text
    assert any(call.kwargs.get("reason") == "suspended" for call in emit_counter.call_args_list)
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).first()
        is None
    )


@pytest.mark.usefixtures("_pgp_user")
def test_embed_profile_rejects_if_recipient_keys_are_removed_during_submission(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_current_paid_super_user(user)
    _configure_embed(user.primary_username)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)
    rate_limit_result = MagicMock(
        limited=False,
        profile_hash="profile-hash",
        source_bucket_hash="source-bucket-hash",
    )

    def remove_keys_after_initial_block_check(_username: Username) -> MagicMock:
        user.pgp_key = None
        for recipient in user.notification_recipients:
            recipient.pgp_key = None
        return rate_limit_result

    with (
        patch(
            "hushline.routes.profile.check_embed_rate_limit",
            side_effect=remove_keys_after_initial_block_check,
        ),
        patch("hushline.routes.profile.emit_embed_abuse_counter") as emit_counter,
    ):
        response = client.post(
            url_for("embed_profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **submission_data,
            },
            headers=_embed_post_headers(),
        )

    assert response.status_code == 400
    assert "do not have any usable recipient PGP keys" in response.text
    assert any(
        call.kwargs.get("reason") == "missing_recipient_keys"
        for call in emit_counter.call_args_list
    )
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).first()
        is None
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_pgp_required(client: FlaskClient, app: Flask, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    assert 'id="messageForm"' in response.text
    assert 'data-submit-spinner="true"' in response.text
    assert "You can't send encrypted messages to this user through Hush Line" not in response.text

    user.pgp_key = None
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_allows_submission_with_recipient_key_when_legacy_user_key_missing(
    client: FlaskClient, user: User
) -> None:
    user.pgp_key = None
    user.notification_recipients.append(NotificationRecipient(position=1, enabled=True))
    user.notification_recipients[-1].email = "secondary@example.com"
    user.notification_recipients[-1].pgp_key = Path("tests/test_pgp_key.txt").read_text()
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" not in response.text

    soup = BeautifulSoup(response.data, "html.parser")
    recipient_keys = soup.find("script", attrs={"id": "recipientPublicKeys"})
    assert recipient_keys is not None
    assert "BEGIN PGP PUBLIC KEY BLOCK" in recipient_keys.get_text()


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_allows_submission_with_legacy_key_when_primary_recipient_lacks_key(
    client: FlaskClient, user: User
) -> None:
    pgp_key = Path("tests/test_pgp_key.txt").read_text()
    user.email = "primary@example.com"
    user.pgp_key = pgp_key
    primary_recipient = user.primary_notification_recipient
    assert primary_recipient is not None
    primary_recipient.pgp_key = None
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" not in response.text

    soup = BeautifulSoup(response.data, "html.parser")
    recipient_keys = soup.find("script", attrs={"id": "recipientPublicKeys"})
    assert recipient_keys is not None
    assert "BEGIN PGP PUBLIC KEY BLOCK" in recipient_keys.get_text()


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message_with_recipient_key_when_legacy_user_key_missing(
    client: FlaskClient, user: User
) -> None:
    user.pgp_key = None
    user.notification_recipients.append(NotificationRecipient(position=1, enabled=True))
    user.notification_recipients[-1].email = "secondary@example.com"
    user.notification_recipients[-1].pgp_key = Path("tests/test_pgp_key.txt").read_text()
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text

    message = db.session.scalars(
        db.select(Message).filter_by(username_id=user.primary_username.id)
    ).one()
    assert len(message.field_values) == 2
    for field_value in message.field_values:
        assert pgp_message_sig in (field_value.value or "")


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_submit_message_ignores_enabled_recipient_without_key(
    client: FlaskClient, user: User
) -> None:
    user.pgp_key = None
    user.notification_recipients.append(NotificationRecipient(position=1, enabled=True))
    user.notification_recipients[-1].email = "secondary@example.com"
    user.notification_recipients[-1].pgp_key = Path("tests/test_pgp_key.txt").read_text()
    user.notification_recipients.append(NotificationRecipient(position=2, enabled=True))
    user.notification_recipients[-1].email = "tertiary@example.com"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert "Sending messages is disabled" not in response.text

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, response.text
    assert "Message submitted successfully." in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_suspended_state_disables_message_form_with_pgp_key(
    client: FlaskClient, user: User
) -> None:
    user.is_suspended = True
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200
    assert suspended_message in response.text
    assert 'id="submitBtn"' in response.text
    assert 'disabled="disabled"' in response.text
    assert "/static/js/submit-message.js" not in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_post_rejects_when_target_has_no_pgp_key(client: FlaskClient, user: User) -> None:
    user.pgp_key = None
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "do not have any usable recipient PGP keys" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_post_rejects_when_target_is_suspended(client: FlaskClient, user: User) -> None:
    user.is_suspended = True
    db.session.commit()

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert suspended_message in response.text
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).first()
        is None
    )


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_post_rejects_alias_when_owner_is_suspended(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    user.is_suspended = True
    db.session.commit()

    response = client.post(
        url_for("profile", username=user_alias.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user_alias.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert suspended_message in response.text
    assert (
        db.session.scalars(db.select(Message).filter_by(username_id=user_alias.id)).first() is None
    )


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_post_form_validation_errors_are_rendered(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": "",
            "field_1": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "There was an error submitting your message" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_requires_csrf_token(app: Flask, client: FlaskClient, user: User) -> None:
    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("profile", username=user.primary_username.username),
            data={
                "field_0": msg_contact_method,
                "field_1": msg_content,
                **get_profile_submission_data(client, user.primary_username.username),
            },
            follow_redirects=False,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior

    assert response.status_code == 400
    assert (
        db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).first()
        is None
    )


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_full_body_encryption_fallback_to_generic_when_no_fields(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    for field_def in user.primary_username.message_fields:
        field_def.enabled = False
    db.session.commit()

    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "encrypted_email_body": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    assert sent == ["You have a new Hush Line message! Please log in to read it."]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.routes.profile.encrypt_message", side_effect=ValueError("boom"))
def test_profile_full_body_encryption_exception_falls_back_to_generic(
    encrypt_message_mock: MagicMock,
    client: FlaskClient,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = encrypt_message_mock
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_email_body": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    assert sent == ["You have a new Hush Line message! Please log in to read it."]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_full_body_encryption_uses_server_fallback_when_client_body_missing(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    sent: list[str] = []
    encrypt_message = MagicMock(return_value="encrypted fallback body")

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.encrypt_message", encrypt_message)
    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            "encrypted_email_body": "",
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Message submitted successfully." in response.text
    assert sent == ["encrypted fallback body"]
    encrypted_plaintext = encrypt_message.call_args.args[0]
    assert "Contact Method" in encrypted_plaintext
    assert msg_content in encrypted_plaintext


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_notification_without_message_content_sends_generic_body(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = False
    db.session.commit()
    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert sent == ["You have a new Hush Line message! Please log in to read it."]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_single_recipient_notification_can_include_stored_message_content(
    client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    db.session.commit()
    sent: list[str] = []

    def fake_send_email(_user: User, body: str) -> None:
        sent.append(body)

    monkeypatch.setattr("hushline.routes.profile.do_send_email", fake_send_email)

    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data={
            "field_0": msg_contact_method,
            "field_1": msg_content,
            **get_profile_submission_data(client, user.primary_username.username),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(sent) == 1
    assert "Contact Method" in sent[0]
    assert "Message" in sent[0]
    assert pgp_message_sig in sent[0]


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_extra_fields(client: FlaskClient, app: Flask, user: User) -> None:
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    user.primary_username.extra_field_label2 = "Arbitrary Link"
    user.primary_username.extra_field_value2 = "https://scidsg.org/"
    user.primary_username.extra_field_label3 = "xss should fail"
    user.primary_username.extra_field_value3 = "<script>alert('xss')</script>"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    signal_username_span = soup.find("span", class_="extra-field-value")
    assert signal_username_span is not None
    assert signal_username_span.text.strip() == "singleusername.666"

    link = soup.find("a", href="https://scidsg.org/")
    assert link is not None
    assert link.get("target") == "_blank"
    assert "noopener" in link.get("rel", [])
    assert "noreferrer" in link.get("rel", [])

    # Verify that XSS is correctly escaped
    # Search for the XSS string directly in the HTML with both possible escapes
    html_str = str(soup)
    assert (
        "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in html_str
        or "&lt;script&gt;alert('xss')&lt;/script&gt;" in html_str
    )
    assert "<script>alert('xss')</script>" not in html_str


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_profile_field_encryption_labels(client: FlaskClient, user: User) -> None:
    user.primary_username.message_fields[0].encrypted = False
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    meta_labels = [node.get_text(" ", strip=True) for node in soup.select(".field-group p.meta")]
    assert "⚠️ Not Encrypted. Learn why." in meta_labels
    assert "🔒 Encrypted" in meta_labels

    learn_why_link = soup.find(
        "a",
        string="Learn why.",
        href="https://hushline.app/library/docs/getting-started/account-setup/",
    )
    assert learn_why_link is not None
    assert learn_why_link.get("target") == "_blank"
    assert "noopener" in learn_why_link.get("rel", [])
    assert "noreferrer" in learn_why_link.get("rel", [])


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_account_category_renders_first_extra_field(
    client: FlaskClient, user: User
) -> None:
    user.account_category = AccountCategory.LAWYER.value
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    user.primary_username.extra_field_label2 = "Website"
    user.primary_username.extra_field_value2 = "https://scidsg.org/"
    user.primary_username.extra_field_label3 = "Pronouns"
    user.primary_username.extra_field_value3 = "they/them"
    user.primary_username.extra_field_label4 = "Timezone"
    user.primary_username.extra_field_value4 = "UTC"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Category", "Signal username", "Website", "Pronouns", "Timezone"]
    assert values[0] == "Attorney"


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_location_renders_as_single_extra_field(client: FlaskClient, user: User) -> None:
    user.country = "US"
    user.subdivision = "IL"
    user.city = "Chicago"
    user.primary_username.extra_field_label1 = "Signal username"
    user.primary_username.extra_field_value1 = "singleusername.666"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Location", "Signal username"]
    assert values[0] == "Chicago, IL, US"


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_location_keeps_full_names_outside_us(client: FlaskClient, user: User) -> None:
    user.country = "Australia"
    user.subdivision = "New South Wales"
    user.city = "Sydney"
    db.session.commit()

    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    labels = [node.get_text(strip=True) for node in soup.select(".extra-field-label")]
    values = [node.get_text(" ", strip=True) for node in soup.select(".extra-field-value")]
    assert labels == ["Location"]
    assert values[0] == "Sydney, New South Wales, Australia"


def test_redirect_submit_message_route(client: FlaskClient, user: User) -> None:
    response = client.get(
        url_for("redirect_submit_message", username=user.primary_username.username),
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["Location"].endswith(
        url_for("profile", username=user.primary_username.username)
    )


def test_submission_success_without_reply_slug_redirects_directory(client: FlaskClient) -> None:
    response = client.get(url_for("submission_success"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("directory"))


def test_submission_success_404_when_message_missing(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["reply_slug"] = "does-not-exist"

    response = client.get(url_for("submission_success"), follow_redirects=True)
    assert response.status_code == 404
    assert "404: Not Found" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
def test_submission_success_uses_public_base_url_for_reply_link(app: Flask, user: User) -> None:
    app.config["SERVER_NAME"] = None
    app.config["PUBLIC_BASE_URL"] = "https://safe.example"
    message = Message(username_id=user.primary_username.id)
    db.session.add(message)
    db.session.commit()

    with app.test_request_context(
        url_for("submission_success"),
        base_url="http://evil.example",
    ):
        from flask import session

        session["reply_slug"] = message.reply_slug
        response = app.view_functions["submission_success"]()

    assert isinstance(response, str)
    assert f'href="https://safe.example/reply/{message.reply_slug}"' in response
    assert "evil.example" not in response

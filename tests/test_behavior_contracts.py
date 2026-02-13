from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session, get_captcha_from_session_register

from hushline.db import db
from hushline.model import (
    InviteCode,
    Message,
    MessageStatus,
    OrganizationSetting,
    Tier,
    User,
    Username,
)
from hushline.routes.common import format_full_message_email_body
from hushline.settings import (
    ChangePasswordForm,
    ChangeUsernameForm,
    DisplayNameForm,
    NewAliasForm,
    PGPKeyForm,
)
from hushline.settings.branding import ToggleDonateButtonForm
from hushline.settings.forms import (
    SetHomepageUsernameForm,
    UpdateBrandAppNameForm,
    UpdateBrandPrimaryColorForm,
    UpdateDirectoryTextForm,
    UpdateProfileHeaderForm,
    UserGuidanceForm,
)
from tests.helpers import form_to_data

GENERIC_EMAIL_BODY = "You have a new Hush Line message! Please log in to read it."
PGP_SIG = "-----BEGIN PGP MESSAGE-----"


def _submit_message(client: FlaskClient, user: User, encrypted_email_body: str = "") -> None:
    data = {
        "field_0": "Signal",
        "field_1": "Contract test message",
        "username_user_id": user.id,
        "captcha_answer": get_captcha_from_session(client, user.primary_username.username),
    }
    if encrypted_email_body:
        data["encrypted_email_body"] = encrypted_email_body
    response = client.post(
        url_for("profile", username=user.primary_username.username),
        data=data,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Message submitted successfully." in response.text


def _latest_message_for(user: User) -> Message:
    message = db.session.scalars(
        db.select(Message)
        .filter_by(username_id=user.primary_username.id)
        .order_by(Message.created_at.desc())
    ).first()
    assert message is not None
    return message


def _authenticate_as(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = True


def test_contract_register_login_and_2fa_challenge(client: FlaskClient, app: Flask) -> None:
    app.config["STRIPE_SECRET_KEY"] = ""
    username = f"contract-{uuid.uuid4().hex[:8]}"
    password = "SecurePassword123!"
    captcha_answer = get_captcha_from_session_register(client)

    register_response = client.post(
        url_for("register"),
        data={"username": username, "password": password, "captcha_answer": captcha_answer},
        follow_redirects=True,
    )
    assert register_response.status_code == 200
    assert "Registration successful!" in register_response.text

    created_username = db.session.scalars(
        db.select(Username).where(Username._username == username)
    ).one()
    created_user = db.session.get(User, created_username.user_id)
    assert created_user is not None
    created_user.onboarding_complete = True
    created_user.tier_id = 1
    created_user.totp_secret = pyotp.random_base32()
    db.session.commit()

    login_response = client.post(
        url_for("login"),
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Enter your 2FA Code" in login_response.text

    verify_response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": pyotp.TOTP(created_user.totp_secret).now()},
        follow_redirects=True,
    )
    assert verify_response.status_code == 200
    assert "Inbox" in verify_response.text


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_notifications_generic_mode(client: FlaskClient, user: User) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = False
    user.email_encrypt_entire_body = False
    db.session.commit()

    with patch("hushline.routes.profile.do_send_email", new=MagicMock()) as send_email_mock:
        _submit_message(client, user)
        send_email_mock.assert_called_once_with(user, GENERIC_EMAIL_BODY)

    message = _latest_message_for(user)
    assert message.field_values
    for value in message.field_values:
        assert PGP_SIG in (value.value or "")


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_notifications_field_content_mode(client: FlaskClient, user: User) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = False
    db.session.commit()

    with patch("hushline.routes.profile.do_send_email", new=MagicMock()) as send_email_mock:
        _submit_message(client, user)
        send_email_mock.assert_called_once()
        _, body = send_email_mock.call_args.args
        assert "Contact Method" in body
        assert "Message" in body
        assert PGP_SIG in body


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_notifications_full_body_mode_prefers_client_encrypted_body(
    client: FlaskClient, user: User
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    client_body = (
        "-----BEGIN PGP MESSAGE-----\n\nclient encrypted body\n\n-----END PGP MESSAGE-----"
    )
    with (
        patch("hushline.routes.profile.do_send_email", new=MagicMock()) as send_email_mock,
        patch("hushline.routes.profile.encrypt_message", new=MagicMock()) as encrypt_mock,
    ):
        _submit_message(client, user, encrypted_email_body=client_body)
        send_email_mock.assert_called_once_with(user, client_body)
        encrypt_mock.assert_not_called()


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_notifications_full_body_mode_falls_back_to_server_encrypt(
    client: FlaskClient, user: User
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    db.session.commit()

    server_body = (
        "-----BEGIN PGP MESSAGE-----\n\nserver encrypted body\n\n-----END PGP MESSAGE-----"
    )
    with (
        patch("hushline.routes.profile.do_send_email", new=MagicMock()) as send_email_mock,
        patch(
            "hushline.routes.profile.encrypt_message", new=MagicMock(return_value=server_body)
        ) as encrypt_mock,
    ):
        _submit_message(client, user, encrypted_email_body="")
        expected_plaintext_body = format_full_message_email_body(
            [("Contact Method", "Signal"), ("Message", "Contract test message")]
        )
        encrypt_mock.assert_called_once_with(expected_plaintext_body, user.pgp_key)
        send_email_mock.assert_called_once_with(user, server_body)


@pytest.mark.usefixtures("_authenticated_user")
def test_contract_2fa_enable_then_disable_round_trip(client: FlaskClient, user: User) -> None:
    assert user.totp_secret is None

    response = client.post(url_for("settings.toggle_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.enable_2fa"))

    response = client.get(url_for("settings.enable_2fa"), follow_redirects=False)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        temp_totp_secret = str(sess["temp_totp_secret"])
    verification_code = pyotp.TOTP(temp_totp_secret).now()

    response = client.post(
        url_for("settings.enable_2fa"),
        data={"verification_code": verification_code},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("logout"))

    db.session.refresh(user)
    assert user.totp_secret is not None

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.primary_username.username
        sess["is_authenticated"] = True

    response = client.get(url_for("settings.auth"), follow_redirects=True)
    assert response.status_code == 200
    assert "Disable 2FA" in response.text

    response = client.post(url_for("settings.disable_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.auth"))
    db.session.refresh(user)
    assert user.totp_secret is None


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_onboarding_notifications_and_directory_persist_expected_state(
    client: FlaskClient, user: User
) -> None:
    user.onboarding_complete = False
    user.enable_email_notifications = False
    user.email_include_message_content = False
    user.email_encrypt_entire_body = False
    user.email = None
    user.primary_username.show_in_directory = False
    db.session.commit()

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "contracts@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding", step="directory"))
    db.session.refresh(user)
    assert user.enable_email_notifications is True
    assert user.email_include_message_content is True
    assert user.email_encrypt_entire_body is True
    assert user.email == "contracts@example.com"

    response = client.post(
        url_for("onboarding"),
        data={"step": "directory", "show_in_directory": "y"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))
    db.session.refresh(user)
    assert user.onboarding_complete is True
    assert user.primary_username.show_in_directory is True


def test_contract_directory_users_surface_verified_and_unverified_accounts(
    client: FlaskClient, user: User, user2: User
) -> None:
    user.primary_username.show_in_directory = True
    user.primary_username.is_verified = True
    user.primary_username._display_name = "Verified Sender"
    user.primary_username.bio = "verified bio"

    user2.primary_username.show_in_directory = True
    user2.primary_username.is_verified = False
    user2.primary_username._display_name = None
    user2.primary_username.bio = "unverified bio"
    db.session.commit()

    response = client.get(url_for("directory_users"))
    assert response.status_code == 200
    rows = response.json or []

    verified_row = next(
        row for row in rows if row["primary_username"] == user.primary_username.username
    )
    unverified_row = next(
        row for row in rows if row["primary_username"] == user2.primary_username.username
    )

    assert verified_row["is_verified"] is True
    assert verified_row["display_name"] == "Verified Sender"
    assert verified_row["bio"] == "verified bio"
    assert unverified_row["is_verified"] is False
    assert unverified_row["display_name"] == user2.primary_username.username
    assert unverified_row["bio"] == "unverified bio"


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_whistleblower_message_flow_defaults_and_actions(
    client: FlaskClient, user: User
) -> None:
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "contracts@example.com"
    db.session.commit()

    _submit_message(client, user)
    message = _latest_message_for(user)
    assert message.field_values
    for value in message.field_values:
        assert PGP_SIG in (value.value or "")

    inbox_response = client.get(url_for("inbox"), follow_redirects=True)
    assert inbox_response.status_code == 200
    assert message.public_id in inbox_response.text

    message_response = client.get(
        url_for("message", public_id=message.public_id), follow_redirects=True
    )
    assert message_response.status_code == 200

    status_response = client.post(
        url_for("set_message_status", public_id=message.public_id),
        data={"status": MessageStatus.ACCEPTED.value},
        follow_redirects=True,
    )
    assert status_response.status_code == 200
    db.session.refresh(message)
    assert message.status == MessageStatus.ACCEPTED

    with patch("hushline.routes.message.do_send_email", new=MagicMock()) as send_email_mock:
        resend_response = client.post(
            url_for("resend_message", public_id=message.public_id),
            data={"submit": ""},
            follow_redirects=True,
        )
        assert resend_response.status_code == 200
        assert "Message resent to your email inbox." in resend_response.text
        assert send_email_mock.call_count >= 1

    delete_response = client.post(
        url_for("delete_message", public_id=message.public_id),
        data={"submit": ""},
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "Message deleted successfully." in delete_response.text
    assert (
        db.session.scalars(db.select(Message).where(Message.id == message.id)).one_or_none() is None
    )


@pytest.mark.usefixtures("_authenticated_user", "_pgp_user")
def test_contract_message_actions_do_not_cross_user_boundaries(
    client: FlaskClient, user: User, user2: User
) -> None:
    _submit_message(client, user)
    message = _latest_message_for(user)

    _authenticate_as(client, user2)

    message_response = client.get(
        url_for("message", public_id=message.public_id), follow_redirects=True
    )
    assert message_response.status_code == 404
    assert "404: Not Found" in message_response.text

    status_response = client.post(
        url_for("set_message_status", public_id=message.public_id),
        data={"status": MessageStatus.ACCEPTED.value},
        follow_redirects=True,
    )
    assert status_response.status_code == 404
    db.session.refresh(message)
    assert message.status != MessageStatus.ACCEPTED

    with patch("hushline.routes.message.do_send_email", new=MagicMock()) as send_email_mock:
        resend_response = client.post(
            url_for("resend_message", public_id=message.public_id),
            data={"submit": ""},
            follow_redirects=True,
        )
        assert resend_response.status_code == 200
        assert "Message not found." in resend_response.text
        send_email_mock.assert_not_called()

    delete_response = client.post(
        url_for("delete_message", public_id=message.public_id),
        data={"submit": ""},
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "Message not found." in delete_response.text
    assert db.session.get(Message, message.id) is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_contract_authenticated_settings_profile_and_auth_round_trip(
    client: FlaskClient, user: User, user_password: str
) -> None:
    display_name = "Contract Display"
    profile_bio = "Contract Bio"
    username_suffix = "-ct"
    new_username = f"{user.primary_username.username}{username_suffix}"
    new_password = "ContractPassword123!"

    response = client.post(
        url_for("settings.profile"),
        data=form_to_data(DisplayNameForm(data={"display_name": display_name})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Display name updated successfully" in response.text

    response = client.post(
        url_for("settings.profile"),
        data={
            "bio": profile_bio,
            "extra_field_label1": "Signal",
            "extra_field_value1": "@contract-user",
            "update_bio": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Bio and fields updated successfully" in response.text

    response = client.post(
        url_for("settings.profile"),
        data={"show_in_directory": "y", "update_directory_visibility": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Directory visibility updated successfully" in response.text

    response = client.post(
        url_for("settings.auth"),
        data=form_to_data(ChangeUsernameForm(data={"new_username": new_username})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Username changed successfully" in response.text

    response = client.post(
        url_for("settings.auth"),
        data=form_to_data(
            ChangePasswordForm(data={"old_password": user_password, "new_password": new_password})
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Password successfully changed. Please log in again." in response.text

    login_response = client.post(
        url_for("login"),
        data={"username": new_username, "password": new_password},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Inbox" in login_response.text

    updated_username = db.session.scalars(
        db.select(Username).where(Username._username == new_username)
    ).one()
    assert updated_username.display_name == display_name
    assert updated_username.bio == profile_bio
    assert updated_username.show_in_directory is True
    assert updated_username.extra_field_label1 == "Signal"
    assert updated_username.extra_field_value1 == "@contract-user"


@pytest.mark.usefixtures("_authenticated_user")
def test_contract_authenticated_encryption_and_data_export_flow(
    client: FlaskClient, user: User
) -> None:
    with open("tests/test_pgp_key.txt", encoding="utf-8") as f:
        pgp_key = f.read().strip()

    response = client.post(
        url_for("settings.encryption"),
        data=form_to_data(PGPKeyForm(data={"pgp_key": pgp_key})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "PGP key updated successfully" in response.text

    with (
        patch(
            "hushline.settings.proton.requests.get",
            return_value=MagicMock(status_code=200, text=pgp_key),
        ),
        patch("hushline.settings.proton.is_valid_pgp_key", return_value=True),
        patch("hushline.settings.proton.can_encrypt_with_pgp_key", return_value=True),
    ):
        proton_response = client.post(
            url_for("settings.update_pgp_key_proton"),
            data={"email": "contract@proton.me"},
            follow_redirects=True,
        )
    assert proton_response.status_code == 200
    assert "PGP key updated successfully." in proton_response.text

    export_response = client.post(url_for("settings.data_export"), data={"encrypt_export": "false"})
    assert export_response.status_code == 200
    assert export_response.mimetype == "application/zip"
    assert export_response.headers["Content-Disposition"].startswith("attachment;")

    encrypted_export_response = client.post(
        url_for("settings.data_export"), data={"encrypt_export": "y"}
    )
    assert encrypted_export_response.status_code == 200
    assert encrypted_export_response.mimetype == "application/pgp-encrypted"
    assert encrypted_export_response.data.startswith(b"-----BEGIN PGP MESSAGE-----")


@pytest.mark.usefixtures("_authenticated_user")
def test_contract_paid_user_alias_vision_and_subscription_controls(
    client: FlaskClient, user: User
) -> None:
    business_tier = db.session.scalars(
        db.select(Tier).where(Tier.name.in_(["Business", "Super User"]))
    ).first()
    assert business_tier is not None
    user.tier_id = business_tier.id
    user.stripe_subscription_id = "sub_contract_123"
    db.session.commit()

    add_alias_response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(NewAliasForm(data={"username": "contractalias"})),
        follow_redirects=True,
    )
    assert add_alias_response.status_code == 200
    added_alias = db.session.scalars(
        db.select(Username).where(
            Username.user_id == user.id,
            Username.is_primary.is_(False),
            Username._username == "contractalias",
        )
    ).one_or_none()
    assert added_alias is not None

    delete_alias_response = client.post(
        url_for("settings.delete_alias", username_id=added_alias.id),
        data={"delete_alias": ""},
        follow_redirects=True,
    )
    assert delete_alias_response.status_code == 200
    assert db.session.get(Username, added_alias.id) is None

    vision_response = client.get(url_for("vision"), follow_redirects=True)
    assert vision_response.status_code == 200
    assert "Vision Assistant" in vision_response.text

    with patch("hushline.premium.stripe.Subscription.modify", return_value=MagicMock()):
        disable_response = client.post(url_for("premium.disable_autorenew"), follow_redirects=False)
    assert disable_response.status_code == 302
    assert disable_response.headers["Location"].endswith(url_for("premium.index"))
    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is True

    with patch("hushline.premium.stripe.Subscription.modify", return_value=MagicMock()):
        enable_response = client.post(url_for("premium.enable_autorenew"), follow_redirects=False)
    assert enable_response.status_code == 302
    assert enable_response.headers["Location"].endswith(url_for("premium.index"))
    db.session.refresh(user)
    assert user.stripe_subscription_cancel_at_period_end is False

    with patch("hushline.premium.stripe.Subscription.delete", return_value=MagicMock()):
        cancel_response = client.post(url_for("premium.cancel"), follow_redirects=False)
    assert cancel_response.status_code == 302
    assert cancel_response.headers["Location"].endswith(url_for("premium.index"))
    db.session.refresh(user)
    assert user.is_free_tier


@pytest.mark.usefixtures("_authenticated_admin")
def test_contract_admin_branding_guidance_and_registration_controls(
    client: FlaskClient, app: Flask, admin: User, user: User
) -> None:
    app.config["USER_VERIFICATION_ENABLED"] = True

    directory_text = "Contract directory intro"
    branding_response = client.post(
        url_for("settings.branding"),
        data={"markdown": directory_text, UpdateDirectoryTextForm.submit.name: ""},
        follow_redirects=True,
    )
    assert branding_response.status_code == 200
    assert "Directory intro text updated" in branding_response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT) == directory_text

    color_response = client.post(
        url_for("settings.branding"),
        data=form_to_data(UpdateBrandPrimaryColorForm(data={"brand_primary_hex_color": "#1144aa"})),
        follow_redirects=True,
    )
    assert color_response.status_code == 200
    assert "Brand primary color updated successfully" in color_response.text

    name_response = client.post(
        url_for("settings.branding"),
        data=form_to_data(UpdateBrandAppNameForm(data={"brand_app_name": "Hush Contract"})),
        follow_redirects=True,
    )
    assert name_response.status_code == 200
    assert "Brand app name updated successfully" in name_response.text

    homepage_response = client.post(
        url_for("settings.branding"),
        data={
            "username": user.primary_username.username,
            SetHomepageUsernameForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert homepage_response.status_code == 200
    assert "Homepage set to user" in homepage_response.text

    profile_header_response = client.post(
        url_for("settings.branding"),
        data=form_to_data(UpdateProfileHeaderForm(data={"template": "<p>{{username}}</p>"})),
        follow_redirects=True,
    )
    assert profile_header_response.status_code == 200
    assert "Profile header template updated successfully" in profile_header_response.text

    donate_toggle_response = client.post(
        url_for("settings.branding"),
        data=form_to_data(ToggleDonateButtonForm(data={"hide_button": True})),
        follow_redirects=True,
    )
    assert donate_toggle_response.status_code == 200
    assert "Donate button set to hidden" in donate_toggle_response.text

    guidance_toggle_response = client.post(
        url_for("settings.guidance"),
        data={"show_user_guidance": True, UserGuidanceForm.submit.name: ""},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert guidance_toggle_response.status_code == 200
    assert "User guidance enabled." in guidance_toggle_response.text

    registration_toggle_response = client.post(
        url_for("settings.registration"),
        data={"registration_enabled": "y"},
        follow_redirects=True,
    )
    assert registration_toggle_response.status_code == 200
    assert "Registration enabled." in registration_toggle_response.text

    create_invite_response = client.post(
        url_for("settings.registration"),
        data={"create_invite_code": ""},
        follow_redirects=True,
    )
    assert create_invite_response.status_code == 200
    invite = db.session.scalars(db.select(InviteCode).order_by(InviteCode.id.desc())).first()
    assert invite is not None

    verify_response = client.post(
        url_for("admin.toggle_verified", user_id=user.id),
        data={"is_verified": "true"},
        follow_redirects=True,
    )
    assert verify_response.status_code == 200
    db.session.refresh(user)
    assert user.primary_username.is_verified is True

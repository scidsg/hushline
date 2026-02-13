from __future__ import annotations

from unittest.mock import MagicMock, patch

import pyotp
import pytest
from flask import url_for
from flask.testing import FlaskClient
from helpers import get_captcha_from_session

from hushline.db import db
from hushline.model import Message, User
from hushline.routes.common import format_full_message_email_body

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

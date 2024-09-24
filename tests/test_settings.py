from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, SMTPEncryption, User, Username


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_page_loads(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("settings.index"), follow_redirects=True)
    assert response.status_code == 200
    assert "Settings" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_change_display_name(client: FlaskClient, user: User) -> None:
    new_display_name = (user.primary_username.display_name or "") + "_NEW"

    response = client.post(
        url_for("settings.index"),
        data={
            "display_name": new_display_name,
            "update_display_name": "Update Display Name",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Display name updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.display_name == new_display_name


@pytest.mark.usefixtures("_authenticated_user")
def test_change_username(client: FlaskClient, user: User) -> None:
    new_username = user.primary_username.username + "-new"

    response = client.post(
        url_for("settings.index"),
        data={
            "new_username": new_username,
            "change_username": "Change Username",  # html submit button
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Username changed successfully" in response.text

    updated_user = db.session.scalars(db.select(Username).filter_by(_username=new_username)).one()
    assert updated_user.username == new_username
    assert not updated_user.is_verified


@pytest.mark.usefixtures("_authenticated_user")
def test_change_password(client: FlaskClient, user: User, user_password: str) -> None:
    new_password = user_password + "xxx"

    assert len(original_password_hash := user.password_hash) > 32
    assert original_password_hash.startswith("$scrypt$")
    assert user_password not in original_password_hash

    response = client.post(
        url_for("settings.change_password"),
        data={
            "old_password": user_password,
            "new_password": new_password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Password successfully changed. Please log in again." in response.text
    assert "/login" in response.request.url
    assert len(new_password_hash := user.password_hash) > 32
    assert new_password_hash.startswith("$scrypt$")
    assert original_password_hash not in new_password_hash
    assert user_password not in new_password_hash
    assert new_password not in new_password_hash

    # TODO simulate a log out?

    # Attempt to log in with the registered user's old password
    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": user_password},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid username or password" in response.text
    assert "/login" in response.request.url

    # TODO simulate a log out?

    # Attempt to log in with the registered user's new password
    response = client.post(
        url_for("login"),
        data={"username": user.primary_username.username, "password": new_password},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Empty Inbox" in response.text
    assert "Invalid username or password" not in response.text
    assert "/inbox" in response.request.url


@pytest.mark.usefixtures("_authenticated_user")
def test_add_pgp_key(client: FlaskClient, user: User, user_password: str) -> None:
    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read()

    response = client.post(
        url_for("settings.update_pgp_key"),
        data={"pgp_key": new_pgp_key},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Failed to update PGP key"
    assert "PGP key updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.user.pgp_key == new_pgp_key


@pytest.mark.usefixtures("_authenticated_user")
def test_add_invalid_pgp_key(client: FlaskClient, user: User) -> None:
    invalid_pgp_key = "NOT A VALID PGP KEY BLOCK"

    response = client.post(
        url_for("settings.update_pgp_key"),
        data={"pgp_key": invalid_pgp_key},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid PGP key format" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.user.pgp_key != invalid_pgp_key


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_no_pgp(SMTP: MagicMock, client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("settings.update_smtp_settings"),
        data={
            "forwarding_enabled": True,
            "email_address": "primary@example.com",
            "custom_smtp_settings": True,
            "smtp_settings-smtp_server": "smtp.example.com",
            "smtp_settings-smtp_port": 587,
            "smtp_settings-smtp_username": "user@example.com",
            "smtp_settings-smtp_password": "securepassword123",
            "smtp_settings-smtp_encryption": "StartTLS",
            "smtp_settings-smtp_sender": "sender@example.com",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Email forwarding requires a configured PGP key" in response.text

    updated_user = (
        db.session.scalars(db.select(Username).filter_by(_username=user.primary_username.username))
        .one()
        .user
    )
    assert updated_user.email is None
    assert updated_user.smtp_server is None
    assert updated_user.smtp_port is None
    assert updated_user.smtp_username is None
    assert updated_user.smtp_password is None


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_starttls(SMTP: MagicMock, client: FlaskClient, user: User) -> None:
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 587,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "StartTLS",
        "smtp_settings-smtp_sender": "sender@example.com",
    }

    response = client.post(
        url_for("settings.update_smtp_settings"),
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SMTP settings updated successfully" in response.text

    SMTP.assert_called_with(user.smtp_server, user.smtp_port, timeout=ANY)
    SMTP.return_value.__enter__.return_value.starttls.assert_called_once_with()
    SMTP.return_value.__enter__.return_value.login.assert_called_once_with(
        user.smtp_username, user.smtp_password
    )

    updated_user = (
        db.session.scalars(db.select(Username).filter_by(_username=user.primary_username.username))
        .one()
        .user
    )
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    assert updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    assert updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    assert updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    assert updated_user.smtp_encryption.value == new_smtp_settings["smtp_settings-smtp_encryption"]
    assert updated_user.smtp_sender == new_smtp_settings["smtp_settings-smtp_sender"]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.utils.smtplib.SMTP_SSL")
def test_update_smtp_settings_ssl(SMTP: MagicMock, client: FlaskClient, user: User) -> None:
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 465,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "SSL",
        "smtp_settings-smtp_sender": "sender@example.com",
    }

    response = client.post(
        url_for("settings.update_smtp_settings"),
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SMTP settings updated successfully" in response.text

    SMTP.assert_called_with(user.smtp_server, user.smtp_port, timeout=ANY)
    SMTP.return_value.__enter__.return_value.starttls.assert_not_called()
    SMTP.return_value.__enter__.return_value.login.assert_called_once_with(
        user.smtp_username, user.smtp_password
    )

    updated_user = (
        db.session.scalars(db.select(Username).filter_by(_username=user.primary_username.username))
        .one()
        .user
    )
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    assert updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    assert updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    assert updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    assert updated_user.smtp_encryption.value == new_smtp_settings["smtp_settings-smtp_encryption"]
    assert updated_user.smtp_sender == new_smtp_settings["smtp_settings-smtp_sender"]


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_default_forwarding(
    SMTP: MagicMock, client: FlaskClient, user: User
) -> None:
    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "smtp_settings-smtp_encryption": "StartTLS",
    }

    response = client.post(
        url_for("settings.update_smtp_settings"),
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SMTP settings updated successfully" in response.text

    SMTP.assert_not_called()
    SMTP.return_value.__enter__.return_value.starttls.assert_not_called()
    SMTP.return_value.__enter__.return_value.login.assert_not_called()

    updated_user = (
        db.session.scalars(db.select(Username).filter_by(_username=user.primary_username.username))
        .one()
        .user
    )
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server is None
    assert updated_user.smtp_port is None
    assert updated_user.smtp_username is None
    assert updated_user.smtp_password is None
    assert updated_user.smtp_encryption.value == SMTPEncryption.default().value
    assert updated_user.smtp_sender is None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account(client: FlaskClient, user: User, message: Message) -> None:
    # save these because SqlAlchemy is too smart about nullifying them on deletion
    user_id = user.id
    username_id = user.primary_username.id
    msg_id = message.id

    resp = client.post(url_for("settings.delete_account"), follow_redirects=True)
    assert resp.status_code == 200
    assert "Your account and all related information have been deleted." in resp.text
    assert db.session.scalars(db.select(User).filter_by(id=user_id)).one_or_none() is None
    assert db.session.scalars(db.select(Username).filter_by(id=username_id)).one_or_none() is None
    assert db.session.scalars(db.select(Message).filter_by(id=msg_id)).one_or_none() is None

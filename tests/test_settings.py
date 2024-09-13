from secrets import token_urlsafe
from unittest.mock import ANY, MagicMock, patch

from auth_helper import configure_pgp, login_user, register_user
from flask import url_for
from flask.testing import FlaskClient

from hushline.model import SMTPEncryption, Username


def test_settings_page_loads(client: FlaskClient) -> None:
    username = "testuser_settings"
    password = "SecureTestPass123!"
    register_user(client, username, password)

    assert login_user(client, username, password)

    response = client.get(url_for("settings.index"), follow_redirects=True)
    assert response.status_code == 200


def test_change_display_name(client: FlaskClient) -> None:
    username = "testuser_settings"
    password = "SecureTestPass123!"
    register_user(client, username, password)
    login_user(client, username, password)

    new_display_name = "New Display Name"

    response = client.post(
        "/settings/",
        data={
            "display_name": new_display_name,
            "update_display_name": "Update Display Name",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, "Failed to update display name"
    assert "Display name updated successfully" in response.text

    updated_user = Username.query.filter_by(_username=username).one()
    assert updated_user.display_name == new_display_name


def test_change_username(client: FlaskClient) -> None:
    username = "original_username"
    password = "SecureTestPass123!"
    new_username = "updated_username"

    register_user(client, username, password)
    assert login_user(client, username, password)

    response = client.post(
        url_for("settings.index"),
        data={
            "new_username": new_username,
            "change_username": "Update Username",  # html submit button
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Username changed successfully" in response.text

    updated_user = Username.query.filter_by(_username=new_username).one()
    assert updated_user.username == new_username
    assert not updated_user.is_verified


def test_change_password(client: FlaskClient) -> None:
    username = "test_change_password"
    original_password = f"{token_urlsafe(16)}!"
    new_password = f"{token_urlsafe(16)}!!!"

    user = register_user(client, username, original_password)
    assert len(original_password_hash := user.password_hash) > 32
    assert original_password_hash.startswith("$scrypt$")
    assert original_password not in original_password_hash

    logged_in_user = login_user(client, username, original_password)
    assert logged_in_user is not None
    assert user.id == logged_in_user.id

    response = client.post(
        "/settings/change-password",
        data={
            "old_password": original_password,
            "new_password": new_password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200, "Failed to update password"
    assert "login" in response.request.url
    assert len(new_password_hash := user.password_hash) > 32
    assert new_password_hash.startswith("$scrypt$")
    assert original_password_hash not in new_password_hash
    assert original_password not in new_password_hash
    assert new_password not in new_password_hash
    assert "Password successfully changed. Please log in again." in response.text

    # Attempt to log in with the registered user's old password
    response = client.post(
        "/login", data={"username": username, "password": original_password}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "login" in response.request.url
    assert "Invalid username or password" in response.text

    # Attempt to log in with the registered user's new password
    response = client.post(
        "/login", data={"username": username, "password": new_password}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "inbox" in response.request.url
    assert "Empty Inbox" in response.text
    assert "Invalid username or password" not in response.text


def test_add_pgp_key(client: FlaskClient) -> None:
    register_user(client, "user_with_pgp", "SecureTestPass123!")
    login_user(client, "user_with_pgp", "SecureTestPass123!")

    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read()

    response = client.post(
        "/settings/update-pgp-key",
        data={"pgp_key": new_pgp_key},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Failed to update PGP key"
    assert "PGP key updated successfully" in response.text

    updated_user = Username.query.filter_by(_username="user_with_pgp").one()
    assert updated_user.user.pgp_key == new_pgp_key


def test_add_invalid_pgp_key(client: FlaskClient) -> None:
    username = "user_invalid_pgp"
    password = "SecureTestPass123!"
    invalid_pgp_key = "NOT A VALID PGP KEY BLOCK"

    register_user(client, username, password)
    login_user(client, username, password)

    response = client.post(
        "/settings/update-pgp-key",
        data={"pgp_key": invalid_pgp_key},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid PGP key format" in response.text

    updated_user = Username.query.filter_by(_username=username).one()
    assert updated_user.user.pgp_key != invalid_pgp_key


@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_no_pgp(SMTP: MagicMock, client: FlaskClient) -> None:
    username = "user_smtp_settings_no_pgp"
    password = "SecureTestPass123!"

    register_user(client, username, password)
    login_user(client, username, password)

    response = client.post(
        "/settings/update-smtp-settings",
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

    updated_user = Username.query.filter_by(_username=username).one().user

    assert updated_user.email is None
    assert updated_user.smtp_server is None
    assert updated_user.smtp_port is None
    assert updated_user.smtp_username is None
    assert updated_user.smtp_password is None


@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_starttls(SMTP: MagicMock, client: FlaskClient) -> None:
    username = "user_smtp_settings_tls"
    password = "SecureTestPass123!"

    user = register_user(client, username, password)
    login_user(client, username, password)
    configure_pgp(client)

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
        "/settings/update-smtp-settings",
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

    updated_user = Username.query.filter_by(_username="user_smtp_settings_tls").one().user
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    assert updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    assert updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    assert updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    assert updated_user.smtp_encryption.value == new_smtp_settings["smtp_settings-smtp_encryption"]
    assert updated_user.smtp_sender == new_smtp_settings["smtp_settings-smtp_sender"]


@patch("hushline.utils.smtplib.SMTP_SSL")
def test_update_smtp_settings_ssl(SMTP: MagicMock, client: FlaskClient) -> None:
    username = "user_smtp_settings_ssl"
    password = "SecureTestPass123!"
    user = register_user(client, username, password)
    login_user(client, username, password)
    configure_pgp(client)

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
        "/settings/update-smtp-settings",
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

    updated_user = Username.query.filter_by(_username="user_smtp_settings_ssl").one().user
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server == new_smtp_settings["smtp_settings-smtp_server"]
    assert updated_user.smtp_port == new_smtp_settings["smtp_settings-smtp_port"]
    assert updated_user.smtp_username == new_smtp_settings["smtp_settings-smtp_username"]
    assert updated_user.smtp_password == new_smtp_settings["smtp_settings-smtp_password"]
    assert updated_user.smtp_encryption.value == new_smtp_settings["smtp_settings-smtp_encryption"]
    assert updated_user.smtp_sender == new_smtp_settings["smtp_settings-smtp_sender"]


@patch("hushline.utils.smtplib.SMTP")
def test_update_smtp_settings_default_forwarding(SMTP: MagicMock, client: FlaskClient) -> None:
    username = "user_default_forwarding"
    password = "SecureTestPass123!"

    register_user(client, username, password)
    login_user(client, username, password)
    configure_pgp(client)

    new_smtp_settings = {
        "forwarding_enabled": True,
        "email_address": "primary@example.com",
        "smtp_settings-smtp_encryption": "StartTLS",
    }

    response = client.post(
        "/settings/update-smtp-settings",
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SMTP settings updated successfully" in response.text

    SMTP.assert_not_called()
    SMTP.return_value.__enter__.return_value.starttls.assert_not_called()
    SMTP.return_value.__enter__.return_value.login.assert_not_called()

    updated_user = Username.query.filter_by(_username=username).one().user
    assert updated_user.email == new_smtp_settings["email_address"]
    assert updated_user.smtp_server is None
    assert updated_user.smtp_port is None
    assert updated_user.smtp_username is None
    assert updated_user.smtp_password is None
    assert updated_user.smtp_encryption.value == SMTPEncryption.default().value
    assert updated_user.smtp_sender is None

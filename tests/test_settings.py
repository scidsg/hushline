from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import HostOrganization, Message, SMTPEncryption, User, Username


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
    assert len(original_password_hash := user.password_hash) > 32
    assert original_password_hash.startswith("$scrypt$")
    assert user_password not in original_password_hash

    url = url_for("settings.change_password")
    for new_password in [user_password, "", "aB!!", "aB3!", (33 * "aB3!")[:129], 5 * "aB3!"]:
        data = dict(old_password=user_password, new_password=new_password)
        response = client.post(url, data=data, follow_redirects=True)
        if (
            user_password != new_password
            and 17 < len(user_password) < 129
            and 17 < len(new_password) < 129
        ):
            assert response.status_code == 200, data
            assert "Password successfully changed. Please log in again." in response.text, data
            assert "/login" in response.request.url, data
            assert len(new_password_hash := user.password_hash) > 32, data
            assert new_password_hash.startswith("$scrypt$"), data
            assert original_password_hash not in new_password_hash, data
            assert user_password not in new_password_hash, data
            assert new_password not in new_password_hash, data
        elif user_password == new_password:
            assert "Cannot choose a repeat password." in response.text, data
            assert "/settings" in response.request.url, data
            assert original_password_hash == user.password_hash, data
        else:
            assert "Invalid form data. Please try again." in response.text, data
            assert "/settings" in response.request.url, data
            assert original_password_hash == user.password_hash, data

    assert original_password_hash != user.password_hash

    # TODO simulate a log out?

    # Attempt to log in with the registered user's old password
    data = dict(username=user.primary_username.username, password=user_password)
    response = client.post(url_for("login"), data=data, follow_redirects=True)
    assert response.status_code == 200, data
    assert "Invalid username or password" in response.text, data
    assert "/login" in response.request.url, data

    # TODO simulate a log out?

    # Attempt to log in with the registered user's new password
    data = dict(username=user.primary_username.username, password=new_password)
    response = client.post(url_for("login"), data=data, follow_redirects=True)
    assert response.status_code == 200, data
    assert "Empty Inbox" in response.text, data
    assert "Invalid username or password" not in response.text, data
    assert "/inbox" in response.request.url, data


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
def test_add_alias(client: FlaskClient, user: User) -> None:
    alias_username = str(uuid4())[0:12]
    response = client.post(
        url_for("settings.index"),
        data={
            "username": alias_username,
            "new_alias": "",  # html form
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Alias created successfully" in response.text

    alias = db.session.scalars(db.select(Username).filter_by(_username=alias_username)).one()
    assert not alias.is_primary
    assert alias.user_id == user.id


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias_duplicate(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("settings.index"),
        data={
            "username": user.primary_username.username,
            "new_alias": "",  # html form
        },
        follow_redirects=True,
    )
    assert "This username is already taken." in response.text
    assert db.session.scalar(db.func.count(Username.id)) == 1


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_page_loads(client: FlaskClient, user: User, user_alias: Username) -> None:
    response = client.get(
        url_for("settings.alias", username_id=user_alias.id), follow_redirects=True
    )
    assert response.status_code == 200
    assert f"Alias: @{user_alias.username}" in response.text


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


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_change_display_name(client: FlaskClient, user: User, user_alias: Username) -> None:
    new_display_name = (user_alias.display_name or "") + "_NEW"

    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data={
            "display_name": new_display_name,
            "update_display_name": "",  # html form
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Display name updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user_alias.username)
    ).one()
    assert updated_user.display_name == new_display_name


@pytest.mark.usefixtures("_authenticated_user")
def test_change_bio(client: FlaskClient, user: User) -> None:
    data = {
        "bio": str(uuid4()),
        "update_bio": "",  # html form
    }

    for i in range(1, 5):
        data[f"extra_field_label{i}"] = str(uuid4())
        data[f"extra_field_value{i}"] = str(uuid4())

    response = client.post(
        url_for("settings.index"),
        data=data,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Bio and fields updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.bio == data["bio"]

    for i in range(1, 5):
        label = f"extra_field_label{i}"
        value = f"extra_field_value{i}"
        assert getattr(updated_user, label) == data[label]
        assert getattr(updated_user, value) == data[value]


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_change_bio(client: FlaskClient, user: User, user_alias: Username) -> None:
    data = {
        "bio": str(uuid4()),
        "update_bio": "",  # html form
    }

    for i in range(1, 5):
        data[f"extra_field_label{i}"] = str(uuid4())
        data[f"extra_field_value{i}"] = str(uuid4())

    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data=data,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Bio and fields updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user_alias.username)
    ).one()
    assert updated_user.bio == data["bio"]

    for i in range(1, 5):
        label = f"extra_field_label{i}"
        value = f"extra_field_value{i}"
        assert getattr(updated_user, label) == data[label]
        assert getattr(updated_user, value) == data[value]


@pytest.mark.usefixtures("_authenticated_user")
def test_change_directory_visibility(client: FlaskClient, user: User) -> None:
    original_visibility = user.primary_username.show_in_directory
    resp = client.post(
        url_for("settings.index"),
        data={
            "show_in_directory": not original_visibility,
            "update_directory_visibility": "",  # html form
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Directory visibility updated successfully" in resp.text
    assert db.session.scalar(
        db.select(Username.show_in_directory).filter_by(id=user.primary_username.id)
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_change_directory_visibility(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    original_visibility = user_alias.show_in_directory
    resp = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data={
            "show_in_directory": not original_visibility,
            "update_directory_visibility": "",  # html form
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Directory visibility updated successfully" in resp.text
    assert db.session.scalar(db.select(Username.show_in_directory).filter_by(id=user_alias.id))


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_brand_primary_color(client: FlaskClient, admin: User) -> None:
    color = "#acab00"
    resp = client.post(
        url_for("settings.update_brand_primary_color"),
        data={"brand_primary_hex_color": color},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Brand primary color updated successfully" in resp.text

    soup = BeautifulSoup(resp.text, "html.parser")
    styles = soup.find_all("style")
    assert styles  # sensibility check
    for style in styles:
        if f"--color-brand: oklch(from {color} l c h);" in style.string:
            break
    else:
        pytest.fail("Brand color CSS not updated in response <style>")

    assert (host_org := HostOrganization.fetch())
    assert host_org.brand_primary_hex_color == color


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_brand_app_name(client: FlaskClient, admin: User) -> None:
    name = "h4cK3rZ"
    resp = client.post(
        url_for("settings.update_brand_app_name"),
        data={"brand_app_name": name},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Brand app name updated successfully" in resp.text

    soup = BeautifulSoup(resp.text, "html.parser")
    h1s = soup.select("header h1")
    assert h1s  # sensibility check
    for h1 in h1s:
        if name in h1.string:
            break
    else:
        pytest.fail("Brand name not updated in header <h1>")

    assert (host_org := HostOrganization.fetch())
    assert host_org.brand_app_name == name

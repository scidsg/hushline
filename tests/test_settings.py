from base64 import b64decode
from io import BytesIO
from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest
import requests
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.config import AliasMode, FieldsMode
from hushline.db import db
from hushline.model import (
    AuthenticationLog,
    Message,
    OrganizationSetting,
    SMTPEncryption,
    Tier,
    User,
    Username,
)
from hushline.settings import (
    ChangePasswordForm,
    ChangeUsernameForm,
    DeleteAliasForm,
    DeleteBrandLogoForm,
    DisplayNameForm,
    EmailForwardingForm,
    NewAliasForm,
    PGPKeyForm,
    SetHomepageUsernameForm,
    UpdateBrandAppNameForm,
    UpdateBrandLogoForm,
    UpdateBrandPrimaryColorForm,
    UpdateDirectoryTextForm,
    UpdateProfileHeaderForm,
    UserGuidanceAddPromptForm,
    UserGuidanceEmergencyExitForm,
    UserGuidanceForm,
    UserGuidancePromptContentForm,
)
from hushline.settings.branding import ToggleDonateButtonForm
from hushline.settings.notifications import (
    ToggleEncryptEntireBodyForm,
    ToggleIncludeContentForm,
    ToggleNotificationsForm,
)
from tests.helpers import form_to_data


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_page_loads(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("settings.profile"), follow_redirects=True)
    assert response.status_code == 200
    assert "Settings" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_change_display_name(client: FlaskClient, user: User) -> None:
    new_display_name = (user.primary_username.display_name or "") + "_NEW"

    response = client.post(
        url_for("settings.profile"),
        data=form_to_data(
            DisplayNameForm(
                data={
                    "display_name": new_display_name,
                }
            )
        ),
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
        url_for("settings.auth"),
        data=form_to_data(
            ChangeUsernameForm(
                data={
                    "new_username": new_username,
                }
            )
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Username changed successfully" in response.text

    updated_user = db.session.scalars(db.select(Username).filter_by(_username=new_username)).one()
    assert updated_user.username == new_username
    assert not updated_user.is_verified


@pytest.mark.usefixtures("_authenticated_user")
def test_change_username_rejects_case_insensitive_duplicate(
    client: FlaskClient, user: User, user2: User
) -> None:
    response = client.post(
        url_for("settings.auth"),
        data=form_to_data(
            ChangeUsernameForm(
                data={
                    "new_username": user2.primary_username.username.upper(),
                }
            )
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "This username is already taken." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_change_password(app: Flask, client: FlaskClient, user: User, user_password: str) -> None:
    assert len(original_password_hash := user.password_hash) > 32
    assert original_password_hash.startswith("$scrypt$")
    assert user_password not in original_password_hash
    original_password = user_password

    url = url_for("settings.auth")
    for new_password in [user_password, "", "aB!!", "aB3!", (33 * "aB3!")[:129], 5 * "aB3!"]:
        print(f"Testing: {new_password}")

        # have to use a test request context to "reset" the form fields
        with app.test_request_context():
            form = ChangePasswordForm(
                data={
                    "old_password": user_password,
                    "new_password": new_password,
                }
            )

        response = client.post(url, data=form_to_data(form), follow_redirects=True)
        if (
            user_password != new_password
            and 17 < len(user_password) < 129
            and 17 < len(new_password) < 129
        ):
            assert response.status_code == 200, response.text
            assert "Password successfully changed. Please log in again." in response.text
            assert len(new_password_hash := user.password_hash) > 32
            assert new_password_hash.startswith("$scrypt$")
            assert original_password_hash not in new_password_hash
            assert user_password not in new_password_hash
            assert new_password not in new_password_hash
            user_password = new_password
        elif user_password == new_password:
            assert "Cannot choose a repeat password." in response.text
            assert original_password_hash == user.password_hash
        else:
            assert "Your submitted form could not be processed" in response.text
            assert original_password_hash == user.password_hash

    assert original_password_hash != user.password_hash

    # TODO simulate a log out?

    # Attempt to log in with the registered user's old password
    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": original_password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid username or password" in response.text
    assert "/login" in response.request.url

    # TODO simulate a log out?

    # Attempt to log in with the registered user's new password
    response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": new_password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Empty Inbox" in response.text
    assert "Invalid username or password" not in response.text
    assert "/inbox" in response.request.url


@pytest.mark.usefixtures("_authenticated_user")
def test_add_pgp_key(client: FlaskClient, user: User, user_password: str) -> None:
    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read().strip()

    response = client.post(
        url_for("settings.encryption"),
        data=form_to_data(PGPKeyForm(data={"pgp_key": new_pgp_key})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "PGP key updated successfully" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.user.pgp_key == new_pgp_key


@pytest.mark.usefixtures("_authenticated_user")
def test_add_invalid_pgp_key(client: FlaskClient, user: User) -> None:
    invalid_pgp_key = "NOT A VALID PGP KEY BLOCK"

    response = client.post(
        url_for("settings.encryption"),
        data=form_to_data(PGPKeyForm(data={"pgp_key": invalid_pgp_key})),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Invalid PGP key format" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.user.pgp_key != invalid_pgp_key


@pytest.mark.usefixtures("_authenticated_user")
def test_add_pgp_key_without_encryption_subkey(client: FlaskClient, user: User) -> None:
    with open("tests/test_pgp_key.txt") as file:
        new_pgp_key = file.read().strip()

    with patch("hushline.settings.common.can_encrypt_with_pgp_key", return_value=False):
        response = client.post(
            url_for("settings.encryption"),
            data=form_to_data(PGPKeyForm(data={"pgp_key": new_pgp_key})),
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert "PGP key cannot be used for encryption" in response.text

    updated_user = db.session.scalars(
        db.select(Username).filter_by(_username=user.primary_username.username)
    ).one()
    assert updated_user.user.pgp_key != new_pgp_key


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.settings.proton.can_encrypt_with_pgp_key", return_value=True)
@patch("hushline.settings.proton.is_valid_pgp_key", return_value=True)
@patch("hushline.settings.proton.requests.get")
def test_add_pgp_key_proton_redirects_to_encryption(
    requests_get: MagicMock,
    is_valid_pgp_key: MagicMock,
    can_encrypt_with_pgp_key: MagicMock,
    client: FlaskClient,
) -> None:
    requests_get.return_value = MagicMock(status_code=200, text="dummy-pgp-key")
    is_valid_pgp_key.return_value = True
    can_encrypt_with_pgp_key.return_value = True

    response = client.post(
        url_for("settings.update_pgp_key_proton"),
        data={"email": "user@proton.me"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.encryption"))


@pytest.mark.usefixtures("_authenticated_user")
def test_add_pgp_key_proton_invalid_form_redirects_index(client: FlaskClient) -> None:
    response = client.post(url_for("settings.update_pgp_key_proton"), data={"email": ""})
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption")


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.settings.proton.requests.get")
def test_add_pgp_key_proton_request_exception_redirects_encryption(
    requests_get: MagicMock, client: FlaskClient
) -> None:
    requests_get.side_effect = requests.exceptions.RequestException("network error")
    response = client.post(
        url_for("settings.update_pgp_key_proton"),
        data={"email": "user@proton.me"},
    )
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption")


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.settings.proton.can_encrypt_with_pgp_key", return_value=False)
@patch("hushline.settings.proton.is_valid_pgp_key", return_value=True)
@patch("hushline.settings.proton.requests.get")
def test_add_pgp_key_proton_non_encryptable_key_redirects_encryption(
    requests_get: MagicMock,
    is_valid_pgp_key: MagicMock,
    can_encrypt_with_pgp_key: MagicMock,
    client: FlaskClient,
) -> None:
    _ = (is_valid_pgp_key, can_encrypt_with_pgp_key)
    requests_get.return_value = MagicMock(status_code=200, text="dummy-pgp-key")
    response = client.post(
        url_for("settings.update_pgp_key_proton"),
        data={"email": "user@proton.me"},
    )
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption")


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.settings.proton.is_valid_pgp_key", return_value=False)
@patch("hushline.settings.proton.requests.get")
def test_add_pgp_key_proton_invalid_key_redirects_encryption(
    requests_get: MagicMock, is_valid_pgp_key: MagicMock, client: FlaskClient
) -> None:
    _ = is_valid_pgp_key
    requests_get.return_value = MagicMock(status_code=200, text="not-a-key")
    response = client.post(
        url_for("settings.update_pgp_key_proton"),
        data={"email": "user@proton.me"},
    )
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption")


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.settings.proton.requests.get")
def test_add_pgp_key_proton_non_200_redirects_encryption(
    requests_get: MagicMock, client: FlaskClient
) -> None:
    requests_get.return_value = MagicMock(status_code=404, text="")
    response = client.post(
        url_for("settings.update_pgp_key_proton"),
        data={"email": "user@proton.me"},
    )
    assert response.status_code == 302
    assert response.location == url_for("settings.encryption")


@pytest.mark.usefixtures("_authenticated_user")
def test_advanced_settings_page_loads(client: FlaskClient) -> None:
    response = client.get(url_for("settings.advanced"))
    assert response.status_code == 200
    assert "Download My Data" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.usefixtures("_pgp_user")
@patch("hushline.settings.notifications.is_safe_smtp_host", return_value=False)
def test_update_smtp_settings_reject_private_host(
    is_safe_smtp_host: MagicMock, client: FlaskClient, user: User
) -> None:
    is_safe_smtp_host.return_value = False
    new_smtp_settings = {
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "localhost",
        "smtp_settings-smtp_port": 587,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "StartTLS",
        "smtp_settings-smtp_sender": "sender@example.com",
        EmailForwardingForm.submit.name: "",
    }

    response = client.post(
        url_for("settings.notifications"),
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "SMTP server must resolve to a public IP address" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.email.smtplib.SMTP")
def test_update_smtp_settings_no_pgp(SMTP: MagicMock, client: FlaskClient, user: User) -> None:
    user.pgp_key = None
    db.session.commit()

    response = client.post(
        url_for("settings.notifications"),
        # for some reason using the Form class doesn't work here. why? fuck if i know.
        data={
            "email_address": "primary@example.com",
            "custom_smtp_settings": True,
            "smtp_settings-smtp_server": "smtp.example.com",
            "smtp_settings-smtp_port": 587,
            "smtp_settings-smtp_username": "user@example.com",
            "smtp_settings-smtp_password": "securepassword123",
            "smtp_settings-smtp_encryption": "StartTLS",
            "smtp_settings-smtp_sender": "sender@example.com",
            EmailForwardingForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "Email forwarding requires a configured PGP key" in response.text, response.text

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
@patch("hushline.settings.notifications.is_safe_smtp_host", return_value=True)
@patch("hushline.email.smtplib.SMTP")
def test_update_smtp_settings_starttls(
    SMTP: MagicMock,
    is_safe_smtp_host: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    is_safe_smtp_host.return_value = True
    new_smtp_settings = {
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 587,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "StartTLS",
        "smtp_settings-smtp_sender": "sender@example.com",
        EmailForwardingForm.submit.name: "",
    }

    response = client.post(
        url_for("settings.notifications"),
        data=new_smtp_settings,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "SMTP settings updated successfully" in response.text

    SMTP.assert_called_with(user.smtp_server, user.smtp_port, timeout=ANY)
    SMTP.return_value.__enter__.return_value.starttls.assert_called_once_with(context=ANY)
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
@patch("hushline.settings.notifications.is_safe_smtp_host", return_value=True)
@patch("hushline.email.smtplib.SMTP_SSL")
def test_update_smtp_settings_ssl(
    SMTP: MagicMock,
    is_safe_smtp_host: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    is_safe_smtp_host.return_value = True
    new_smtp_settings = {
        "email_address": "primary@example.com",
        "custom_smtp_settings": True,
        "smtp_settings-smtp_server": "smtp.example.com",
        "smtp_settings-smtp_port": 465,
        "smtp_settings-smtp_username": "user@example.com",
        "smtp_settings-smtp_password": "securepassword123",
        "smtp_settings-smtp_encryption": "SSL",
        "smtp_settings-smtp_sender": "sender@example.com",
        EmailForwardingForm.submit.name: "",
    }

    response = client.post(
        url_for("settings.notifications"),
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
@patch("hushline.settings.notifications.is_safe_smtp_host", return_value=True)
@patch("hushline.email.smtplib.SMTP")
def test_update_smtp_settings_default_forwarding(
    SMTP: MagicMock,
    is_safe_smtp_host: MagicMock,
    client: FlaskClient,
    user: User,
) -> None:
    is_safe_smtp_host.return_value = True
    new_smtp_settings = {
        "email_address": "primary@example.com",
        "smtp_settings-smtp_encryption": "StartTLS",
        EmailForwardingForm.submit.name: "",
    }

    response = client.post(
        url_for("settings.notifications"),
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
def test_toggle_notifications_setting(client: FlaskClient, user: User) -> None:
    user.enable_email_notifications = False
    db.session.commit()

    response = client.post(
        url_for("settings.notifications"),
        data={
            ToggleNotificationsForm.submit.name: "",
            "enable_email_notifications": "y",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Email notifications enabled" in response.text
    assert user.enable_email_notifications


@pytest.mark.usefixtures("_authenticated_user")
def test_toggle_include_content_setting(client: FlaskClient, user: User) -> None:
    user.email_include_message_content = True
    db.session.commit()

    response = client.post(
        url_for("settings.notifications"),
        data={
            ToggleIncludeContentForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Email message content disabled" in response.text
    assert not user.email_include_message_content


@pytest.mark.usefixtures("_authenticated_user")
def test_toggle_encrypt_entire_body_setting(client: FlaskClient, user: User) -> None:
    user.email_encrypt_entire_body = False
    db.session.commit()

    response = client.post(
        url_for("settings.notifications"),
        data={
            ToggleEncryptEntireBodyForm.submit.name: "",
            "encrypt_entire_body": "y",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "The entire body of email messages will be encrypted" in response.text
    assert user.email_encrypt_entire_body


@pytest.mark.usefixtures("_authenticated_user")
def test_notifications_invalid_post_returns_400(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.notifications"),
        data={"not_a_real_form": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert "Your submitted form could not be processed" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias(app: Flask, client: FlaskClient, user: User) -> None:
    app.config["ALIAS_MODE"] = AliasMode.ALWAYS

    alias_username = str(uuid4())[0:12]
    response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(
            NewAliasForm(
                data={
                    "username": alias_username,
                }
            )
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Alias created successfully" in response.text

    alias = db.session.scalars(db.select(Username).filter_by(_username=alias_username)).one()
    assert not alias.is_primary
    assert alias.user_id == user.id


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias_fails_when_alias_mode_is_never(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["ALIAS_MODE"] = AliasMode.NEVER

    alias_username = str(uuid4())[0:12]
    response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(
            NewAliasForm(
                data={
                    "username": alias_username,
                }
            )
        ),
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert not db.session.scalars(
        db.select(Username).filter_by(_username=alias_username)
    ).one_or_none()


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias_not_exceed_max(
    app: Flask, client: FlaskClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    # patch to a small number for faster tests
    monkeypatch.setattr(User, "_PREMIUM_ALIAS_COUNT", 2)

    app.config["ALIAS_MODE"] = AliasMode.PREMIUM
    user.set_business_tier()

    # add up to the max number
    max_alises = user.max_aliases
    for _ in range(max_alises):
        alias_username = str(uuid4())[0:12]
        with app.test_request_context():
            form = NewAliasForm(
                data={
                    "username": alias_username,
                }
            )

        response = client.post(
            url_for("settings.aliases"),
            data=form_to_data(form),
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert db.session.scalars(
            db.select(Username).filter_by(_username=alias_username)
        ).one_or_none()

    # try adding one more
    alias_username = str(uuid4())[0:12]
    response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(
            NewAliasForm(
                data={
                    "username": alias_username,
                }
            )
        ),
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert (
        "Your current subscription level does not allow the creation of more aliases"
        in response.text
    )
    assert not db.session.scalars(
        db.select(Username).filter_by(_username=alias_username)
    ).one_or_none()


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias_duplicate(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(
            NewAliasForm(
                data={
                    "username": user.primary_username.username,
                }
            )
        ),
        follow_redirects=True,
    )
    assert "This username is already taken." in response.text
    assert db.session.scalar(db.func.count(Username.id)) == 1


@pytest.mark.usefixtures("_authenticated_user")
def test_add_alias_duplicate_case_insensitive(client: FlaskClient, user: User) -> None:
    response = client.post(
        url_for("settings.aliases"),
        data=form_to_data(
            NewAliasForm(
                data={
                    "username": user.primary_username.username.upper(),
                }
            )
        ),
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
def test_delete_alias(client: FlaskClient, user: User, user_alias: Username) -> None:
    response = client.post(
        url_for("settings.delete_alias", username_id=user_alias.id),
        data=form_to_data(DeleteAliasForm()),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Alias deleted successfully" in response.text

    alias_row = db.session.scalars(db.select(Username).filter_by(id=user_alias.id)).one_or_none()
    assert alias_row is None


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_account(
    client: FlaskClient, user: User, message: Message, authentication_log: AuthenticationLog
) -> None:
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
        url_for("settings.profile"),
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
        url_for("settings.profile"),
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
        url_for("settings.branding"),
        data=form_to_data(UpdateBrandPrimaryColorForm(data={"brand_primary_hex_color": color})),
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

    setting = db.session.get(OrganizationSetting, OrganizationSetting.BRAND_PRIMARY_COLOR)
    assert setting is not None
    assert setting.value == color


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_brand_app_name(client: FlaskClient, admin: User) -> None:
    name = "h4cK3rZ"
    resp = client.post(
        url_for("settings.branding"),
        data=form_to_data(UpdateBrandAppNameForm(data={"brand_app_name": name})),
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

    setting = db.session.get(OrganizationSetting, OrganizationSetting.BRAND_NAME)
    assert setting is not None
    assert setting.value == name


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_brand_logo(client: FlaskClient, admin: User) -> None:
    # 1x1 pixel white png
    png = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQIW2P4DwQACfsD/Z8fLAAAAAAASUVORK5CYII="
    )

    resp = client.post(
        url_for("settings.branding"),
        data={
            "logo": (BytesIO(png), "wat.png"),
            UpdateBrandLogoForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "Brand logo updated successfully" in resp.text

    soup = BeautifulSoup(resp.text, "html.parser")
    imgs = soup.select("header img")
    assert imgs  # sensibility check
    logo_url = url_for("storage.public", path=OrganizationSetting.BRAND_LOGO_VALUE)
    for img in imgs:
        if img.attrs.get("src") == logo_url:
            break
    else:
        pytest.fail("Brand logo not updated in header <img>")

    setting = db.session.get(OrganizationSetting, OrganizationSetting.BRAND_LOGO)
    assert setting is not None
    assert setting.value == OrganizationSetting.BRAND_LOGO_VALUE

    # check the file got uploaded and is accessible
    resp = client.get(logo_url, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.data == png

    resp = client.post(
        url_for("settings.branding"),
        data=form_to_data(DeleteBrandLogoForm()),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Brand logo deleted" in resp.text

    # check the file is not accessible
    resp = client.get(logo_url, follow_redirects=True)
    assert resp.status_code == 404


@pytest.mark.usefixtures("_authenticated_admin")
def test_enable_disable_guidance(client: FlaskClient, admin: User) -> None:
    # Enable guidance
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "show_user_guidance": True,
            UserGuidanceForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "User guidance enabled" in resp.text

    # Check that it's enabled in org settings
    assert OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_ENABLED) is True

    # Check that the guidance settings are show
    resp = client.get(url_for("settings.guidance"))
    assert resp.status_code == 200
    assert "Prompt Content" in resp.text

    # Disable guidance
    resp = client.post(
        url_for("settings.guidance"),
        data={
            UserGuidanceForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "User guidance disabled" in resp.text

    # Check that it's disabled in org settings
    assert OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_ENABLED) is False

    # Check that the guidance settings are not shown
    resp = client.get(url_for("settings.guidance"))
    assert resp.status_code == 200
    assert "Prompt Content" not in resp.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_guidance_emergency_exit(client: FlaskClient, admin: User) -> None:
    # Enable guidance
    client.post(
        url_for("settings.guidance"),
        data={
            "show_user_guidance": True,
            UserGuidanceForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Update exit button
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "exit_button_text": "wikipedia!",
            "exit_button_link": "https://wikipedia.org",
            UserGuidanceEmergencyExitForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "Emergency exit button updated successfully" in resp.text

    # Check that it's updated in org settings
    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT) == "wikipedia!"
    )
    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK)
        == "https://wikipedia.org"
    )


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_guidance_emergency_exit_requires_url(client: FlaskClient, admin: User) -> None:
    # Enable guidance
    client.post(
        url_for("settings.guidance"),
        data={
            "show_user_guidance": True,
            UserGuidanceForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Update exit button with invalid link
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "exit_button_text": "foo",
            "exit_button_link": "bar",
            UserGuidanceEmergencyExitForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400

    # Check that it's not updated in org settings
    assert OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_EXIT_BUTTON_TEXT) != "foo"
    assert OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_EXIT_BUTTON_LINK) != "bar"


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_guidance_prompts(client: FlaskClient, admin: User) -> None:
    # Enable guidance
    client.post(
        url_for("settings.guidance"),
        data={
            "show_user_guidance": True,
            UserGuidanceForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Update the first prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "heading_text": "prompt 1",
            "prompt_text": "prompt 1",
            "index": 0,
            UserGuidancePromptContentForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    # Check that it's updated in org settings
    assert len(OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_PROMPTS)) == 1

    # Add a new prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            UserGuidanceAddPromptForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Check that it's updated in org settings
    assert len(OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_PROMPTS)) == 2

    # Update the second prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "heading_text": "prompt 2",
            "prompt_text": "prompt 2",
            "index": 1,
            UserGuidancePromptContentForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    # Add a new prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            UserGuidanceAddPromptForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Update the third prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "heading_text": "prompt 3",
            "prompt_text": "prompt 3",
            "index": 2,
            UserGuidancePromptContentForm.submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200

    # Check that it's updated in org settings
    prompts = OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_PROMPTS)
    assert len(prompts) == 3
    assert prompts[0]["heading_text"] == "prompt 1"
    assert prompts[1]["heading_text"] == "prompt 2"
    assert prompts[2]["heading_text"] == "prompt 3"

    # Delete the second prompt
    resp = client.post(
        url_for("settings.guidance"),
        data={
            "index": 1,
            UserGuidancePromptContentForm.delete_submit.name: "",
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )

    # Check that it's updated in org settings
    prompts = OrganizationSetting.fetch_one(OrganizationSetting.GUIDANCE_PROMPTS)
    assert len(prompts) == 2
    assert prompts[0]["heading_text"] == "prompt 1"
    assert prompts[1]["heading_text"] == "prompt 3"


@pytest.mark.usefixtures("_authenticated_admin")
def test_diretory_intro_text(client: FlaskClient, admin: User) -> None:
    alert = "<script>alert(1)</stript>"
    uuid = str(uuid4())
    data = alert + " " + uuid
    resp = client.post(
        url_for("settings.branding"),
        data={
            "markdown": data,
            UpdateDirectoryTextForm.submit.name: "",
        },
    )
    assert resp.status_code == 200
    assert "Directory intro text updated" in resp.text

    val = OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT)
    assert val == data

    resp = client.get(url_for("directory"))
    assert resp.status_code == 200
    assert uuid in resp.text
    assert alert not in resp.text
    assert "&lt;script&gt;" in resp.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_directory_intro_text_reset_to_default(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hushline.settings.branding.UpdateDirectoryTextForm.validate",
        lambda *_a, **_k: True,
    )
    OrganizationSetting.upsert(OrganizationSetting.DIRECTORY_INTRO_TEXT, "to be cleared")
    db.session.commit()

    resp = client.post(
        url_for("settings.branding"),
        data={"markdown": "   ", UpdateDirectoryTextForm.submit.name: ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Directory intro text was reset to defaults" in resp.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.DIRECTORY_INTRO_TEXT) is None


@pytest.mark.usefixtures("_authenticated_admin")
def test_directory_intro_text_reset_aborts_when_multiple_rows_would_delete(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hushline.settings.branding.UpdateDirectoryTextForm.validate",
        lambda *_a, **_k: True,
    )

    class _Result:
        rowcount = 2

    monkeypatch.setattr(
        "hushline.settings.branding.db.session.execute", lambda *_a, **_k: _Result()
    )

    resp = client.post(
        url_for("settings.branding"),
        data={"markdown": "", UpdateDirectoryTextForm.submit.name: ""},
        follow_redirects=False,
    )
    assert resp.status_code == 503


@pytest.mark.usefixtures("_authenticated_admin")
def test_homepage_user(client: FlaskClient, user: User, admin: User) -> None:
    resp = client.post(
        url_for("settings.branding"),
        data={
            "username": user.primary_username.username,
            SetHomepageUsernameForm.submit.name: "",
        },
    )
    assert resp.status_code == 200
    assert "Homepage set to user " in resp.text

    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.HOMEPAGE_USER_NAME)
        == user.primary_username.username
    )

    # "log out" the user
    with client.session_transaction() as session:
        session.clear()

    resp = client.get(url_for("index"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == url_for("profile", username=user.primary_username.username)

    # "log in" the user to make the change
    with client.session_transaction() as session:
        session["user_id"] = admin.id
        session["username"] = admin.primary_username.username
        session["is_authenticated"] = True

    resp = client.post(
        url_for("settings.branding"),
        data={
            SetHomepageUsernameForm.delete_submit.name: "",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Homepage reset to default" in resp.text

    assert OrganizationSetting.fetch_one(OrganizationSetting.HOMEPAGE_USER_NAME) is None

    # "log out" the user
    with client.session_transaction() as session:
        session.clear()

    resp = client.get(url_for("index"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == url_for("directory")


@pytest.mark.usefixtures("_authenticated_admin")
def test_homepage_reset_when_already_default(client: FlaskClient) -> None:
    resp = client.post(
        url_for("settings.branding"),
        data={SetHomepageUsernameForm.delete_submit.name: ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Homepage reset to default" in resp.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_homepage_reset_multiple_rows_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Result:
        rowcount = 2

    monkeypatch.setattr(
        "hushline.settings.branding.db.session.execute", lambda *_a, **_k: _Result()
    )

    resp = client.post(
        url_for("settings.branding"),
        data={SetHomepageUsernameForm.delete_submit.name: ""},
        follow_redirects=True,
    )
    assert resp.status_code == 500
    assert "setting could not reset" in resp.text


@pytest.mark.usefixtures("_authenticated_user")
def test_index_clears_invalid_session_user(client: FlaskClient) -> None:
    with client.session_transaction() as session:
        session["user_id"] = 999999
        session["is_authenticated"] = True

    resp = client.get(url_for("index"), follow_redirects=True)
    assert resp.status_code == 200
    assert "User not found. Please log in again." in resp.text


def test_index_warns_when_homepage_username_missing(client: FlaskClient, user: User) -> None:
    OrganizationSetting.upsert(OrganizationSetting.HOMEPAGE_USER_NAME, "missing-user")
    db.session.commit()

    resp = client.get(url_for("index"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == url_for("directory")


@pytest.mark.usefixtures("_authenticated_user")
def test_index_redirects_authenticated_user_to_inbox(client: FlaskClient) -> None:
    resp = client.get(url_for("index"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == url_for("inbox")


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_profile_header(client: FlaskClient, admin: User) -> None:
    template_str = "{{ display_name_or_username }} {{ display_name }} {{ username }}"
    resp = client.post(
        url_for("settings.branding"),
        data={
            "template": template_str,
            UpdateProfileHeaderForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Profile header template updated successfully" in resp.text
    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE)
        == template_str
    )

    resp = client.post(
        url_for("settings.branding"),
        data={
            "template": "{{ INVALID SYNAX AHHHH !!!! }}",
            UpdateProfileHeaderForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 400
    assert "Your submitted form could not be processed" in resp.text
    assert (
        OrganizationSetting.fetch_one(OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE)
        == template_str
    )

    resp = client.post(
        url_for("settings.branding"),
        data={
            "template": "",
            UpdateProfileHeaderForm.submit.name: "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Profile header template reset to default" in resp.text
    assert (
        db.session.scalars(
            db.select(OrganizationSetting).filter_by(
                key=OrganizationSetting.BRAND_PROFILE_HEADER_TEMPLATE
            )
        ).one_or_none()
        is None
    )


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_profile_header_reset_when_already_default(client: FlaskClient) -> None:
    resp = client.post(
        url_for("settings.branding"),
        data={"template": "", UpdateProfileHeaderForm.submit.name: ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Profile header template reset to default" in resp.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_update_profile_header_reset_multiple_rows_error(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Result:
        rowcount = 2

    monkeypatch.setattr(
        "hushline.settings.branding.db.session.execute", lambda *_a, **_k: _Result()
    )

    resp = client.post(
        url_for("settings.branding"),
        data={"template": "", UpdateProfileHeaderForm.submit.name: ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_fields_enabled(client: FlaskClient, app: Flask, user: User) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.ALWAYS
    resp = client.get(url_for("settings.profile_fields"))
    assert resp.status_code == 302


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_fields_disabled(client: FlaskClient, app: Flask, user: User) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.PREMIUM
    resp = client.get(url_for("settings.profile_fields"))
    assert resp.status_code == 401


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_fields_enabled(
    client: FlaskClient, app: Flask, user: User, user_alias: Username
) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.ALWAYS
    resp = client.get(url_for("settings.alias_fields", username_id=user_alias.id))
    assert resp.status_code == 302


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_fields_disabled(
    client: FlaskClient, app: Flask, user: User, user_alias: Username
) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.PREMIUM
    resp = client.get(url_for("settings.alias_fields", username_id=user_alias.id))
    assert resp.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin")
def test_hide_donate_button(client: FlaskClient, app: Flask, admin: User) -> None:
    # precondition
    setting = OrganizationSetting.query.filter_by(
        key=OrganizationSetting.HIDE_DONATE_BUTTON
    ).one_or_none()
    assert setting is None or setting.value is False

    resp = client.post(
        url_for("settings.branding"),
        data={"hide_button": True, ToggleDonateButtonForm.submit.name: ""},
    )
    assert resp.status_code == 200
    assert "Donate button set to hidden" in resp.text, resp.text

    setting = OrganizationSetting.query.filter_by(key=OrganizationSetting.HIDE_DONATE_BUTTON).one()
    assert setting.value is True

    resp = client.post(url_for("settings.branding"), data={ToggleDonateButtonForm.submit.name: ""})
    assert resp.status_code == 200
    assert "Donate button set to visible" in resp.text, resp.text

    setting = OrganizationSetting.query.filter_by(key=OrganizationSetting.HIDE_DONATE_BUTTON).one()
    assert setting.value is False


@pytest.mark.usefixtures("_authenticated_user")
def test_encryption_post_invalid_form_returns_400(client: FlaskClient, app: Flask) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(url_for("settings.encryption"), data={}, follow_redirects=False)
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_route_missing_alias_returns_404(client: FlaskClient) -> None:
    response = client.get(url_for("settings.alias", username_id=999999), follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_user")
def test_delete_alias_missing_alias_returns_404(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.delete_alias", username_id=999999), follow_redirects=False
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_fields_missing_alias_redirects_index(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.alias_fields", username_id=999999), follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.aliases"))


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_route_invalid_post_returns_400(
    client: FlaskClient, app: Flask, user_alias: Username
) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data={},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_alias_fields_post_uses_handle_field_post_result(
    client: FlaskClient, app: Flask, user_alias: Username, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.ALWAYS
    monkeypatch.setattr(
        "hushline.settings.aliases.handle_field_post",
        lambda _alias: ("handled", 201),
    )
    response = client.post(
        url_for("settings.alias_fields", username_id=user_alias.id),
        data={"any": "value"},
        follow_redirects=False,
    )
    assert response.status_code == 201


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_route_raises_if_primary_username_missing(client: FlaskClient, user: User) -> None:
    user.primary_username.is_primary = False
    db.session.commit()

    response = client.get(url_for("settings.profile"), follow_redirects=False)
    assert response.status_code == 500


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_fields_raises_if_primary_username_missing(client: FlaskClient, user: User) -> None:
    user.primary_username.is_primary = False
    db.session.commit()

    response = client.get(url_for("settings.profile_fields"), follow_redirects=False)
    assert response.status_code == 500


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_invalid_post_returns_400(client: FlaskClient, app: Flask) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post(url_for("settings.profile"), data={}, follow_redirects=False)
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_renders_business_price_with_two_decimals(client: FlaskClient) -> None:
    business_tier = db.session.scalars(db.select(Tier).filter_by(name="Business")).one()
    business_tier.monthly_amount = 2055
    db.session.commit()
    response = client.get(url_for("settings.profile"), follow_redirects=False)
    assert response.status_code == 200
    assert "$20.55/mo to unlock more features!" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_fields_post_uses_handle_field_post_result(
    client: FlaskClient, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.config["FIELDS_MODE"] = FieldsMode.ALWAYS
    monkeypatch.setattr(
        "hushline.settings.profile.handle_field_post",
        lambda _username: ("handled", 202),
    )
    response = client.post(
        url_for("settings.profile_fields"),
        data={"any": "value"},
        follow_redirects=False,
    )
    assert response.status_code == 202

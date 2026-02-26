import pyotp
import pytest
from flask import url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.db import db
from hushline.model import User


@pytest.mark.usefixtures("_authenticated_user")
def test_toggle_2fa_redirects_to_enable_when_not_configured(client: FlaskClient) -> None:
    response = client.post(url_for("settings.toggle_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.enable_2fa"))


@pytest.mark.usefixtures("_authenticated_user")
def test_toggle_2fa_redirects_to_disable_when_already_configured(
    client: FlaskClient, user: User
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()

    response = client.post(url_for("settings.toggle_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.disable_2fa"))


def test_toggle_2fa_redirects_to_login_without_user_id(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess.pop("user_id", None)
        sess.pop("username", None)

    response = client.post(url_for("settings.toggle_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_disable_2fa_clears_secret(client: FlaskClient, user: User) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()

    response = client.post(url_for("settings.disable_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.auth"))
    db.session.refresh(user)
    assert user.totp_secret is None


def test_disable_2fa_redirects_to_login_without_user_id(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["is_authenticated"] = True
        sess.pop("user_id", None)
        sess.pop("username", None)

    response = client.post(url_for("settings.disable_2fa"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_confirm_disable_2fa_page_loads(client: FlaskClient) -> None:
    response = client.get(url_for("settings.confirm_disable_2fa"), follow_redirects=True)
    assert response.status_code == 200
    assert "Are you sure" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_setup_redirects_to_login_for_missing_user(
    client: FlaskClient, user: User, mocker: MockFixture
) -> None:
    # Simulate a race where auth succeeds but the user lookup inside the route misses.
    mocker.patch("hushline.auth.get_session_user", return_value=user)
    mocker.patch("hushline.settings.twofa.db.session.get", return_value=None)

    response = client.post(
        url_for("settings.verify_2fa_setup"),
        data={"verification_code": "000000"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_setup_without_totp_secret_redirects_back_to_enable(
    client: FlaskClient, user: User
) -> None:
    user.totp_secret = None
    db.session.commit()

    response = client.post(
        url_for("settings.verify_2fa_setup"),
        data={"verification_code": "000000"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.enable_2fa"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_setup_invalid_code_redirects_back_to_enable(
    client: FlaskClient, user: User
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()

    response = client.post(
        url_for("settings.verify_2fa_setup"),
        data={"verification_code": "000000"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("settings.enable_2fa"))


@pytest.mark.usefixtures("_authenticated_user")
def test_verify_2fa_setup_valid_code_redirects_logout_and_clears_setup_flag(
    client: FlaskClient, user: User
) -> None:
    user.totp_secret = pyotp.random_base32()
    db.session.commit()
    valid_code = pyotp.TOTP(user.totp_secret).now()

    with client.session_transaction() as sess:
        sess["is_setting_up_2fa"] = True

    response = client.post(
        url_for("settings.verify_2fa_setup"),
        data={"verification_code": valid_code},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("logout"))
    with client.session_transaction() as sess:
        assert "is_setting_up_2fa" not in sess

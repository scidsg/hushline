from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def _load_test_pgp_key() -> str:
    return Path("tests/test_pgp_key.txt").read_text()


def _set_all_onboarding_values_complete(user: User) -> None:
    user.onboarding_complete = True
    user.primary_username.display_name = "Test User"
    user.primary_username.bio = "Short bio"
    user.primary_username.show_in_directory = True
    user.pgp_key = _load_test_pgp_key()
    user.enable_email_notifications = True
    user.email_include_message_content = True
    user.email_encrypt_entire_body = True
    user.email = "test@example.com"


def _run_onboarding_flow_through_step_four(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "profile", "display_name": "Test User", "bio": "Short bio"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding", step="encryption"))

    response = client.get(url_for("onboarding", step="encryption"))
    assert response.status_code == 200
    assert "Step 2 of 4" in response.text
    assert "Now, let's set up encryption" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "manual", "pgp_key": _load_test_pgp_key()},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding", step="notifications"))

    response = client.get(url_for("onboarding", step="notifications"))
    assert response.status_code == 200
    assert "Step 3 of 4" in response.text
    assert "Where should we send new tips?" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "test@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding", step="directory"))

    response = client.get(url_for("onboarding", step="directory"))
    assert response.status_code == 200
    assert "Step 4 of 4" in response.text
    assert "Finally, join the User Directory!" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "directory", "show_in_directory": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "🎉 Congratulations! Your account setup is complete!" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_flow(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = False
    db.session.commit()

    response = client.get(url_for("onboarding"))
    assert response.status_code == 200
    assert "First, tell us about yourself" in response.text
    assert '<span class="bio-count">0</span>/250' in response.text

    _run_onboarding_flow_through_step_four(client)
    db.session.refresh(user)
    assert user.onboarding_complete is True
    assert user.enable_email_notifications is True
    assert user.email_include_message_content is True
    assert user.email_encrypt_entire_body is True
    assert user.email == "test@example.com"
    assert user.primary_username.show_in_directory is True


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_skip(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = False
    db.session.commit()

    response = client.post(url_for("onboarding_skip"), follow_redirects=True)
    assert response.status_code == 200

    db.session.refresh(user)
    assert user.onboarding_complete is True


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.routes.onboarding.can_encrypt_with_pgp_key", return_value=True)
@patch("hushline.routes.onboarding.is_valid_pgp_key", return_value=True)
@patch("hushline.routes.onboarding.requests.get")
def test_onboarding_proton_search_prefills_manual_key(
    requests_get: MagicMock,
    is_valid_pgp_key: MagicMock,
    can_encrypt_with_pgp_key: MagicMock,
    client: FlaskClient,
) -> None:
    test_key = _load_test_pgp_key()
    requests_get.return_value.status_code = 200
    requests_get.return_value.text = test_key
    is_valid_pgp_key.return_value = True
    can_encrypt_with_pgp_key.return_value = True

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "proton", "email": "user@proton.me"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Now, let's set up encryption" in response.text
    assert "BEGIN PGP PUBLIC KEY BLOCK" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@pytest.mark.parametrize(
    "incomplete_field",
    [
        "display_name",
        "bio",
        "pgp_key",
        "enable_email_notifications",
        "email_include_message_content",
        "email_encrypt_entire_body",
        "email",
        "show_in_directory",
    ],
)
def test_onboarding_requires_all_steps_when_any_value_incomplete(
    client: FlaskClient, user: User, incomplete_field: str
) -> None:
    _set_all_onboarding_values_complete(user)

    if incomplete_field == "display_name":
        user.primary_username.display_name = None
    elif incomplete_field == "bio":
        user.primary_username.bio = None
    elif incomplete_field == "pgp_key":
        user.pgp_key = None
    elif incomplete_field == "enable_email_notifications":
        user.enable_email_notifications = False
    elif incomplete_field == "email_include_message_content":
        user.email_include_message_content = False
    elif incomplete_field == "email_encrypt_entire_body":
        user.email_encrypt_entire_body = False
    elif incomplete_field == "email":
        user.email = None
    elif incomplete_field == "show_in_directory":
        user.primary_username.show_in_directory = False
    else:
        raise AssertionError(f"Unhandled field case: {incomplete_field}")

    db.session.commit()

    response = client.get(url_for("inbox"), follow_redirects=True)
    assert response.status_code == 200
    assert "Account Setup" in response.text

    response = client.get(url_for("onboarding"))
    assert response.status_code == 200
    assert "First, tell us about yourself" in response.text

    _run_onboarding_flow_through_step_four(client)


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_redirects_to_inbox_when_already_complete(
    client: FlaskClient, user: User
) -> None:
    _set_all_onboarding_values_complete(user)
    db.session.commit()

    response = client.get(url_for("onboarding"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_handles_missing_primary_username(client: FlaskClient, user: User) -> None:
    user.primary_username.is_primary = False
    db.session.commit()

    response = client.get(url_for("onboarding"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("inbox"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_encryption_unknown_method_returns_bad_request(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "not-a-method"},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_encryption_manual_invalid_key_shows_error(client: FlaskClient) -> None:
    with patch("hushline.routes.onboarding.is_valid_pgp_key", return_value=False):
        response = client.post(
            url_for("onboarding"),
            data={"step": "encryption", "method": "manual", "pgp_key": "not-a-key"},
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert "Invalid PGP key format or import failed." in response.text


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.routes.onboarding.requests.get")
def test_onboarding_proton_fetch_failure_shows_error(
    requests_get: MagicMock, client: FlaskClient
) -> None:
    requests_get.side_effect = requests.exceptions.RequestException("network error")

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "proton", "email": "user@proton.me"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Error fetching PGP key from Proton Mail." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_notifications_requires_pgp_key(client: FlaskClient, user: User) -> None:
    user.pgp_key = None
    db.session.commit()

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "tips@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Add a PGP key before enabling notifications." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_missing_user_redirects_login(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = 999999
        sess["is_authenticated"] = True
        sess["username"] = "missing"

    response = client.get(url_for("onboarding"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_invalid_step_defaults_to_profile(client: FlaskClient) -> None:
    response = client.get(url_for("onboarding", step="nope-step"))
    assert response.status_code == 200
    assert "First, tell us about yourself" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_post_invalid_step_defaults_to_profile(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "not-a-step", "display_name": "Test User", "bio": "Short bio"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding", step="encryption"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_profile_invalid_form_returns_400(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "profile", "display_name": "", "bio": "bio"},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_encryption_proton_invalid_form_returns_400(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "proton", "email": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.routes.onboarding.can_encrypt_with_pgp_key", return_value=False)
@patch("hushline.routes.onboarding.is_valid_pgp_key", return_value=True)
@patch("hushline.routes.onboarding.requests.get")
def test_onboarding_proton_key_without_encryption_subkey_returns_400(
    requests_get: MagicMock,
    is_valid_pgp_key: MagicMock,
    can_encrypt_with_pgp_key: MagicMock,
    client: FlaskClient,
) -> None:
    _ = (is_valid_pgp_key, can_encrypt_with_pgp_key)
    requests_get.return_value.status_code = 200
    requests_get.return_value.text = _load_test_pgp_key()

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "proton", "email": "user@proton.me"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "cannot be used for encryption" in response.text


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.routes.onboarding.is_valid_pgp_key", return_value=False)
@patch("hushline.routes.onboarding.requests.get")
def test_onboarding_proton_no_key_found_returns_400(
    requests_get: MagicMock, is_valid_pgp_key: MagicMock, client: FlaskClient
) -> None:
    _ = is_valid_pgp_key
    requests_get.return_value.status_code = 200
    requests_get.return_value.text = "not-a-key"

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "proton", "email": "user@proton.me"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "No PGP key found for that email address." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_encryption_manual_missing_key_returns_400(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "manual", "pgp_key": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_encryption_manual_invalid_form_returns_400_with_csrf(
    app: Flask, client: FlaskClient
) -> None:
    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("onboarding"),
            data={"step": "encryption", "method": "manual", "pgp_key": _load_test_pgp_key()},
            follow_redirects=False,
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
@patch("hushline.routes.onboarding.can_encrypt_with_pgp_key", return_value=False)
@patch("hushline.routes.onboarding.is_valid_pgp_key", return_value=True)
def test_onboarding_encryption_manual_non_encryptable_key_returns_400(
    is_valid_pgp_key: MagicMock, can_encrypt_with_pgp_key: MagicMock, client: FlaskClient
) -> None:
    _ = (is_valid_pgp_key, can_encrypt_with_pgp_key)
    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "manual", "pgp_key": _load_test_pgp_key()},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "cannot be used for encryption" in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_notifications_invalid_form_returns_400(client: FlaskClient, user: User) -> None:
    user.pgp_key = _load_test_pgp_key()
    db.session.commit()

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_directory_invalid_form_returns_400_with_csrf(
    app: Flask, client: FlaskClient
) -> None:
    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(
            url_for("onboarding"), data={"step": "directory"}, follow_redirects=False
        )
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_unknown_step_post_returns_400(client: FlaskClient) -> None:
    response = client.post(
        url_for("onboarding"), data={"step": "unknown-step"}, follow_redirects=False
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_directory_redirects_to_select_tier_when_stripe_enabled(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    user.tier_id = None
    db.session.commit()

    response = client.post(
        url_for("onboarding"),
        data={"step": "directory", "show_in_directory": "y"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("premium.select_tier"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_skip_missing_user_redirects_login(client: FlaskClient) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = 999999
        sess["is_authenticated"] = True
        sess["username"] = "missing"

    response = client.post(url_for("onboarding_skip"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_skip_invalid_form_redirects_onboarding_with_csrf(
    app: Flask, client: FlaskClient
) -> None:
    prior = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post(url_for("onboarding_skip"), follow_redirects=False)
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("onboarding"))


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_skip_redirects_to_select_tier_when_enabled(
    app: Flask, client: FlaskClient, user: User
) -> None:
    app.config["STRIPE_SECRET_KEY"] = "sk_test_123"
    user.tier_id = None
    db.session.commit()

    response = client.post(url_for("onboarding_skip"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("premium.select_tier"))

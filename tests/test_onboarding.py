from pathlib import Path

import pytest
from flask import url_for
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
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Now, let's set up encryption" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "manual", "pgp_key": _load_test_pgp_key()},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Finally, where should we send new tips?" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "test@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "One last thing: join the User Directory?" in response.text

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

    response = client.post(
        url_for("onboarding"),
        data={"step": "profile", "display_name": "Test User", "bio": "Short bio"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Now, let's set up encryption" in response.text
    response = client.post(
        url_for("onboarding"),
        data={"step": "encryption", "method": "manual", "pgp_key": _load_test_pgp_key()},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Finally, where should we send new tips?" in response.text
    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "test@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "One last thing: join the User Directory?" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "directory", "show_in_directory": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "🎉 Congratulations! Your account setup is complete!" in response.text
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

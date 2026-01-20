from pathlib import Path

import pytest

from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def _load_test_pgp_key() -> str:
    return Path("tests/test_pgp_key.txt").read_text()


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_flow(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = False
    db.session.commit()

    response = client.get(url_for("onboarding"))
    assert response.status_code == 200
    assert "First, tell us a little about yourself!" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "profile", "display_name": "Test User", "bio": "Short bio"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Next, let's secure your account." in response.text

    response = client.post(
        url_for("onboarding"),
        data={
            "step": "encryption",
            "method": "manual",
            "pgp_key": _load_test_pgp_key(),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Where should we send new tips?" in response.text

    response = client.post(
        url_for("onboarding"),
        data={"step": "notifications", "email_address": "test@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(user)
    assert user.onboarding_complete is True
    assert user.enable_email_notifications is True
    assert user.email_include_message_content is True
    assert user.email_encrypt_entire_body is True
    assert user.email == "test@example.com"


@pytest.mark.usefixtures("_authenticated_user")
def test_onboarding_skip(client: FlaskClient, user: User) -> None:
    user.onboarding_complete = False
    db.session.commit()

    response = client.post(url_for("onboarding_skip"), follow_redirects=True)
    assert response.status_code == 200

    db.session.refresh(user)
    assert user.onboarding_complete is True

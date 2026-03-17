import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import InviteCode, OrganizationSetting
from hushline.settings.registration import (
    CreateInviteCodeForm,
    DeleteInviteCodeForm,
    ToggleRegistrationCodesForm,
    ToggleRegistrationForm,
)


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_settings_disabled_returns_unauthorized(
    app: Flask, client: FlaskClient
) -> None:
    app.config["REGISTRATION_SETTINGS_ENABLED"] = False
    response = client.get(url_for("settings.registration"), follow_redirects=False)
    assert response.status_code == 401


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_toggle_enabled(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.registration"),
        data={"registration_enabled": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration enabled." in response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_ENABLED) is True


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_toggle_enabled_does_not_validate_other_forms(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_validate(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("unexpected form validation")

    monkeypatch.setattr(ToggleRegistrationCodesForm, "validate", fail_validate)
    monkeypatch.setattr(CreateInviteCodeForm, "validate", fail_validate)
    monkeypatch.setattr(DeleteInviteCodeForm, "validate", fail_validate)

    response = client.post(
        url_for("settings.registration"),
        data={"registration_enabled": "y"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "👍 Registration enabled." in response.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_toggle_codes_required(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.registration"),
        data={"registration_codes_required": "y"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Registration codes required." in response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.REGISTRATION_CODES_REQUIRED) is True


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_create_invite_code(client: FlaskClient) -> None:
    before_count = db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) or 0
    response = client.post(
        url_for("settings.registration"),
        data={"create_invite_code": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "👍 Invite code " in response.text
    after_count = db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) or 0
    assert after_count == before_count + 1


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_delete_invite_code(client: FlaskClient) -> None:
    invite = InviteCode()
    db.session.add(invite)
    db.session.commit()

    response = client.post(
        url_for("settings.registration"),
        data={"delete_invite_code": "", "invite_code_id": str(invite.id)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert f"👍 Invite code {invite.code} deleted." in response.text
    assert db.session.get(InviteCode, invite.id) is None


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_delete_invite_code_not_found(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.registration"),
        data={"delete_invite_code": "", "invite_code_id": "999999"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "⛔️ Invite code not found." in response.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_invalid_form_submission(client: FlaskClient) -> None:
    response = client.post(
        url_for("settings.registration"),
        data={"unrelated_field": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "⛔️ Invalid form submission." in response.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_invalid_delete_submission_preserves_redirect_and_flash(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_validate(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("unexpected form validation")

    monkeypatch.setattr(ToggleRegistrationForm, "validate", fail_validate)
    monkeypatch.setattr(ToggleRegistrationCodesForm, "validate", fail_validate)
    monkeypatch.setattr(CreateInviteCodeForm, "validate", fail_validate)

    response = client.post(
        url_for("settings.registration"),
        data={"delete_invite_code": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "⛔️ Invalid form submission." in response.text


@pytest.mark.usefixtures("_authenticated_admin")
def test_registration_missing_csrf_redirects_with_invalid_submission_flash(
    app: Flask, client: FlaskClient
) -> None:
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True

    try:
        before_count = db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) or 0

        response = client.post(
            url_for("settings.registration"),
            data={"create_invite_code": ""},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith(url_for("settings.registration"))
        after_count = db.session.scalar(db.select(db.func.count()).select_from(InviteCode)) or 0
        assert after_count == before_count
        with client.session_transaction() as session:
            assert ["message", "⛔️ Invalid form submission."] in session.get("_flashes", [])
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting

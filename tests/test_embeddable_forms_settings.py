from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from hushline.db import db
from hushline.model import Message, OrganizationSetting, User, Username


def _make_message_capable(user: User) -> None:
    with open("tests/test_pgp_key.txt") as file:
        user.pgp_key = file.read().strip()
    db.session.commit()


def _enable_embeds_globally() -> None:
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)
    db.session.commit()


def _configure_embed(username: Username, origin: str = "https://tips.example") -> None:
    username.embed_enabled = True
    username.set_embed_allowed_origins([origin])
    db.session.commit()


def _assert_safe_embed_denial(response: TestResponse) -> None:
    assert response.status_code == 404
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


def _embed_settings_data(enabled: bool, origins: str) -> dict[str, str]:
    data = {
        "embed_allowed_origins": origins,
        "update_embed_settings": "",
    }
    if enabled:
        data["embed_enabled"] = "y"
    return data


def _iframe_from_snippet(response_text: str) -> BeautifulSoup:
    page = BeautifulSoup(response_text, "html.parser")
    snippet = page.find("textarea", id="embed_iframe_snippet")
    assert snippet is not None
    snippet_text = snippet.get_text()
    assert "<script" not in snippet_text.lower()
    return BeautifulSoup(snippet_text, "html.parser")


def _embed_submission_data(response_text: str) -> dict[str, str]:
    page = BeautifulSoup(response_text, "html.parser")
    label = page.find("label", attrs={"for": "captcha_answer"})
    assert label is not None
    left, right = label.get_text(strip=True).replace("=", "").split("+")

    data = {"captcha_answer": str(int(left.strip()) + int(right.strip()))}
    for name in ["owner_guard_nonce", "owner_guard_signature", "embed_captcha_token"]:
        field = page.find("input", attrs={"name": name})
        assert field is not None
        value = field.get("value")
        assert value
        data[name] = str(value)
    data["csrf_token"] = data["embed_captcha_token"]
    return data


def test_admin_embeddable_forms_default_disabled(client: FlaskClient, admin_user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = admin_user.id
        session["session_id"] = admin_user.session_id
        session["username"] = admin_user.primary_username.username
        session["is_authenticated"] = True

    response = client.get(url_for("settings.admin"))

    assert response.status_code == 200
    assert OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED) is False
    assert "Enable Embeds" in response.text
    assert "Disable Embeds" not in response.text


def test_embed_profile_route_is_disabled_by_default(client: FlaskClient, user: User) -> None:
    _make_message_capable(user)
    _configure_embed(user.primary_username)

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_denies_profile_opted_out(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.set_embed_allowed_origins(["https://tips.example"])
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_denies_missing_origin_allowlist(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.embed_enabled = True
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_denies_missing_recipient_key(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _configure_embed(user.primary_username)

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_denies_suspended_target(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username)
    user.is_suspended = True
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_denies_unknown_target(client: FlaskClient) -> None:
    response = client.get(url_for("embed_profile", username="does-not-exist"))

    _assert_safe_embed_denial(response)


def test_embed_profile_route_supports_alias(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user_alias, "https://alias.example")

    response = client.get(url_for("embed_profile", username=user_alias.username))

    assert response.status_code == 200
    assert f"@{user_alias.username}" in response.text
    assert "frame-ancestors https://alias.example" in response.headers["Content-Security-Policy"]


def test_embed_profile_submission_does_not_require_session_cookie(
    app: Flask,
    client: FlaskClient,
    user: User,
) -> None:
    prior_csrf_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        _enable_embeds_globally()
        _make_message_capable(user)
        _configure_embed(user.primary_username)

        response = client.get(url_for("embed_profile", username=user.primary_username.username))

        assert response.status_code == 200
        assert 'name="csrf_token"' in response.text
        with client.session_transaction() as session:
            assert "math_answer" not in session
            assert "math_problem" not in session

        submission_data = _embed_submission_data(response.text)
        with app.test_client() as cross_site_client:
            post_response = cross_site_client.post(
                url_for("embed_profile", username=user.primary_username.username),
                data={
                    "field_0": "Embedded Signal contact",
                    "field_1": "Embedded sessionless message",
                    **submission_data,
                },
            )

        assert post_response.status_code == 200, post_response.text
        assert "Message Submitted!" in post_response.text

        message = db.session.scalars(
            db.select(Message).filter_by(username_id=user.primary_username.id)
        ).one()
        assert len(message.field_values) == 2
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_csrf_setting


def test_embed_profile_submission_requires_embed_form_token(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username)

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200
    submission_data = _embed_submission_data(response.text)
    submission_data.pop("csrf_token")

    post_response = client.post(
        url_for("embed_profile", username=user.primary_username.username),
        data={
            "field_0": "Embedded Signal contact",
            "field_1": "Embedded message",
            **submission_data,
        },
    )

    assert post_response.status_code == 400
    assert "Invalid embed form token" in post_response.text


def test_profile_embed_settings_do_not_show_snippet_when_globally_disabled(
    client: FlaskClient, user: User
) -> None:
    _make_message_capable(user)
    _configure_embed(user.primary_username)
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.get(url_for("settings.profile"))

    assert response.status_code == 200
    assert "Embeds are disabled globally by an administrator." in response.text
    assert 'id="embed_iframe_snippet"' not in response.text


def test_admin_can_toggle_embeddable_forms(client: FlaskClient, admin_user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = admin_user.id
        session["session_id"] = admin_user.session_id
        session["username"] = admin_user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("admin.toggle_embeddable_forms"),
        data={"embeddable_forms_enabled": "true"},
    )
    assert response.status_code == 302
    assert OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED) is True

    response = client.post(
        url_for("admin.toggle_embeddable_forms"),
        data={"embeddable_forms_enabled": "false"},
    )
    assert response.status_code == 302
    assert OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED) is False


def test_non_admin_cannot_toggle_embeddable_forms(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("admin.toggle_embeddable_forms"),
        data={"embeddable_forms_enabled": "true"},
    )

    assert response.status_code == 403
    assert OrganizationSetting.fetch_one(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED) is False


def test_primary_embed_settings_update_origins_and_render_iframe_snippet(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("settings.profile"),
        data=_embed_settings_data(
            True,
            "https://Tips.Example:443\nhttps://other.example:8443",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(user.primary_username)
    assert user.primary_username.embed_enabled is True
    assert user.primary_username.embed_allowed_origins == [
        "https://tips.example",
        "https://other.example:8443",
    ]

    snippet = _iframe_from_snippet(response.text)
    iframe = snippet.find("iframe")
    assert iframe is not None
    assert iframe["src"] == url_for(
        "embed_profile",
        username=user.primary_username.username,
        _external=True,
    )
    assert f"/embed/to/{user.primary_username.username}" in iframe["src"]
    assert iframe["sandbox"] == ["allow-forms", "allow-scripts"]
    assert iframe["referrerpolicy"] == "no-referrer"
    assert iframe["title"]
    assert iframe["width"] == "100%"
    assert iframe["height"] == "700"
    assert "max-width:720px" in iframe["style"]


def test_embed_profile_template_has_compact_trust_chrome_and_form(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.display_name = "Example Recipient"
    user.primary_username.is_verified = True
    _configure_embed(user.primary_username)

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    assert response.status_code == 200
    page = BeautifulSoup(response.text, "html.parser")
    assert page.select_one("body.embed-page") is not None
    assert page.find(string="Secure Hush Line form") is not None
    assert "Hosted by" in response.text
    assert "Example Recipient" in response.text
    assert f"@{user.primary_username.username}" in response.text
    assert "Verified account" in response.text
    assert "Client-side encryption enabled" in response.text
    assert page.find("a", string=lambda value: value and "Open on Hush Line" in value) is not None
    assert page.find("label", attrs={"for": "captcha_answer"}) is not None
    assert page.find("input", attrs={"name": "csrf_token"}) is not None
    assert page.find("script", attrs={"id": "recipientPublicKeys"}) is not None
    assert page.find("label", attrs={"for": "field_0"}) is not None
    assert page.find("label", attrs={"for": "field_1"}) is not None
    script_sources = [script.get("src", "") for script in page.find_all("script")]
    assert not any("submit-message.js" in source for source in script_sources)
    assert page.find("iframe") is None
    assert "script-widget" not in response.text


def test_embed_profile_template_shows_caution_state(client: FlaskClient, user: User) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    user.primary_username.display_name = "Admin Hush Line"
    _configure_embed(user.primary_username)

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    assert response.status_code == 200
    assert "Caution advised" in response.text


def test_embed_profile_template_ignores_sender_query_values(
    client: FlaskClient, user: User
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    _configure_embed(user.primary_username)

    response = client.get(
        url_for(
            "embed_profile",
            username=user.primary_username.username,
            prefill="sender-specific-value",
            analytics_id="analytics-value",
        )
    )

    assert response.status_code == 200
    assert "sender-specific-value" not in response.text
    assert "analytics-value" not in response.text


def test_primary_embed_settings_reject_invalid_origin(client: FlaskClient, user: User) -> None:
    _make_message_capable(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("settings.profile"),
        data=_embed_settings_data(True, "https://tips.example/path"),
    )

    assert response.status_code == 400
    db.session.refresh(user.primary_username)
    assert user.primary_username.embed_enabled is False
    assert user.primary_username.embed_allowed_origins == []


def test_embed_settings_require_message_capable_owner(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("settings.profile"),
        data=_embed_settings_data(True, "https://tips.example"),
    )

    assert response.status_code == 400
    db.session.refresh(user.primary_username)
    assert user.primary_username.embed_enabled is False


def test_alias_embed_settings_are_independent(
    client: FlaskClient, user: User, user_alias: Username
) -> None:
    _enable_embeds_globally()
    _make_message_capable(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["session_id"] = user.session_id
        session["username"] = user.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data=_embed_settings_data(True, "https://alias.example"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    db.session.refresh(user.primary_username)
    db.session.refresh(user_alias)
    assert user.primary_username.embed_enabled is False
    assert user.primary_username.embed_allowed_origins == []
    assert user_alias.embed_enabled is True
    assert user_alias.embed_allowed_origins == ["https://alias.example"]

    snippet = _iframe_from_snippet(response.text)
    iframe = snippet.find("iframe")
    assert iframe is not None
    assert iframe["src"] == url_for(
        "embed_profile",
        username=user_alias.username,
        _external=True,
    )


def test_alias_embed_settings_require_alias_owner(
    client: FlaskClient, user2: User, user_alias: Username
) -> None:
    _make_message_capable(user2)
    with client.session_transaction() as session:
        session["user_id"] = user2.id
        session["session_id"] = user2.session_id
        session["username"] = user2.primary_username.username
        session["is_authenticated"] = True

    response = client.post(
        url_for("settings.alias", username_id=user_alias.id),
        data=_embed_settings_data(True, "https://alias.example"),
    )

    assert response.status_code == 404
    db.session.refresh(user_alias)
    assert user_alias.embed_enabled is False

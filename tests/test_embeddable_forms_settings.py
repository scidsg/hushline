from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import OrganizationSetting, User, Username


def _make_message_capable(user: User) -> None:
    with open("tests/test_pgp_key.txt") as file:
        user.pgp_key = file.read().strip()
    db.session.commit()


def _enable_embeds_globally() -> None:
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)
    db.session.commit()


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
    user.primary_username.embed_enabled = True
    user.primary_username.set_embed_allowed_origins(["https://tips.example"])
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))

    assert response.status_code == 404


def test_profile_embed_settings_do_not_show_snippet_when_globally_disabled(
    client: FlaskClient, user: User
) -> None:
    _make_message_capable(user)
    user.primary_username.embed_enabled = True
    user.primary_username.set_embed_allowed_origins(["https://tips.example"])
    db.session.commit()
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
    assert iframe["sandbox"] == ["allow-forms", "allow-scripts"]
    assert iframe["referrerpolicy"] == "no-referrer"
    assert iframe["title"]
    assert iframe["width"] == "100%"
    assert iframe["height"] == "700"
    assert "max-width:720px" in iframe["style"]


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

from pathlib import Path

import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

from hushline import PERMISSIONS_POLICY
from hushline.db import db
from hushline.model import (
    Conversation,
    ConversationParticipant,
    OrganizationSetting,
    StripeSubscriptionStatusEnum,
    User,
)


def _csp_directives(response_headers: Headers) -> dict[str, str]:
    csp = response_headers["Content-Security-Policy"]
    return {
        directive: sources
        for directive, sources in (
            part.strip().split(" ", 1) for part in csp.split(";") if part.strip()
        )
    }


def test_csp(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "img-src 'self' data: https:" in csp
    assert "form-action 'self'" in csp


def test_csp_form_action_allows_stripe_redirect_hosts_when_premium_enabled(
    client: FlaskClient, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "STRIPE_SECRET_KEY", "sk_test_enabled")

    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200

    directives = _csp_directives(response.headers)
    assert directives["form-action"] == (
        "'self' https://checkout.stripe.com https://billing.stripe.com"
    )


def test_csp_form_action_omits_stripe_redirect_hosts_when_premium_disabled(
    client: FlaskClient, app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "STRIPE_SECRET_KEY", "")

    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200

    directives = _csp_directives(response.headers)
    assert directives["form-action"] == "'self'"


def test_csp_script_src_elem_disallows_inline_scripts(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    csp = response.headers["Content-Security-Policy"]
    assert "script-src-elem 'self' https://js.stripe.com https://cdn.jsdelivr.net" in csp
    assert "script-src-elem 'self' 'unsafe-inline'" not in csp


def test_custom_splash_logo_keeps_csp_enforced(client: FlaskClient) -> None:
    OrganizationSetting.upsert(
        OrganizationSetting.BRAND_SPLASH_LOGO, OrganizationSetting.BRAND_SPLASH_LOGO_VALUE
    )

    response = client.get(url_for("register"), follow_redirects=True)
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "img-src 'self' data: https:" in csp
    assert "script-src-elem 'self' 'unsafe-inline'" not in csp


def test_native_pwa_startup_splash_keeps_csp_enforced(client: FlaskClient) -> None:
    response = client.get(url_for("register"), follow_redirects=True)
    assert response.status_code == 200
    assert 'rel="apple-touch-startup-image"' in response.text

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "img-src 'self' data: https:" in csp
    assert "script-src-elem 'self' 'unsafe-inline'" not in csp


def test_profile_page_keeps_csp_enforced(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "script-src-elem 'self' 'unsafe-inline'" not in csp


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_profile_keeps_frame_restrictions(client: FlaskClient) -> None:
    response = client.get(url_for("settings.profile"))
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert "frame-ancestors 'none'" in csp
    assert response.headers["X-Frame-Options"] == "DENY"


def test_embed_profile_uses_allowed_origins_for_frames_and_sandboxed_assets(
    client: FlaskClient, app: Flask, user: User
) -> None:
    app.config["PUBLIC_BASE_URL"] = "https://tips.hushline.app"
    with open("tests/test_pgp_key.txt") as file:
        user.pgp_key = file.read().strip()
    user.set_business_tier()
    user.stripe_subscription_status = StripeSubscriptionStatusEnum.ACTIVE
    user.primary_username.embed_enabled = True
    user.primary_username.set_embed_allowed_origins(
        ["https://tips.example", "https://newsroom.example:8443"]
    )
    OrganizationSetting.upsert(OrganizationSetting.EMBEDDABLE_FORMS_ENABLED, True)
    db.session.commit()

    response = client.get(url_for("embed_profile", username=user.primary_username.username))
    assert response.status_code == 200

    directives = _csp_directives(response.headers)
    assert directives["frame-ancestors"] == "https://tips.example https://newsroom.example:8443"
    assert directives["form-action"] == (
        "'self' https://checkout.stripe.com https://billing.stripe.com"
    )
    assert directives["style-src"] == "'self' 'unsafe-inline' https://tips.hushline.app"
    assert directives["font-src"] == "'self' https://tips.hushline.app"
    assert directives["script-src"] == (
        "'self' https://js.stripe.com https://cdn.jsdelivr.net "
        "'wasm-unsafe-eval' https://tips.hushline.app"
    )
    assert directives["script-src-elem"] == (
        "'self' https://js.stripe.com https://cdn.jsdelivr.net https://tips.hushline.app"
    )
    assert "X-Frame-Options" not in response.headers


def test_non_embed_csp_does_not_add_canonical_asset_origin(client: FlaskClient, app: Flask) -> None:
    app.config["PUBLIC_BASE_URL"] = "https://tips.hushline.app"

    response = client.get(url_for("directory"))

    assert response.status_code == 200
    directives = _csp_directives(response.headers)
    assert directives["style-src"] == "'self' 'unsafe-inline'"
    assert directives["font-src"] == "'self'"
    assert directives["script-src-elem"] == (
        "'self' https://js.stripe.com https://cdn.jsdelivr.net"
    )


def test_denied_embed_csp_does_not_add_canonical_asset_origin(
    client: FlaskClient, app: Flask
) -> None:
    app.config["PUBLIC_BASE_URL"] = "https://tips.hushline.app"

    response = client.get(url_for("embed_profile", username="does-not-exist"))

    assert response.status_code == 404
    directives = _csp_directives(response.headers)
    assert directives["frame-ancestors"] == "'none'"
    assert directives["style-src"] == "'self' 'unsafe-inline'"
    assert directives["font-src"] == "'self'"
    assert directives["script-src-elem"] == (
        "'self' https://js.stripe.com https://cdn.jsdelivr.net"
    )
    assert response.headers["X-Frame-Options"] == "DENY"


def test_static_fonts_allow_cross_origin_embed_loading(
    client: FlaskClient, app: Flask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font_path = tmp_path / "fonts" / "AtkinsonHyperlegible-Regular.woff2"
    font_path.parent.mkdir()
    font_path.write_bytes(b"test font")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))

    response = client.get(url_for("static", filename="fonts/AtkinsonHyperlegible-Regular.woff2"))
    assert response.status_code == 200

    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_static_non_font_assets_do_not_enable_cors(
    client: FlaskClient, app: Flask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stylesheet_path = tmp_path / "css" / "style.css"
    stylesheet_path.parent.mkdir()
    stylesheet_path.write_text("body { color: black; }")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))

    response = client.get(url_for("static", filename="css/style.css"))
    assert response.status_code == 200

    assert "Access-Control-Allow-Origin" not in response.headers


def test_password_reset_pages_keep_csp_enforced(client: FlaskClient) -> None:
    paths = (
        url_for("request_password_reset"),
        url_for("reset_password", token="unknown"),  # noqa: S106
    )
    for path in paths:
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200
        csp = (response.headers.get("Content-Security-Policy") or "").strip()
        assert csp
        assert "'unsafe-eval'" not in csp
        assert "script-src-elem 'self' 'unsafe-inline'" not in csp


@pytest.mark.usefixtures("_authenticated_user")
def test_conversation_page_keeps_csp_enforced(client: FlaskClient, user: User, user2: User) -> None:
    conversation = Conversation()
    participant = ConversationParticipant()
    participant.conversation = conversation
    participant.user = user
    other_participant = ConversationParticipant()
    other_participant.conversation = conversation
    other_participant.user = user2
    db.session.add(conversation)
    db.session.commit()

    response = client.get(url_for("conversation", public_id=conversation.public_id))

    assert response.status_code == 200
    directives = _csp_directives(response.headers)
    assert "'unsafe-eval'" not in response.headers["Content-Security-Policy"]
    assert directives["script-src-elem"] == (
        "'self' https://js.stripe.com https://cdn.jsdelivr.net"
    )
    assert (
        "script-src-elem 'self' 'unsafe-inline'" not in response.headers["Content-Security-Policy"]
    )


def test_base_template_uses_external_no_js_bootstrap_script(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert 'src="/static/no-js.js"' in response.text
    assert 'document.documentElement.classList.remove("no-js");' not in response.text
    assert "sessionStorage.getItem" not in response.text


def test_x_frame_options(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"


def test_x_content_type_options(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_permissions_policy(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["Permissions-Policy"] == PERMISSIONS_POLICY
    assert not response.headers["Permissions-Policy"].endswith(";")
    assert ";," not in response.headers["Permissions-Policy"]
    for unsupported_feature in ("notifications", "push", "speaker", "vibrate"):
        assert f"{unsupported_feature}=()" not in response.headers["Permissions-Policy"]


def test_referrer_policy(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_x_xss_protection(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["X-XSS-Protection"] == "1; mode=block"


def test_strict_transport_security(client: FlaskClient, app: Flask) -> None:
    app.config["SERVER_NAME"] = "example.com"
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == ("max-age=63072000; includeSubdomains")


def test_no_strict_transport_security_onion(client: FlaskClient, app: Flask) -> None:
    app.config["SERVER_NAME"] = "example.onion"
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers

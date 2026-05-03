from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.model import OrganizationSetting, User


def test_csp(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "img-src 'self' data: https:" in csp


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


def test_profile_page_keeps_csp_enforced(client: FlaskClient, user: User) -> None:
    response = client.get(url_for("profile", username=user.primary_username.username))
    assert response.status_code == 200

    csp = (response.headers.get("Content-Security-Policy") or "").strip()
    assert csp
    assert "'unsafe-eval'" not in csp
    assert "script-src-elem 'self' 'unsafe-inline'" not in csp


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
    assert response.headers["Permissions-Policy"] == (
        "geolocation=(), midi=(), notifications=(), push=(), sync-xhr=(), microphone=(), camera=(), magnetometer=(), gyroscope=(), speaker=(), vibrate=(), fullscreen=(), payment=(), interest-cohort=();"  # noqa: E501
    )


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

from flask import Flask, url_for
from flask.testing import FlaskClient


def test_csp(client: FlaskClient) -> None:
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert (response.headers.get("Content-Security-Policy") or "").strip()


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

import pytest
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import User


def test_csp(client: FlaskClient) -> None:
    # Load the directory homepage
    response = client.get(
        url_for("directory"),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers

    # Check that the CSP header is set correctly
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self';" in csp
    assert "script-src 'self' https://js.stripe.com;" in csp
    assert "img-src 'self' data: https:;" in csp
    assert "style-src 'self';" in csp
    assert "frame-ancestors 'none';" in csp
    assert "connect-src 'self' https://api.stripe.com;" in csp
    assert "child-src https://js.stripe.com;" in csp
    assert "frame-src https://js.stripe.com;" in csp

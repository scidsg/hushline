import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline.model import OrganizationSetting
from hushline.update_notice import RELEASE_PAGE


@pytest.mark.parametrize("brand_name", ["🤫 Hush Line", "Our Newsroom"])
def test_footer_shows_update_for_default_and_custom_brand_without_broadening_csp(
    app: Flask, client: FlaskClient, mocker: MockFixture, brand_name: str
) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_NAME, brand_name)
    mocker.patch.dict(app.config, {"TESTING": False, "UPDATE_CHECK_ENABLED": True})
    mocker.patch.object(
        app.extensions["hushline_release_check"], "newer_than", return_value="0.7.28"
    )
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    notice = BeautifulSoup(response.text, "html.parser").select_one("footer .update-notice")
    assert notice is not None
    assert notice.get_text(" ", strip=True) == "| ⚠️ Update available"
    assert f'href="{RELEASE_PAGE}"' in response.text
    assert ("Powered by Hush Line" in response.text) == (brand_name != "🤫 Hush Line")
    directives = dict(
        part.strip().split(" ", 1)
        for part in response.headers["Content-Security-Policy"].split(";")
        if part.strip()
    )
    assert directives["connect-src"] == "'self' data:"
    assert directives["script-src"] == "'self'"
    assert 'rel="noopener noreferrer"' in response.text


def test_footer_does_not_claim_unknown_release_is_current(
    app: Flask, client: FlaskClient, mocker: MockFixture
) -> None:
    mocker.patch.dict(app.config, {"TESTING": False, "UPDATE_CHECK_ENABLED": True})
    mocker.patch.object(app.extensions["hushline_release_check"], "newer_than", return_value=None)
    response = client.get(url_for("directory"), follow_redirects=True)
    assert response.status_code == 200
    assert "Update available" not in response.text
    assert "up to date" not in response.text.lower()

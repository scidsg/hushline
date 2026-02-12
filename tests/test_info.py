import os
from typing import Callable

import pytest
from flask import Flask, url_for
from pytest_mock import MockFixture

from hushline.model import OrganizationSetting


@pytest.fixture()
def env_var_modifier() -> Callable[[MockFixture], None]:
    def modifier(mocker: MockFixture) -> None:
        mocker.patch.dict(os.environ, {"ONION_HOSTNAME": "example.onion"})

    return modifier


def test_info_available(app: Flask) -> None:
    with app.test_client() as client:
        response = client.get(url_for("server_info"))
        assert response.status_code == 200
        assert "Hush Line Server Info" in response.get_data(as_text=True)
        assert "example.onion" in response.get_data(as_text=True)


def test_site_webmanifest_reflects_branding(app: Flask) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_NAME, "Test Brand")
    OrganizationSetting.upsert(OrganizationSetting.BRAND_PRIMARY_COLOR, "#112233")

    with app.test_client() as client:
        response = client.get(url_for("site_webmanifest"))
        assert response.status_code == 200
        assert response.mimetype == "application/manifest+json"
        payload = response.get_json()
        assert payload["name"] == "Test Brand"
        assert payload["short_name"] == "Test Brand"
        assert payload["theme_color"] == "#112233"


def test_site_webmanifest_includes_uploaded_logo_icon(app: Flask) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_LOGO, "brand/logo.png")

    with app.test_client() as client:
        response = client.get(url_for("site_webmanifest"))
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["icons"][0]["src"].endswith("/assets/public/brand/logo.png")

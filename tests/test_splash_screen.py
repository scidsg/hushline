from typing import Any

from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.config import SPLASH_SCREEN_DURATION_MS
from hushline.db import db
from hushline.model import OrganizationSetting


def _get_splash(client: FlaskClient) -> Any:
    response = client.get(url_for("register"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    splash = soup.find(id="first-load-splash")
    assert splash is not None
    return splash


def test_first_load_splash_markup_uses_default_duration(client: FlaskClient) -> None:
    splash = _get_splash(client)

    assert splash.get("aria-hidden") == "true"
    assert splash.get("data-splash-duration-ms") == "2000"
    logo = splash.find("img", src=url_for("static", filename="img/splash-logo.png"))
    assert logo
    assert not splash.find("img", src="https://hushline.app/assets/img/social/logo.png")
    assert logo.get("referrerpolicy") == "no-referrer"
    assert splash.find("span", class_="first-load-splash-spinner")
    assert not splash.find(["a", "button", "input", "select", "textarea"])


def test_first_load_splash_duration_uses_runtime_config(app: Flask, client: FlaskClient) -> None:
    app.config[SPLASH_SCREEN_DURATION_MS] = 750

    splash = _get_splash(client)

    assert splash.get("data-splash-duration-ms") == "750"


def test_first_load_splash_ignores_custom_header_logo(client: FlaskClient) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_LOGO, OrganizationSetting.BRAND_LOGO_VALUE)
    db.session.commit()

    splash = _get_splash(client)

    assert splash.find("img", src=url_for("static", filename="img/splash-logo.png"))
    assert not splash.find(
        "img", src=url_for("storage.public", path=OrganizationSetting.BRAND_LOGO_VALUE)
    )


def test_first_load_splash_uses_custom_splash_logo(client: FlaskClient) -> None:
    OrganizationSetting.upsert(
        OrganizationSetting.BRAND_SPLASH_LOGO, OrganizationSetting.BRAND_SPLASH_LOGO_VALUE
    )
    db.session.commit()

    splash = _get_splash(client)

    splash_logo_url = url_for("storage.public", path=OrganizationSetting.BRAND_SPLASH_LOGO_VALUE)
    logo = splash.find("img", src=splash_logo_url)
    assert logo
    assert logo.get("referrerpolicy") == "no-referrer"
    assert not splash.find("img", src=url_for("static", filename="img/splash-logo.png"))

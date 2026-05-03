from typing import Any

from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.config import SPLASH_SCREEN_DURATION_MS
from hushline.db import db
from hushline.model import OrganizationSetting

NATIVE_STARTUP_SPLASH_MEDIA = {
    "launch-1125x2436.png": (
        "(width: 375px) and (height: 812px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
    "launch-828x1792.png": (
        "(width: 414px) and (height: 896px) and (-webkit-device-pixel-ratio: 2) "
        "and (orientation: portrait)"
    ),
    "launch-1242x2688.png": (
        "(width: 414px) and (height: 896px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
    "launch-1080x2340.png": (
        "(width: 360px) and (height: 780px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
    "launch-1170x2532.png": (
        "(width: 390px) and (height: 844px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
    "launch-1179x2556.png": (
        "(width: 393px) and (height: 852px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
    "launch-1284x2778.png": (
        "(width: 428px) and (height: 926px) and (-webkit-device-pixel-ratio: 3) "
        "and (orientation: portrait)"
    ),
}


def _get_splash(client: FlaskClient) -> Any:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_SPLASH_SCREEN_ENABLED, True)
    db.session.commit()

    response = client.get(url_for("register"))
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    splash = soup.find(id="first-load-splash")
    assert splash is not None
    return splash


def _native_startup_splash_links(soup: BeautifulSoup) -> dict[str, str]:
    links = soup.find_all("link", rel="apple-touch-startup-image")
    return {
        link.get("href", "").removeprefix("/static/splash/"): " ".join(
            (link.get("media") or "").split()
        )
        for link in links
    }


def test_first_load_splash_markup_uses_default_duration(client: FlaskClient) -> None:
    splash = _get_splash(client)

    assert splash.get("aria-hidden") == "true"
    assert splash.get("data-splash-duration-ms") == "2000"
    assert splash.get("data-splash-skip-seen-mark") == "false"
    logo = splash.find("img", src=url_for("static", filename="img/splash-logo.png"))
    assert logo
    assert not splash.find("img", src="https://hushline.app/assets/img/social/logo.png")
    assert logo.get("referrerpolicy") == "no-referrer"
    assert splash.find("span", class_="first-load-splash-spinner")
    assert not splash.find(["a", "button", "input", "select", "textarea"])


def test_native_pwa_startup_splash_defaults_to_declared(client: FlaskClient) -> None:
    response = client.get(url_for("register"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert _native_startup_splash_links(soup) == NATIVE_STARTUP_SPLASH_MEDIA
    assert soup.find(id="first-load-splash") is None
    assert soup.find("meta", attrs={"name": "first-load-splash-logo-src"}) is None


def test_native_pwa_startup_splash_is_not_declared_with_first_load_splash(
    client: FlaskClient,
) -> None:
    splash = _get_splash(client)
    soup = BeautifulSoup(str(splash.find_parent("html")), "html.parser")

    assert _native_startup_splash_links(soup) == {}
    assert soup.find("meta", attrs={"name": "first-load-splash-logo-src"}) is not None


def test_first_load_splash_duration_uses_runtime_config(app: Flask, client: FlaskClient) -> None:
    app.config[SPLASH_SCREEN_DURATION_MS] = 750

    splash = _get_splash(client)

    assert splash.get("data-splash-duration-ms") == "750"


def test_first_load_splash_uses_brand_logo_fallback(client: FlaskClient) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_LOGO, OrganizationSetting.BRAND_LOGO_VALUE)
    db.session.commit()

    splash = _get_splash(client)

    brand_logo_url = url_for("storage.public", path=OrganizationSetting.BRAND_LOGO_VALUE)
    logo = splash.find("img", src=brand_logo_url)
    assert logo
    assert logo.get("referrerpolicy") == "no-referrer"
    assert not splash.find("img", src=url_for("static", filename="img/splash-logo.png"))


def test_first_load_splash_uses_custom_splash_logo(client: FlaskClient) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_LOGO, OrganizationSetting.BRAND_LOGO_VALUE)
    OrganizationSetting.upsert(
        OrganizationSetting.BRAND_SPLASH_LOGO, OrganizationSetting.BRAND_SPLASH_LOGO_VALUE
    )
    db.session.commit()

    splash = _get_splash(client)

    splash_logo_url = url_for("storage.public", path=OrganizationSetting.BRAND_SPLASH_LOGO_VALUE)
    logo = splash.find("img", src=splash_logo_url)
    assert logo
    assert logo.get("referrerpolicy") == "no-referrer"
    assert not splash.find(
        "img", src=url_for("storage.public", path=OrganizationSetting.BRAND_LOGO_VALUE)
    )
    assert not splash.find("img", src=url_for("static", filename="img/splash-logo.png"))


def test_first_load_splash_uses_versioned_custom_splash_logo(client: FlaskClient) -> None:
    OrganizationSetting.upsert(
        OrganizationSetting.BRAND_SPLASH_LOGO, OrganizationSetting.BRAND_SPLASH_LOGO_VALUE
    )
    OrganizationSetting.upsert(OrganizationSetting.BRAND_SPLASH_LOGO_CACHE_BUSTER, "12345")
    db.session.commit()

    splash = _get_splash(client)

    splash_logo_url = url_for(
        "storage.public",
        path=OrganizationSetting.BRAND_SPLASH_LOGO_VALUE,
        v="12345",
    )
    assert splash.find("img", src=splash_logo_url)


def test_first_load_splash_defaults_to_disabled(client: FlaskClient) -> None:
    response = client.get(url_for("register"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.find(id="first-load-splash") is None
    assert soup.find("meta", attrs={"name": "first-load-splash-logo-src"}) is None
    assert _native_startup_splash_links(soup) == NATIVE_STARTUP_SPLASH_MEDIA


def test_first_load_splash_can_be_disabled(client: FlaskClient) -> None:
    OrganizationSetting.upsert(OrganizationSetting.BRAND_SPLASH_SCREEN_ENABLED, False)
    db.session.commit()

    response = client.get(url_for("register"))

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.find(id="first-load-splash") is None
    assert soup.find("meta", attrs={"name": "first-load-splash-logo-src"}) is None
    assert _native_startup_splash_links(soup) == NATIVE_STARTUP_SPLASH_MEDIA

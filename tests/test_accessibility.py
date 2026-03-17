import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import OrganizationSetting


def test_directory_tab_aria_and_controls(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    primary_nav = soup.find("nav", {"aria-label": "Primary navigation"})
    verified_tab = soup.find("button", {"id": "verified-tab"})
    public_records_tab = soup.find("button", {"id": "public-records-tab"})
    globaleaks_tab = soup.find("button", {"id": "globaleaks-tab"})
    securedrop_tab = soup.find("button", {"id": "securedrop-tab"})
    all_tab = soup.find("button", {"id": "all-tab"})
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    globaleaks_panel = soup.find(id="globaleaks")
    securedrop_panel = soup.find(id="securedrop")
    all_panel = soup.find(id="all")
    clear_button = soup.find("button", {"id": "clearIcon"})
    search_status = soup.find(id="directory-search-status")
    region_filter_label = soup.find("label", {"for": "attorney-region-filter"})
    region_filter = soup.find("select", {"id": "attorney-region-filter"})

    assert primary_nav is not None
    assert verified_tab is not None
    assert verified_tab.get("aria-controls") == "verified"
    assert verified_tab.get("aria-selected") in {"true", "false"}
    assert public_records_tab is not None

    badge = public_records_tab.select_one("span.badge")
    assert badge is not None
    assert badge.get("role") == "img"
    assert badge.get("aria-label") == "Attorney count"
    assert badge.get_text(strip=True).isdigit()

    # Button label text excluding the badge
    label_text = (
        public_records_tab.get_text(" ", strip=True)
        .replace(badge.get_text(" ", strip=True), "")
        .strip()
    )
    assert label_text == "Attorneys"
    assert public_records_tab.get("aria-controls") == "public-records"
    assert public_records_tab.get("aria-selected") in {"true", "false"}
    assert globaleaks_tab is not None
    globaleaks_badge = globaleaks_tab.select_one("span.badge")
    assert globaleaks_badge is not None
    assert globaleaks_badge.get("role") == "img"
    assert globaleaks_badge.get("aria-label") == "GlobaLeaks instance count"
    assert globaleaks_badge.get_text(strip=True).isdigit()
    globaleaks_label_text = (
        globaleaks_tab.get_text(" ", strip=True)
        .replace(globaleaks_badge.get_text(" ", strip=True), "")
        .strip()
    )
    assert globaleaks_label_text == "GlobaLeaks"
    assert globaleaks_tab.get("aria-controls") == "globaleaks"
    assert globaleaks_tab.get("aria-selected") in {"true", "false"}
    assert securedrop_tab is not None
    securedrop_badge = securedrop_tab.select_one("span.badge")
    assert securedrop_badge is not None
    assert securedrop_badge.get("role") == "img"
    assert securedrop_badge.get("aria-label") == "SecureDrop instance count"
    assert securedrop_badge.get_text(strip=True).isdigit()
    securedrop_label_text = (
        securedrop_tab.get_text(" ", strip=True)
        .replace(securedrop_badge.get_text(" ", strip=True), "")
        .strip()
    )
    assert securedrop_label_text == "SecureDrop"
    assert securedrop_tab.get("aria-controls") == "securedrop"
    assert securedrop_tab.get("aria-selected") in {"true", "false"}
    assert all_tab is not None
    assert all_tab.get("aria-controls") == "all"
    assert all_tab.get("aria-selected") in {"true", "false"}
    assert verified_panel is not None
    assert verified_panel.get("role") == "tabpanel"
    assert verified_panel.get("aria-labelledby") == "verified-tab"
    assert public_records_panel is not None
    assert public_records_panel.get("role") == "tabpanel"
    assert public_records_panel.get("aria-labelledby") == "public-records-tab"
    assert globaleaks_panel is not None
    assert globaleaks_panel.get("role") == "tabpanel"
    assert globaleaks_panel.get("aria-labelledby") == "globaleaks-tab"
    assert securedrop_panel is not None
    assert securedrop_panel.get("role") == "tabpanel"
    assert securedrop_panel.get("aria-labelledby") == "securedrop-tab"
    assert all_panel is not None
    assert all_panel.get("role") == "tabpanel"
    assert all_panel.get("aria-labelledby") == "all-tab"
    assert clear_button is not None
    assert clear_button.get("aria-label") == "Clear search field"
    assert region_filter_label is not None
    assert region_filter_label.get_text(" ", strip=True) == "State / Province / Region"
    assert region_filter is not None
    assert region_filter.find("option") is not None
    assert region_filter.find("option").get_text(" ", strip=True) == "All"
    assert search_status is not None
    assert search_status.get("role") == "status"
    assert search_status.get("aria-live") == "polite"
    assert search_status.get("aria-atomic") == "true"


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_nav_marks_current_page(client: FlaskClient) -> None:
    response = client.get(url_for("settings.profile"), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    current = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current is not None
    assert current.text.strip() == "Profile"


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_filter_nav_marks_current_page(client: FlaskClient) -> None:
    response = client.get(url_for("inbox"), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    primary_nav = soup.find("nav", {"aria-label": "Primary navigation"})
    inbox_nav = soup.find("nav", {"aria-label": "Inbox filters"})
    current = soup.select_one('nav.inbox-tabs-nav a[aria-current="page"]')

    assert primary_nav is not None
    assert inbox_nav is not None
    assert current is not None
    assert current.text.strip() == "All"


def test_guidance_modal_has_accessible_attributes(client: FlaskClient) -> None:
    OrganizationSetting.upsert(OrganizationSetting.GUIDANCE_ENABLED, True)
    OrganizationSetting.upsert(
        OrganizationSetting.GUIDANCE_PROMPTS,
        [
            {"heading_text": "Prompt 1", "prompt_text": "Prompt 1", "index": 0},
            {"heading_text": "Prompt 2", "prompt_text": "Prompt 2", "index": 1},
        ],
    )
    db.session.commit()

    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    modal = soup.find(id="guidance-modal")
    assert modal is not None
    assert modal.get("role") == "dialog"
    assert modal.get("aria-modal") == "true"
    assert modal.get("aria-labelledby") == "guidance-heading-0"
    assert modal.get("aria-hidden") == "true"
    assert modal.get("tabindex") == "-1"
    assert soup.find("button", {"aria-label": "Go to step 1"}) is not None
    assert soup.find("button", {"aria-label": "Go to step 2"}) is not None

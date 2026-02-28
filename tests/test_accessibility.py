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
    all_tab = soup.find("button", {"id": "all-tab"})
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    all_panel = soup.find(id="all")
    clear_button = soup.find("button", {"id": "clearIcon"})
    search_status = soup.find(id="directory-search-status")

    assert primary_nav is not None
    assert verified_tab is not None
    assert verified_tab.get("aria-controls") == "verified"
    assert verified_tab.get("aria-selected") in {"true", "false"}
    assert public_records_tab is not None
    assert public_records_tab.get("aria-controls") == "public-records"
    assert public_records_tab.get("aria-selected") in {"true", "false"}
    assert all_tab is not None
    assert all_tab.get("aria-controls") == "all"
    assert all_tab.get("aria-selected") in {"true", "false"}
    assert verified_panel is not None
    assert verified_panel.get("role") == "tabpanel"
    assert verified_panel.get("aria-labelledby") == "verified-tab"
    assert public_records_panel is not None
    assert public_records_panel.get("role") == "tabpanel"
    assert public_records_panel.get("aria-labelledby") == "public-records-tab"
    assert all_panel is not None
    assert all_panel.get("role") == "tabpanel"
    assert all_panel.get("aria-labelledby") == "all-tab"
    assert clear_button is not None
    assert clear_button.get("aria-label") == "Clear search field"
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

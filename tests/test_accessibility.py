import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import Message, OrganizationSetting, User


def test_directory_tab_aria_and_controls(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    primary_nav = soup.find("nav", {"aria-label": "Primary navigation"})
    skip_link = soup.find("a", {"class": "skip-link"})
    verified_tab = soup.find("button", {"id": "verified-tab"})
    all_tab = soup.find("button", {"id": "all-tab"})
    verified_panel = soup.find(id="verified")
    all_panel = soup.find(id="all")
    clear_button = soup.find("button", {"id": "clearIcon"})

    assert primary_nav is not None
    assert skip_link is not None
    assert skip_link.get("href") == "#main-content"
    assert verified_tab is not None
    assert verified_tab.get("aria-controls") == "verified"
    assert verified_tab.get("aria-selected") in {"true", "false"}
    assert all_tab is not None
    assert all_tab.get("aria-controls") == "all"
    assert all_tab.get("aria-selected") in {"true", "false"}
    assert verified_panel is not None
    assert verified_panel.get("role") == "tabpanel"
    assert verified_panel.get("aria-labelledby") == "verified-tab"
    assert all_panel is not None
    assert all_panel.get("role") == "tabpanel"
    assert all_panel.get("aria-labelledby") == "all-tab"
    assert clear_button is not None
    assert clear_button.get("aria-label") == "Clear search field"


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_nav_marks_current_page(client: FlaskClient) -> None:
    response = client.get(url_for("settings.profile"), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    current = soup.select_one('nav.settings-tabs a[aria-current="page"]')
    assert current is not None
    assert current.text.strip() == "Profile"


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
    assert modal.get("aria-hidden") == "true"
    assert modal.get("aria-labelledby") == "guidance-heading-0"
    assert modal.get("aria-describedby") == "guidance-body-0"
    assert modal.get("tabindex") == "-1"
    assert soup.find("button", {"aria-label": "Go to step 1"}) is not None
    assert soup.find("button", {"aria-label": "Go to step 2"}) is not None


@pytest.mark.usefixtures("_authenticated_user")
def test_message_status_control_has_accessible_name(client: FlaskClient, message: Message) -> None:
    response = client.get(url_for("message", public_id=message.public_id), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    status = soup.find("select", {"name": "status"})

    assert status is not None
    assert status.get("aria-label") == "Message status"


@pytest.mark.usefixtures("_authenticated_user")
def test_profile_verified_address_icon_has_accessible_name(client: FlaskClient, user: User) -> None:
    username = user.primary_username
    username.extra_field_label1 = "Website"
    username.extra_field_value1 = "https://example.org"
    username.extra_field_verified1 = True
    db.session.commit()

    response = client.get(url_for("profile", username=username.username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    verified_icon = soup.find("span", {"aria-label": "Verified address"})

    assert verified_icon is not None
    assert verified_icon.get("role") == "img"


@pytest.mark.usefixtures("_authenticated_user")
def test_settings_profile_verified_address_icon_has_accessible_name(
    client: FlaskClient,
    user: User,
) -> None:
    username = user.primary_username
    username.extra_field_label1 = "Website"
    username.extra_field_value1 = "https://example.org"
    username.extra_field_verified1 = True
    db.session.commit()

    response = client.get(url_for("settings.profile"), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    verified_icon = soup.find("span", {"aria-label": "Verified address"})

    assert verified_icon is not None
    assert verified_icon.get("role") == "img"


def test_registration_errors_are_announced_and_linked_to_fields(client: FlaskClient) -> None:
    response = client.post(url_for("register"), data={"username": "", "password": ""})
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    username_input = soup.find("input", {"id": "username"})
    password_input = soup.find("input", {"id": "password"})
    username_error = soup.find(id="username-error")
    password_error = soup.find(id="password-error")

    assert username_input is not None
    assert username_input.get("aria-invalid") == "true"
    assert username_input.get("aria-describedby") == "username-error"
    assert username_error is not None
    assert username_error.get("role") == "alert"
    assert username_error.text.strip()

    assert password_input is not None
    assert password_input.get("aria-invalid") == "true"
    assert password_input.get("aria-describedby") == "password-error"
    assert password_error is not None
    assert password_error.get("role") == "alert"
    assert password_error.text.strip()

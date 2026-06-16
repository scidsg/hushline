import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient

from hushline.db import db
from hushline.model import (
    Conversation,
    ConversationMessage,
    ConversationMessageCopy,
    ConversationParticipant,
    OrganizationSetting,
    User,
)


def _assert_2fa_code_input_accessibility(
    soup: BeautifulSoup,
    *,
    describedby_ids: set[str],
    expects_error: bool = False,
) -> None:
    field = soup.find(id="verification_code")
    label = soup.find("label", {"for": "verification_code"})

    assert field is not None
    assert label is not None
    assert label.get_text(" ", strip=True) == "2FA Code"
    assert field.get("autocomplete") == "one-time-code"
    assert field.get("inputmode") == "numeric"
    assert field.get("pattern") == "[0-9]*"

    describedby = set((field.get("aria-describedby") or "").split())
    assert describedby_ids.issubset(describedby)
    for element_id in describedby_ids:
        assert soup.find(id=element_id) is not None

    if expects_error:
        assert field.get("aria-invalid") == "true"
        error = soup.find(id="verification-code-error")
        assert error is not None
        assert error.get("role") == "alert"
        assert error.get("aria-live") == "assertive"
    else:
        assert field.get("aria-invalid") == "false"


def _make_inbox_conversation(
    user: User,
    user2: User,
    *,
    user_has_copy: bool,
    sender_is_other_user: bool,
) -> Conversation:
    conversation = Conversation()
    user_participant = ConversationParticipant()
    user_participant.conversation = conversation
    user_participant.user = user
    user_participant.has_usable_public_key = user_has_copy
    other_participant = ConversationParticipant()
    other_participant.conversation = conversation
    other_participant.user = user2
    other_participant.has_usable_public_key = True
    conversation_message = ConversationMessage()
    conversation_message.conversation = conversation
    conversation_message.sender_participant = (
        other_participant if sender_is_other_user else user_participant
    )
    if user_has_copy:
        user_copy = ConversationMessageCopy()
        user_copy.recipient_participant = user_participant
        user_copy.encrypted_payload = "encrypted-for-current-user"
        conversation_message.encrypted_copies.append(user_copy)
    other_copy = ConversationMessageCopy()
    other_copy.recipient_participant = other_participant
    other_copy.encrypted_payload = "encrypted-for-other-user"
    conversation_message.encrypted_copies.append(other_copy)
    db.session.add(conversation)
    db.session.commit()
    return conversation


def test_directory_tab_aria_and_controls(client: FlaskClient) -> None:
    response = client.get(url_for("directory"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    primary_nav = soup.find("nav", {"aria-label": "Primary navigation"})
    verified_tab = soup.find("button", {"id": "verified-tab"})
    public_records_tab = soup.find("button", {"id": "public-records-tab"})
    journalists_tab = soup.find("button", {"id": "newsrooms-tab"})
    globaleaks_tab = soup.find("button", {"id": "globaleaks-tab"})
    securedrop_tab = soup.find("button", {"id": "securedrop-tab"})
    all_tab = soup.find("button", {"id": "all-tab"})
    verified_panel = soup.find(id="verified")
    public_records_panel = soup.find(id="public-records")
    journalists_panel = soup.find(id="newsrooms")
    globaleaks_panel = soup.find(id="globaleaks")
    securedrop_panel = soup.find(id="securedrop")
    all_panel = soup.find(id="all")
    clear_button = soup.find("button", {"id": "clearIcon"})
    search_status = soup.find(id="directory-search-status")
    all_filters_toggle = soup.find("button", {"id": "all-filters-toggle"})
    all_filters_panel = soup.find(id="all-filters-panel")
    all_listing_type_label = soup.find("label", {"for": "all-listing-type-filter"})
    all_listing_type_filter = soup.find("select", {"id": "all-listing-type-filter"})
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
    assert journalists_tab is not None
    journalists_badge = journalists_tab.select_one("span.badge")
    assert journalists_badge is not None
    assert journalists_badge.get("role") == "img"
    assert journalists_badge.get("aria-label") == "Journalist and newsroom listing count"
    assert journalists_badge.get_text(strip=True).isdigit()
    journalists_label_text = (
        journalists_tab.get_text(" ", strip=True)
        .replace(journalists_badge.get_text(" ", strip=True), "")
        .strip()
    )
    assert journalists_label_text == "Journalists"
    assert journalists_tab.get("aria-controls") == "newsrooms"
    assert journalists_tab.get("aria-selected") in {"true", "false"}
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
    assert journalists_panel is not None
    assert journalists_panel.get("role") == "tabpanel"
    assert journalists_panel.get("aria-labelledby") == "newsrooms-tab"
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
    assert all_filters_toggle is not None
    assert all_filters_toggle.get("aria-controls") == "all-filters-panel"
    assert all_filters_toggle.get("aria-expanded") in {"true", "false"}
    assert all_filters_panel is not None
    assert all_filters_panel.find("a", {"id": "all-filters-clear"}) is not None
    assert all_listing_type_label is not None
    assert all_listing_type_label.get_text(" ", strip=True) == "Listing Type"
    assert all_listing_type_filter is not None
    assert all_listing_type_filter.find("option") is not None
    assert all_listing_type_filter.find("option").get_text(" ", strip=True) == "All"
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

    tips_response = client.get(url_for("inbox", type="tips"), follow_redirects=True)
    assert tips_response.status_code == 200
    tips_soup = BeautifulSoup(tips_response.text, "html.parser")
    tips_current = tips_soup.select_one('nav.inbox-tabs-nav a[aria-current="page"]')
    assert tips_current is not None
    assert tips_current.text.strip() == "Tips"

    conversations_response = client.get(
        url_for("inbox", type="conversations"),
        follow_redirects=True,
    )
    assert conversations_response.status_code == 200
    conversations_soup = BeautifulSoup(conversations_response.text, "html.parser")
    conversations_current = conversations_soup.select_one(
        'nav.inbox-tabs-nav a[aria-current="page"]'
    )
    assert conversations_current is not None
    assert conversations_current.text.strip() == "Conversations"


@pytest.mark.usefixtures("_authenticated_user")
def test_inbox_conversation_rows_have_accessible_status_and_unread_state(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    locked_conversation = _make_inbox_conversation(
        user,
        user2,
        user_has_copy=True,
        sender_is_other_user=False,
    )
    unavailable_conversation = _make_inbox_conversation(
        user,
        user2,
        user_has_copy=False,
        sender_is_other_user=True,
    )

    response = client.get(url_for("inbox"), follow_redirects=True)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    conversation_section = soup.find("section", {"aria-label": "Conversations"})
    conversation_heading = soup.find(id="conversation-list-heading")
    message_list = soup.select_one(".message-list")
    conversation_rows = soup.select("article.conversation-summary")
    unread_indicator = soup.select_one("article.conversation-summary .conversation-unread-dot")
    status_messages = soup.select("article.conversation-summary [role='status']")

    assert conversation_section is None
    assert conversation_heading is None
    assert message_list is not None
    assert len(conversation_rows) == 2
    for row in conversation_rows:
        assert row.parent == message_list
        time = row.find("time")
        assert time is not None
        assert time.parent is not None
        assert "inbox-message-summary-meta" in time.parent.get("class", [])
        title_id = row.get("aria-labelledby")
        assert title_id
        title = soup.find(id=title_id)
        assert title is not None
        assert title.get_text(" ", strip=True).startswith("From: @")
        route = row.select_one(".conversation-summary-route")
        assert route is not None
        assert route.get_text(" ", strip=True).startswith("To: @")
        avatar = row.select_one(".conversation-summary-avatar")
        assert avatar is not None
        assert avatar.get("aria-hidden") == "true"
        assert avatar.get_text(" ", strip=True)

    assert unread_indicator is not None
    assert unread_indicator.get("role") == "img"
    assert unread_indicator.get("aria-label") == "Unread conversation"
    assert unread_indicator.get_text(" ", strip=True) == ""
    unread_title = unread_indicator.parent
    assert unread_title is not None
    assert "inbox-message-recipient" in unread_title.get("class", [])
    assert unread_title.find("span", class_="conversation-unread-dot") == unread_indicator
    assert unread_title.get_text(" ", strip=True).startswith("From: @")
    assert str(unread_title).index('class="conversation-unread-dot"') < str(unread_title).index(
        "From:"
    )
    assert status_messages == []
    locked_link = soup.find(
        "a", href=url_for("conversation", public_id=locked_conversation.public_id)
    )
    unavailable_link = soup.find(
        "a",
        href=url_for("conversation", public_id=unavailable_conversation.public_id),
    )
    assert locked_link is not None
    assert locked_link.get_text(" ", strip=True) == "Go to conversation"
    assert unavailable_link is not None
    assert unavailable_link.get_text(" ", strip=True) == "Go to conversation"


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


@pytest.mark.usefixtures("_authenticated_user")
def test_conversation_chat_has_accessible_log_and_composer(
    client: FlaskClient,
    user: User,
    user2: User,
) -> None:
    conversation = _make_inbox_conversation(
        user,
        user2,
        user_has_copy=True,
        sender_is_other_user=True,
    )

    response = client.get(
        url_for("conversation", public_id=conversation.public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    thread = soup.select_one(".conversation-thread")
    live_status = soup.find(id="conversation-live-status")
    composer = soup.find(id="conversation-compose-body")
    help_text = soup.find(id="conversation-compose-help")
    chat_status = soup.find(id="conversation-chat-status")
    message_time = soup.select_one("[data-conversation-message-time]")

    assert thread is not None
    assert thread.get("role") == "log"
    assert thread.get("tabindex") == "0"
    assert thread.get("aria-live") == "polite"
    assert thread.get("aria-relevant") == "additions text"
    assert thread.get("aria-atomic") == "false"
    assert live_status is not None
    assert live_status.get("role") == "status"
    assert live_status.get("aria-live") == "polite"
    assert live_status.get("aria-atomic") == "true"
    assert composer is not None
    assert help_text is not None
    assert chat_status is not None
    assert set((composer.get("aria-describedby") or "").split()) == {
        "conversation-compose-help",
        "conversation-chat-status",
    }
    assert message_time is not None
    assert message_time.get("role") is None


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_2fa_setup_has_accessible_code_entry(client: FlaskClient) -> None:
    response = client.get(url_for("settings.enable_2fa"))
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    qr_code = soup.find("img", class_="qr")
    secret = soup.find(id="two-factor-secret")

    assert qr_code is not None
    assert qr_code.get("alt") == "QR code for adding this Hush Line account to a 2FA app"
    assert secret is not None
    _assert_2fa_code_input_accessibility(
        soup,
        describedby_ids={"two-factor-setup-instructions", "two-factor-secret"},
    )


@pytest.mark.usefixtures("_authenticated_user")
def test_enable_2fa_invalid_code_has_accessible_error(client: FlaskClient) -> None:
    client.get(url_for("settings.enable_2fa"))

    response = client.post(
        url_for("settings.enable_2fa"),
        data={"verification_code": "000000"},
    )
    assert response.status_code == 400

    soup = BeautifulSoup(response.text, "html.parser")
    _assert_2fa_code_input_accessibility(
        soup,
        describedby_ids={
            "two-factor-setup-instructions",
            "two-factor-secret",
            "verification-code-error",
        },
        expects_error=True,
    )
    assert "Invalid 2FA code. Please try again." in soup.get_text(" ", strip=True)


def test_verify_2fa_login_has_accessible_error(
    client: FlaskClient, user: User, user_password: str
) -> None:
    user.totp_secret = "KBOVHCCELV67CYGOQ2QYU5SCNYVAREMH"
    db.session.commit()
    login_response = client.post(
        url_for("login"),
        data={
            "username": user.primary_username.username,
            "password": user_password,
        },
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    response = client.post(
        url_for("verify_2fa_login"),
        data={"verification_code": "000000"},
    )
    assert response.status_code == 401

    soup = BeautifulSoup(response.text, "html.parser")
    _assert_2fa_code_input_accessibility(
        soup,
        describedby_ids={"verification-code-help", "verification-code-error"},
        expects_error=True,
    )
    assert "Invalid 2FA code. Please try again." in soup.get_text(" ", strip=True)

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "screenshots" / "scenes.json"
CAPTURE_SCRIPT_PATH = REPO_ROOT / "scripts" / "capture-doc-screenshots.mjs"
INDUSTRY_FIELD_FORM_SELECTOR = (
    ".field-form:not(.field-form-new):has(.field-form-label:has-text('Industry'))"
)
INDUSTRY_FIELD_TOGGLE_SELECTOR = f"{INDUSTRY_FIELD_FORM_SELECTOR} .field-form-toggle"
INDUSTRY_FIELD_DELETE_SELECTOR = f"{INDUSTRY_FIELD_FORM_SELECTOR} button[name='delete_field']"


def _scene_map() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {scene["slug"]: scene for scene in manifest["scenes"]}


def test_docs_screenshots_manifest_covers_guest_directory_verified_subtabs() -> None:
    scenes = _scene_map()

    expected_paths = {
        "guest-directory-attorneys-closed-filters": "/directory",
        "guest-directory-attorneys-open-filters": "/directory",
        "guest-directory-attorneys-applied-filters": "/directory?country=US&region=CA",
        "guest-directory-attorney-adam-j-levitt": (
            "/directory/public-records/public-record~adam-j-levitt"
        ),
        "guest-directory-newsrooms": "/directory",
        "guest-directory-securedrop": "/directory",
        "guest-directory-globaleaks": "/directory",
    }

    for slug, path in expected_paths.items():
        scene = scenes[slug]
        assert scene["session"] == "guest"
        assert scene["path"] == path
        assert "viewports" not in scene
        assert "themes" not in scene

    assert scenes["guest-directory-attorneys-closed-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {
            "type": "wait_for",
            "selector": "#attorney-filters-toggle-shell:not([hidden]) #attorney-filters-toggle",
        },
    ]
    assert scenes["guest-directory-attorneys-open-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {
            "type": "wait_for",
            "selector": "#attorney-filters-toggle-shell:not([hidden]) #attorney-filters-toggle",
        },
        {"type": "click", "selector": "#attorney-filters-toggle"},
        {"type": "wait_for", "selector": "#attorney-filters-panel:not([hidden])"},
    ]
    assert scenes["guest-directory-attorneys-applied-filters"]["actions"] == [
        {"type": "click", "selector": "#public-records-tab"},
        {"type": "wait_for", "selector": "#public-records.tab-content.active"},
        {"type": "wait_for", "selector": "#attorney-filters-panel:not([hidden])"},
        {
            "type": "wait_for",
            "selector": "#attorney-country-filter:has(option:checked[value='United States'])",
        },
        {
            "type": "wait_for",
            "selector": "#attorney-region-filter:has(option:checked[value='CA'])",
        },
    ]
    assert scenes["guest-directory-attorney-adam-j-levitt"]["waitForSelector"] == "h2.submit"
    assert scenes["guest-directory-securedrop"]["actions"] == [
        {"type": "click", "selector": "#securedrop-tab"},
        {"type": "wait_for", "selector": "#securedrop.tab-content.active"},
    ]
    assert scenes["guest-directory-newsrooms"]["actions"] == [
        {"type": "click", "selector": "#newsrooms-tab"},
        {"type": "wait_for", "selector": "#newsrooms.tab-content.active"},
    ]
    assert scenes["guest-directory-globaleaks"]["actions"] == [
        {"type": "click", "selector": "#globaleaks-tab"},
        {"type": "wait_for", "selector": "#globaleaks.tab-content.active"},
    ]


def test_docs_screenshots_manifest_disables_full_page_for_heavy_directory_scenes() -> None:
    scenes = _scene_map()

    assert scenes["auth-admin-directory-all"]["captureModes"] == ["fold", "scroll"]
    assert scenes["guest-directory-newsrooms"]["captureModes"] == ["fold", "scroll"]
    assert scenes["guest-directory-all"]["captureModes"] == ["fold", "scroll"]


def test_docs_screenshot_capture_suppresses_first_load_splash() -> None:
    script = CAPTURE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'const FIRST_LOAD_SPLASH_SEEN_KEY = "hushline:first-load-splash-seen";' in script
    assert 'sessionStorage.setItem(splashStorageKey, "true")' in script
    assert "await context.addInitScript(" in script
    assert 'await context.route("**/static/css/style.css*"' in script
    assert "#first-load-splash" in script
    assert ".first-load-splash" in script


def test_docs_screenshots_manifest_artvandelay_notifications_waits_for_third_recipient() -> None:
    scenes = _scene_map()

    artvandelay_notifications = scenes["auth-artvandelay-settings-notifications"]

    assert artvandelay_notifications["session"] == "artvandelay"
    assert artvandelay_notifications["path"] == "/settings/notifications"
    assert artvandelay_notifications["waitForSelector"] == "a:has-text('board@vandelay.news')"


def test_docs_screenshots_manifest_guest_message_submission_skips_choice_list_fill() -> None:
    scenes = _scene_map()

    assert scenes["guest-message-submitted"]["actions"] == [
        {
            "type": "fill_if_exists",
            "selector": "#field_1, [name='field_1']",
            "value": "Technology",
        },
        {
            "type": "fill_if_exists",
            "selector": "#field_2, [name='field_2']",
            "value": "Screenshot test value 2",
        },
        {
            "type": "fill_if_exists",
            "selector": "#field_4, [name='field_4']",
            "value": "Screenshot test value 4",
        },
        {
            "type": "click_if_exists",
            "selector": "#messageForm input[type='checkbox']",
        },
        {
            "type": "fill_if_exists",
            "selector": "#content, textarea#content, textarea.form-field",
            "value": "Screenshot test message body.",
        },
        {"type": "solve_math_captcha"},
        {
            "type": "submit_form",
            "selector": "#messageForm",
            "waitForNetworkIdle": True,
        },
        {
            "type": "wait_for",
            "selector": "#reply-url",
        },
    ]


def test_docs_screenshots_manifest_guest_artvandelay_profile_scenes_reset_all_custom_fields() -> (
    None
):
    scenes = _scene_map()

    expected_cleanup = [
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_TOGGLE_SELECTOR,
        },
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_DELETE_SELECTOR,
            "acceptDialog": True,
            "waitForNetworkIdle": True,
        },
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_TOGGLE_SELECTOR,
        },
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_DELETE_SELECTOR,
            "acceptDialog": True,
            "waitForNetworkIdle": True,
        },
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_TOGGLE_SELECTOR,
        },
        {
            "type": "click_if_exists",
            "selector": INDUSTRY_FIELD_DELETE_SELECTOR,
            "acceptDialog": True,
            "waitForNetworkIdle": True,
        },
    ]

    assert (
        scenes["auth-artvandelay-profile-custom-form-setup-industry"]["actions"][:6]
        == expected_cleanup
    )
    assert (
        scenes["auth-artvandelay-profile-custom-form-reset-default-guest"]["actions"]
        == expected_cleanup
    )
    assert (
        scenes["auth-artvandelay-profile-custom-form-setup-industry-guest"]["actions"][:6]
        == expected_cleanup
    )


def test_docs_screenshots_manifest_artvandelay_profile_cleanup_accepts_delete_confirmations() -> (
    None
):
    scenes = _scene_map()

    reset_actions = scenes["auth-artvandelay-profile-custom-form-reset-default-guest"]["actions"]
    setup_actions = scenes["auth-artvandelay-profile-custom-form-setup-industry-guest"]["actions"]

    reset_delete_actions = [
        action
        for action in reset_actions
        if action.get("selector", "").endswith("button[name='delete_field']")
    ]
    setup_delete_actions = [
        action
        for action in setup_actions
        if action.get("selector", "").endswith("button[name='delete_field']")
    ]

    assert reset_delete_actions
    assert setup_delete_actions
    assert all(action["acceptDialog"] is True for action in reset_delete_actions)
    assert all(action["acceptDialog"] is True for action in setup_delete_actions)

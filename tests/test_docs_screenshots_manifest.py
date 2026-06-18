import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "screenshots" / "scenes.json"
CAPTURE_SCRIPT_PATH = REPO_ROOT / "scripts" / "capture-doc-screenshots.mjs"
ALLOWLIST_SCRIPT_PATH = REPO_ROOT / "scripts" / "resolve-doc-screenshot-allowlist.py"
INDUSTRY_FIELD_FORM_SELECTOR = (
    ".field-form:not(.field-form-new):has(.field-form-label:has-text('Industry'))"
)
INDUSTRY_FIELD_TOGGLE_SELECTOR = f"{INDUSTRY_FIELD_FORM_SELECTOR} .field-form-toggle"
INDUSTRY_FIELD_DELETE_SELECTOR = f"{INDUSTRY_FIELD_FORM_SELECTOR} button[name='delete_field']"


def _scene_map() -> dict[str, dict[str, Any]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {scene["slug"]: scene for scene in manifest["scenes"]}


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_allowlist_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "resolve_doc_screenshot_allowlist", ALLOWLIST_SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_screenshots_manifest_defaults_to_empty_generated_allowlist() -> None:
    manifest = _manifest()

    assert manifest["captureFiles"] == []


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


def test_docs_screenshots_manifest_includes_featured_directory_carousel() -> None:
    scenes = _scene_map()
    screenshots_readme = (REPO_ROOT / "docs" / "screenshots" / "README.md").read_text(
        encoding="utf-8"
    )

    featured_scene = scenes["guest-directory-featured-carousel"]

    assert featured_scene["title"] == "Directory - Featured Carousel"
    assert featured_scene["path"] == "/directory"
    assert featured_scene["session"] == "guest"
    assert featured_scene["captureModes"] == ["fold"]
    assert featured_scene["viewports"] == ["desktop"]
    assert featured_scene["themes"] == ["light"]
    assert (
        featured_scene["waitForSelector"]
        == "[data-featured-carousel].is-enhanced .featured-directory-slide.active"
    )
    assert (
        "./releases/latest/guest/guest-directory-featured-carousel-desktop-light-fold.png"
        in screenshots_readme
    )


def test_docs_screenshots_manifest_includes_decrypted_conversation_scenes() -> None:
    scenes = _scene_map()
    screenshots_readme = (REPO_ROOT / "docs" / "screenshots" / "README.md").read_text(
        encoding="utf-8"
    )
    dev_data = (REPO_ROOT / "scripts" / "dev_data.py").read_text(encoding="utf-8")

    inbox_scene = scenes["auth-artvandelay-inbox-conversations"]
    artvandelay_thread = scenes["auth-artvandelay-conversation-thread"]
    newman_thread = scenes["auth-newman-conversation-thread"]

    assert inbox_scene["path"] == "/inbox?type=conversations"
    assert inbox_scene["session"] == "artvandelay"
    assert inbox_scene["waitForSelector"] == ".conversation-summary"
    assert artvandelay_thread["path"] == "/conversation/33333333-3333-4333-8333-333333333333"
    assert artvandelay_thread["waitForSelector"] == (
        ".conversation-message-body:has-text('Human Fund')"
    )
    assert newman_thread["path"] == artvandelay_thread["path"]
    assert newman_thread["waitForSelector"] == (
        ".conversation-message-body:has-text('Hello, Newman.')"
    )
    assert "create_sample_conversations()" in dev_data
    assert "ECDH-P256-AES-GCM" in dev_data
    assert "PBKDF2-SHA-256" in dev_data
    assert (
        "./releases/latest/artvandelay/auth-artvandelay-conversation-thread-mobile-light-fold.png"
        in screenshots_readme
    )


def test_docs_screenshot_capture_suppresses_first_load_splash() -> None:
    script = CAPTURE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'const FIRST_LOAD_SPLASH_SEEN_KEY = "hushline:first-load-splash-seen";' in script
    assert 'sessionStorage.setItem(splashStorageKey, "true")' in script
    assert "await context.addInitScript(" in script
    assert 'await context.route("**/static/css/style.css*"' in script
    assert "#first-load-splash" in script
    assert ".first-load-splash" in script


def test_docs_screenshot_capture_filters_to_manifest_capture_files() -> None:
    script = CAPTURE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "const captureFiles = normalizeCaptureFiles(manifest.captureFiles);" in script
    assert "return null;" in script
    assert "captureFiles === null" in script
    assert "scene.alwaysVisit === true" in script
    assert "captureFiles !== null" in script
    assert "shouldVisitCaptureTarget(" in script
    assert "shouldCaptureFile(captureFiles, relativeFile)" in script
    assert "Required screenshot captures were not produced" in script


def test_docs_screenshot_capture_login_waits_for_fetch_driven_redirect() -> None:
    script = CAPTURE_SCRIPT_PATH.read_text(encoding="utf-8")
    login_body = script[
        script.index("async function login(") : script.index("async function runAction")
    ]

    assert 'const CHAT_PRIVATE_JWK_STORAGE_KEY = "hushline:chat-private-jwk";' in script
    assert "await page.click(\"button[type='submit']\");" in login_body
    assert 'window.location.pathname !== "/login"' in login_body
    assert "sessionStorage.getItem(storageKey)" in login_body
    assert "sessionStorage.setItem(storageKey, storageValue)" in login_body
    assert "await context.addInitScript(" in login_body
    assert "Promise.all" not in login_body


def test_docs_screenshot_capture_supports_scene_masks() -> None:
    script = CAPTURE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "function buildScreenshotOptions(page, scene)" in script
    assert "maskSelectors.join" in script
    assert "filter: blur(14px) !important;" in script
    assert "maskColor" not in script
    assert "...buildScreenshotOptions(page, scene)" in script
    assert "buildScreenshotOptions(page, scene)," in script


def test_docs_screenshot_allowlist_resolves_only_referenced_images(tmp_path: Path) -> None:
    script = _load_allowlist_script()
    website_dir = tmp_path / "website"
    docs_dir = tmp_path / "docs_repo"
    hushline_dir = tmp_path / "hushline"
    (website_dir / "src" / "pages").mkdir(parents=True)
    (docs_dir / "docs" / "docs" / "getting-started").mkdir(parents=True)
    (hushline_dir / "docs" / "screenshots").mkdir(parents=True)

    (website_dir / "src" / "pages" / "index.astro").write_text(
        "\n".join(
            [
                '<img src="/assets/img/screenshots/current/guest/used-from-website.png">',
                'import img from "../assets/img/screenshots/current/admin/imported.png";',
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "docs" / "docs" / "getting-started" / "secure-your-account.md").write_text(
        "![Scan QR](https://github.com/scidsg/hushline-screenshots/blob/main/"
        "releases/latest/artvandelay/auth-artvandelay-enable-2fa-desktop-light-fold.png"
        "?raw=true)",
        encoding="utf-8",
    )
    (hushline_dir / "README.md").write_text(
        "https://raw.githubusercontent.com/scidsg/hushline-screenshots/"
        "refs/heads/main/releases/latest/newman/used-from-docs.png",
        encoding="utf-8",
    )
    (hushline_dir / "docs" / "screenshots" / "scenes.json").write_text(
        '{"captureFiles":["guest/not-a-reference.png"]}',
        encoding="utf-8",
    )

    patterns = script.compile_reference_patterns("src/assets/img/screenshots")
    refs = (
        script.collect_references(
            website_dir,
            docs_only=False,
            patterns=patterns,
            screenshot_root="src/assets/img/screenshots",
        )
        | script.collect_references(
            docs_dir,
            docs_only=True,
            patterns=patterns,
            screenshot_root="src/assets/img/screenshots",
        )
        | script.collect_references(
            hushline_dir,
            docs_only=True,
            patterns=patterns,
            screenshot_root="src/assets/img/screenshots",
        )
    )

    assert refs == {
        "admin/imported.png",
        "artvandelay/auth-artvandelay-enable-2fa-desktop-light-fold.png",
        "guest/used-from-website.png",
        "newman/used-from-docs.png",
    }


def test_docs_screenshot_allowlist_filters_current_tree(tmp_path: Path) -> None:
    script = _load_allowlist_script()
    current_root = tmp_path / "current"
    filtered_root = tmp_path / "filtered"
    (current_root / "guest").mkdir(parents=True)
    (current_root / "guest" / "used.png").write_bytes(b"used")
    (current_root / "guest" / "unused.png").write_bytes(b"unused")

    script.copy_filtered_current(current_root, filtered_root, ["guest/used.png"])

    assert (filtered_root / "guest" / "used.png").read_bytes() == b"used"
    assert not (filtered_root / "guest" / "unused.png").exists()


def test_docs_screenshot_allowlist_rejects_symlinked_current_images(
    tmp_path: Path,
) -> None:
    script = _load_allowlist_script()
    current_root = tmp_path / "current"
    filtered_root = tmp_path / "filtered"
    sensitive_file = tmp_path / "hushline-website" / ".git" / "config"
    (current_root / "guest").mkdir(parents=True)
    sensitive_file.parent.mkdir(parents=True)
    sensitive_file.write_text(
        "url = https://x-access-token:SECRET@example.invalid\n", encoding="utf-8"
    )
    (current_root / "guest" / "used.png").symlink_to(sensitive_file)

    assert script.available_images(current_root) == set()

    with pytest.raises(SystemExit) as exc_info:
        script.copy_filtered_current(current_root, filtered_root, ["guest/used.png"])

    assert exc_info.value.code == 1
    assert not (filtered_root / "guest" / "used.png").exists()


def test_docs_screenshot_allowlist_can_reuse_capture_files_artifact(tmp_path: Path) -> None:
    script = _load_allowlist_script()
    refs_input = tmp_path / "capture_files.json"

    refs_input.write_text(
        json.dumps(
            [
                "guest/used.png",
                "guest/used.png",
                "artvandelay/auth-artvandelay-enable-2fa-desktop-light-fold.png",
            ]
        ),
        encoding="utf-8",
    )

    assert script.read_refs_input(refs_input) == [
        "artvandelay/auth-artvandelay-enable-2fa-desktop-light-fold.png",
        "guest/used.png",
    ]


def test_docs_screenshot_allowlist_rejects_unsafe_capture_files_artifact(tmp_path: Path) -> None:
    script = _load_allowlist_script()
    refs_input = tmp_path / "capture_files.json"

    refs_input.write_text(
        json.dumps(["guest/used.png", "../escape.png", "guest/script.js"]),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Unexpected captureFiles screenshot path"):
        script.read_refs_input(refs_input)


def test_docs_screenshots_manifest_artvandelay_notifications_waits_for_third_recipient() -> None:
    scenes = _scene_map()

    artvandelay_notifications = scenes["auth-artvandelay-settings-notifications"]

    assert artvandelay_notifications["session"] == "artvandelay"
    assert artvandelay_notifications["path"] == "/settings/notifications"
    assert artvandelay_notifications["waitForSelector"] == "a:has-text('board@vandelay.news')"


def test_docs_screenshots_manifest_masks_artvandelay_2fa_secret() -> None:
    scenes = _scene_map()

    enable_2fa = scenes["auth-artvandelay-enable-2fa"]

    assert enable_2fa["path"] == "/settings/auth"
    assert enable_2fa["screenshotMasks"] == [".qr", ".totp-secret"]


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


def test_docs_screenshots_manifest_marks_state_preparation_scenes_always_visit() -> None:
    scenes = _scene_map()

    state_preparation_slugs = {
        "auth-artvandelay-profile-custom-form-setup-industry",
        "auth-artvandelay-profile-custom-form-reset-default-guest",
        "auth-artvandelay-profile-custom-form-setup-industry-guest",
    }

    for slug in state_preparation_slugs:
        assert scenes[slug]["alwaysVisit"] is True


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

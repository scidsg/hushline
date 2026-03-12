import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_package_json_declares_node_20_plus() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    engines = package_json.get("engines", {})
    assert engines.get("node") == ">=20"


def test_client_side_encryption_has_platform_guards() -> None:
    js = (ROOT / "assets/js/client-side-encryption.js").read_text(encoding="utf-8")

    assert "function assertClientCryptoSupport()" in js
    assert "window.isSecureContext" in js
    assert "window.crypto.subtle" in js
    assert "window.ReadableStream" in js
    assert 'typeof BigInt === "undefined"' in js
    assert 'typeof openpgp === "undefined"' in js
    assert "function getDicewareWords()" in js
    assert "Encryption module failed to initialize." in js
    assert "Encryption padding dictionary is unavailable." in js
    assert "Encrypted email body field is missing." in js
    assert "assertClientCryptoSupport();" in js


def test_profile_template_avoids_inline_submit_handlers() -> None:
    template = (ROOT / "hushline/templates/profile.html").read_text(encoding="utf-8")

    assert 'id="messageForm"' in template
    assert 'onsubmit="' not in template


def test_submit_spinner_hooks_exist_for_scoped_forms() -> None:
    js = (ROOT / "assets/js/global.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert "form[data-submit-spinner='true']" in js
    assert "submit-button-label" in js
    assert "submit-button-spinner" in js
    assert 'attributeFilter: ["disabled"]' in js
    assert 'button[data-submit-spinner-init="true"]' in scss
    assert "transform: translate(-50%, -50%);" in scss
    assert "translate(-50%, -50%) rotate(360deg)" in scss
    assert "@keyframes submit-button-spinner-rotate" in scss


def test_directory_search_accessibility_hooks_exist() -> None:
    directory_template = (ROOT / "hushline/templates/directory.html").read_text(encoding="utf-8")
    directory_js = (ROOT / "assets/js/directory.js").read_text(encoding="utf-8")
    directory_verified_js = (ROOT / "assets/js/directory_verified.js").read_text(encoding="utf-8")
    directory_verified_static_js = (ROOT / "hushline/static/js/directory_verified.js").read_text(
        encoding="utf-8"
    )
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="directory-sticky-shell"' in directory_template
    assert 'id="directory-search-status"' in directory_template
    assert 'class="visually-hidden"' in directory_template
    assert 'role="status"' in directory_template
    assert 'aria-live="polite"' in directory_template
    assert (
        'const searchStatus = document.getElementById("directory-search-status");' in directory_js
    )
    assert (
        'const searchStatus = document.getElementById("directory-search-status");'
        in directory_verified_js
    )
    assert "Showing all users." in directory_js
    assert "Showing all" in directory_verified_js
    assert 'searchInput.placeholder = "Search attorneys...";' in directory_verified_js
    assert 'searchInput.placeholder = "Search GlobaLeaks instances...";' in directory_verified_js
    assert 'return "attorneys";' in directory_verified_js
    assert 'return "GlobaLeaks instances";' in directory_verified_js
    assert "user.city," in directory_verified_js
    assert "user.country," in directory_verified_js
    assert "user.subdivision," in directory_verified_js
    assert "Array.isArray(user.countries)" in directory_verified_js
    assert "function formatLocation(user)" in directory_verified_js
    assert "function buildLocationLine(user, query)" in directory_verified_js
    assert "user.country," in directory_verified_static_js
    assert "function formatLocation(user)" in directory_verified_static_js
    assert "function buildLocationLine(user, query)" in directory_verified_static_js
    assert ".directory-sticky-shell" in scss
    assert ".visually-hidden" in scss


def test_directory_sticky_active_tab_scroll_to_top_hook_exists() -> None:
    directory_verified_js = (ROOT / "assets/js/directory_verified.js").read_text(encoding="utf-8")

    assert 'clickedTab.classList.contains("active")' in directory_verified_js
    assert 'directoryTabs.classList.contains("is-sticky")' in directory_verified_js
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in directory_verified_js
    assert 'window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });' in (
        directory_verified_js
    )


def test_inbox_sticky_nav_hooks_exist() -> None:
    inbox_template = (ROOT / "hushline/templates/inbox.html").read_text(encoding="utf-8")
    inbox_js = (ROOT / "assets/js/inbox.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="inbox-tabs-nav"' in inbox_template
    assert 'const inboxTabsNav = document.querySelector(".inbox-tabs-nav");' in inbox_js
    assert "--inbox-tabs-top" in inbox_js
    assert ".inbox-tabs-nav {" in scss
    assert "position: sticky;" in scss


def test_settings_sticky_nav_hooks_exist() -> None:
    settings_template = (ROOT / "hushline/templates/settings/nav.html").read_text(
        encoding="utf-8",
    )
    settings_js = (ROOT / "assets/js/settings.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="settings-tabs"' in settings_template
    assert 'const settingsTabsNav = document.querySelector(".settings-tabs");' in settings_js
    assert "--settings-tabs-top" in settings_js
    assert ".settings-tabs {" in scss
    assert "position: sticky;" in scss

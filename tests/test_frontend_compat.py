import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_package_json_declares_node_18_plus() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    engines = package_json.get("engines", {})
    assert engines.get("node") == ">=18"


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
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

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
    assert ".visually-hidden" in scss


def test_inbox_sticky_nav_hooks_exist() -> None:
    inbox_template = (ROOT / "hushline/templates/inbox.html").read_text(encoding="utf-8")
    inbox_js = (ROOT / "assets/js/inbox.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="inbox-tabs-nav"' in inbox_template
    assert 'const inboxTabsNav = document.querySelector(".inbox-tabs-nav");' in inbox_js
    assert '--inbox-tabs-top' in inbox_js
    assert ".inbox-tabs-nav {" in scss
    assert "position: sticky;" in scss

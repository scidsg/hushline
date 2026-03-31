import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_package_json_declares_node_20_plus() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    engines = package_json.get("engines", {})
    assert engines.get("node") == ">=20"


def test_static_js_bundles_avoid_eval_wrappers() -> None:
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")

    assert 'devtool: isDev ? "source-map" : false,' in webpack_config

    for static_js in sorted((ROOT / "hushline/static/js").glob("*.js")):
        bundle = static_js.read_text(encoding="utf-8")
        assert "eval(" not in bundle, static_js.name
        assert "webpack://" not in bundle, static_js.name


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
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'id="messageForm"' in template
    assert 'onsubmit="' not in template
    assert "What's this?" in template
    assert 'class="badge badgeCaution"' in template
    assert 'role="tooltip"' in template
    assert ".badgeHelpTooltipGroup" in scss
    assert ".badgeHelpTrigger" in scss
    assert ".badgeHelpTooltip" in scss


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
    user_search_js = (ROOT / "assets/js/user_search.js").read_text(encoding="utf-8")
    directory_verified_static_js = (ROOT / "hushline/static/js/directory_verified.js").read_text(
        encoding="utf-8"
    )
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert 'class="directory-sticky-shell"' in directory_template
    assert 'id="directory-search-status"' in directory_template
    assert 'id="public-record-count"' in directory_template
    assert 'id="newsroom-count"' in directory_template
    assert 'id="all-filters-toggle"' in directory_template
    assert 'id="all-filters-panel"' in directory_template
    assert 'id="attorney-filters-toggle"' in directory_template
    assert 'id="attorney-filters-panel"' in directory_template
    assert 'id="newsroom-filters-toggle"' in directory_template
    assert 'id="newsroom-filters-panel"' in directory_template
    assert "Clear Filters" in directory_template
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
    assert 'const publicRecordCountBadge = document.getElementById("public-record-count");' in (
        directory_verified_js
    )
    assert 'const allFiltersToggle = document.getElementById("all-filters-toggle");' in (
        directory_verified_js
    )
    assert 'const allFiltersPanel = document.getElementById("all-filters-panel");' in (
        directory_verified_js
    )
    assert 'const allListingTypeFilter = document.getElementById("all-listing-type-filter");' in (
        directory_verified_js
    )
    assert (
        'const attorneyFiltersToggle = document.getElementById("attorney-filters-toggle");'
        in directory_verified_js
    )
    assert (
        'const attorneyFiltersPanel = document.getElementById("attorney-filters-panel");'
        in directory_verified_js
    )
    assert (
        'const attorneyCountryFilter = document.getElementById("attorney-country-filter");'
        in directory_verified_js
    )
    assert (
        'const attorneyRegionFilter = document.getElementById("attorney-region-filter");'
        in directory_verified_js
    )
    assert "Showing all users." in directory_js
    assert "Showing all" in directory_verified_js
    assert 'searchInput.placeholder = "Search attorneys...";' in directory_verified_js
    assert 'searchInput.placeholder = "Search GlobaLeaks instances...";' in directory_verified_js
    assert 'return "attorneys";' in directory_verified_js
    assert 'return "GlobaLeaks instances";' in directory_verified_js
    assert "window.location.search" in directory_verified_js
    assert "window.location.search" in directory_verified_static_js
    assert "function escapeHtml(value)" in user_search_js
    assert "return escapeHtml(sourceText);" in user_search_js
    assert '<mark class="search-highlight">${escapeHtml(match[0])}</mark>' in user_search_js
    assert "function createLocationFilterController(config)" in directory_verified_js
    assert "controller.updateCountBadge = function () {" in directory_verified_js
    assert "updateLocationFilterCountBadges();" in directory_verified_js
    assert 'const directoryPath = window.location.pathname.replace(/\\/$/, "");' in (
        directory_verified_js
    )
    assert "fetch(`${directoryPath}/users.json${search}`, requestOptions)" in directory_verified_js
    assert 'metadataPath: "all-filters.json"' in directory_verified_js
    assert 'metadataPath: "attorney-filters.json"' in directory_verified_js
    assert 'metadataPath: "newsroom-filters.json"' in directory_verified_js
    assert "fetch(`${directoryPath}/${controller.metadataPath}${search}`)" in directory_verified_js
    assert 'const directoryPath = window.location.pathname.replace(/\\/$/, "");' in (directory_js)
    assert "fetch(`${directoryPath}/users.json`)" in directory_js
    assert "window.history.replaceState" in directory_verified_js
    assert "new AbortController();" in directory_verified_js
    assert 'controller.panel.setAttribute("aria-busy", isLoading ? "true" : "false");' in (
        directory_verified_js
    )
    assert "controller.inferredCountryForRegionCode = function (regionCode) {" in (
        directory_verified_js
    )
    assert "controller.updateSelectExpandedLabels = function (isExpanded) {" in (
        directory_verified_js
    )
    assert 'controller.countryFilter.addEventListener("change", function () {' in (
        directory_verified_js
    )
    assert 'controller.regionFilter.addEventListener("change", function () {' in (
        directory_verified_js
    )
    assert 'select.addEventListener("focus", syncExpandedLabelsOnOpen);' in directory_verified_js
    assert 'select.addEventListener("blur", syncExpandedLabelsOnClose);' in directory_verified_js
    assert "controller.countryFilter.value = controller.inferredCountryForRegionCode(" in (
        directory_verified_js
    )
    assert "controller.updateClearVisibility();" in directory_verified_js
    assert 'button[type="submit"]' not in directory_template
    assert "setSearchStatus(`Updating ${controller.resultsLabelPlural} results.`);" in (
        directory_verified_js
    )
    assert "controller.panel.hidden = !controller.panel.hidden;" in directory_verified_js
    assert 'controller.toggle.textContent = isExpanded ? "Hide Filters" : "Show Filters";' in (
        directory_verified_js
    )
    assert "Hide Filters" in directory_verified_static_js
    assert "Show Filters" in directory_verified_static_js
    assert "eval(" not in directory_verified_static_js
    assert "webpack://" not in directory_verified_static_js
    assert "all_tab_sort_transliterated" in directory_verified_js
    assert "all_tab_sort_normalized" in directory_verified_js
    assert "show_caution_badge" in directory_js
    assert "show_caution_badge" in directory_verified_js
    assert "all_tab_sort_transliterated" in directory_verified_static_js
    assert "all_tab_sort_normalized" in directory_verified_static_js
    assert "show_caution_badge" in directory_verified_static_js
    assert "all_tab_sort_transliterated ??" in directory_verified_js
    assert "all_tab_sort_transliterated ??" in directory_verified_static_js
    assert "localeCompare" not in directory_verified_js
    assert "localeCompare" not in directory_verified_static_js
    assert "Caution: display name may be mistaken for admin" in directory_js
    assert "Caution: display name may be mistaken for admin" in directory_verified_js
    assert "Caution: display name may be mistaken for admin" in directory_verified_static_js
    assert "const safeDisplayName = userSearch.escapeHtml(" in directory_js
    assert "const safeDisplayName = userSearch.escapeHtml(" in directory_verified_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No bio");' in directory_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No bio");' in directory_verified_js
    assert 'const safeBio = userSearch.escapeHtml(user.bio || "No description");' in (
        directory_verified_js
    )
    safe_user_aria = (
        'aria-label="${safeUserType}, Display name:${safeDisplayName}, Username: '
        '${safeUsername}, Bio: ${safeBio}"'
    )
    assert safe_user_aria in directory_js
    assert safe_user_aria in directory_verified_js
    assert (
        'aria-label="${safeListingType}, Display name:${safeDisplayName}, Description: ${safeBio}"'
        in directory_verified_js
    )
    assert (
        'aria-label="${userType}, Display name:${user.display_name || user.primary_username}'
        not in (directory_verified_js)
    )
    assert (
        'aria-label="${userType}, Display name:${user.display_name || user.primary_username}'
        not in (directory_js)
    )
    assert "user.city," in directory_verified_js
    assert "user.country," in directory_verified_js
    assert "user.subdivision," in directory_verified_js
    assert "Array.isArray(user.countries)" in directory_verified_js
    assert "users.json" in directory_verified_static_js
    assert "all-filters.json" in directory_verified_static_js
    assert "attorney-filters.json" in directory_verified_static_js
    assert "replaceState" in directory_verified_static_js
    assert ".directory-sticky-shell" in scss
    assert ".directory-filter-panel" in scss
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


def test_settings_field_delete_confirmation_blocks_submit_on_cancel() -> None:
    js = (ROOT / "assets/js/settings-fields.js").read_text(encoding="utf-8")

    assert '.querySelectorAll(".message-field-delete-button")' in js
    assert "return confirm(" in js


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


def test_profile_location_settings_use_country_select_and_dependency_script() -> None:
    profile_template = (ROOT / "hushline/templates/settings/profile.html").read_text(
        encoding="utf-8"
    )
    profile_forms_template = (ROOT / "hushline/templates/settings/profile-forms.html").read_text(
        encoding="utf-8"
    )
    location_asset_js = (ROOT / "assets/js/settings-location.js").read_text(encoding="utf-8")
    location_js = (ROOT / "hushline/static/js/settings-location.js").read_text(encoding="utf-8")
    webpack_config = (ROOT / "webpack.config.js").read_text(encoding="utf-8")
    scss = (ROOT / "assets/scss/style.scss").read_text(encoding="utf-8")

    assert "settings-location.js" in profile_template
    assert "autocomplete='country-name'" in profile_forms_template
    assert "autocomplete='address-level2'" in profile_forms_template
    assert "autocomplete='address-level1'" in profile_forms_template
    assert "data_states_url=url_for('.profile_states')" in profile_forms_template
    assert "data_cities_url=url_for('.profile_cities')" in profile_forms_template
    assert 'const countryInput = document.getElementById("country");' in location_asset_js
    assert '"settings-location",' in webpack_config
    assert 'const countryInput = document.getElementById("country");' in location_js
    assert 'const subdivisionInput = document.getElementById("subdivision");' in location_js
    assert 'const cityInput = document.getElementById("city");' in location_js
    assert "const statesUrl = countryInput.dataset.statesUrl;" in location_js
    assert "const citiesUrl = subdivisionInput.dataset.citiesUrl;" in location_js
    assert "async function loadStates(selectedValue)" in location_js
    assert "async function loadCities(selectedValue)" in location_js
    assert 'countryInput.addEventListener("change", async function () {' in location_js
    assert 'subdivisionInput.addEventListener("change", async function () {' in location_js
    assert "${statesUrl}?country=${encodeURIComponent(country)}" in location_js
    assert "const params = new URLSearchParams({" in location_js
    assert '#country:has(option:checked[value=""])' in scss
    assert '#subdivision:has(option:checked[value=""])' in scss
    assert '#city:has(option:checked[value=""])' in scss


def test_settings_field_builder_select_hooks_are_wrapper_safe() -> None:
    settings_fields_js = (ROOT / "assets/js/settings-fields.js").read_text(encoding="utf-8")

    assert "function getFieldFormRoot(fieldType)" in settings_fields_js
    assert 'return fieldType.closest("form");' in settings_fields_js
    assert (
        "const choicesContainer = getFieldFormRoot(fieldType)?.querySelector(" in settings_fields_js
    )
    assert (
        "const requiredCheckboxContainer = getFieldFormRoot(fieldType)?.querySelector("
        in settings_fields_js
    )
    assert "const requiredCheckbox = getFieldFormRoot(fieldType)?.querySelector(" in (
        settings_fields_js
    )

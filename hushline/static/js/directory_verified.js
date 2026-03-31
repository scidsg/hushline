document.addEventListener("DOMContentLoaded", function () {
  const legacyCountryNameByCode = {
    au: "Australia",
    at: "Austria",
    be: "Belgium",
    fi: "Finland",
    fr: "France",
    de: "Germany",
    in: "India",
    it: "Italy",
    jp: "Japan",
    lu: "Luxembourg",
    nl: "Netherlands",
    pt: "Portugal",
    sg: "Singapore",
    es: "Spain",
    se: "Sweden",
    us: "United States",
  };
  const userSearch = window.HushlineUserSearch;
  const directoryPath = window.location.pathname.replace(/\/$/, "");
  const directoryTabs = document.getElementById("directory-tabs");
  const directoryTabList = document.getElementById("directory-tab-list");
  const scrollLeftButton = directoryTabs?.querySelector(".scroll-left");
  const scrollRightButton = directoryTabs?.querySelector(".scroll-right");
  const desktopTabScrollMediaQuery = window.matchMedia("(min-width: 641px)");
  const tabs = document.querySelectorAll(".tab[data-tab]");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const searchStatus = document.getElementById("directory-search-status");
  const publicRecordCountBadge = document.getElementById("public-record-count");
  const newsroomCountBadge = document.getElementById("newsroom-count");
  const allFiltersToggleShell = document.getElementById("all-filters-toggle-shell");
  const allFiltersPanelShell = document.getElementById("all-filters-panel-shell");
  const allFiltersToggle = document.getElementById("all-filters-toggle");
  const allFiltersPanel = document.getElementById("all-filters-panel");
  const allCountryFilter = document.getElementById("all-country-filter");
  const allRegionFilter = document.getElementById("all-region-filter");
  const allListingTypeFilter = document.getElementById("all-listing-type-filter");
  const attorneyFiltersToggleShell = document.getElementById("attorney-filters-toggle-shell");
  const attorneyFiltersPanelShell = document.getElementById("attorney-filters-panel-shell");
  const attorneyFiltersToggle = document.getElementById("attorney-filters-toggle");
  const attorneyFiltersPanel = document.getElementById("attorney-filters-panel");
  const attorneyCountryFilter = document.getElementById("attorney-country-filter");
  const attorneyRegionFilter = document.getElementById("attorney-region-filter");
  const newsroomFiltersToggleShell = document.getElementById("newsroom-filters-toggle-shell");
  const newsroomFiltersPanelShell = document.getElementById("newsroom-filters-panel-shell");
  const newsroomFiltersToggle = document.getElementById("newsroom-filters-toggle");
  const newsroomFiltersPanel = document.getElementById("newsroom-filters-panel");
  const newsroomCountryFilter = document.getElementById("newsroom-country-filter");
  const newsroomRegionFilter = document.getElementById("newsroom-region-filter");
  const initialMarkup = new Map();
  let userData = [];
  let allTabUserData = [];
  let hasRenderedSearch = false;
  let directoryDataRequestController = null;
  let directoryDataLoadingController = null;
  let loadedDirectorySearch = window.location.search;

  tabPanels.forEach((panel) => {
    initialMarkup.set(panel.id, panel.innerHTML);
  });

  function setSearchStatus(message) {
    if (searchStatus) {
      searchStatus.textContent = message;
    }
  }

  function normalizedCountryFilterValue(value) {
    const normalizedValue = value?.trim() || "";
    if (!normalizedValue) {
      return "";
    }

    return legacyCountryNameByCode[normalizedValue.toLowerCase()] || normalizedValue;
  }

  function activeTabName() {
    return document.querySelector(".tab.active")?.getAttribute("data-tab") || "all";
  }

  function activePanel() {
    return document.querySelector(".tab-content.active") || document.getElementById("all");
  }

  function usersForTab(tab = activeTabName()) {
    return tab === "all" ? allTabUserData : userData;
  }

  function updateTabScrollControls() {
    if (!directoryTabs || !directoryTabList || !scrollLeftButton || !scrollRightButton) {
      return;
    }

    const overflowWidth = directoryTabList.scrollWidth - directoryTabList.clientWidth;
    const hasOverflow = desktopTabScrollMediaQuery.matches && overflowWidth > 1;
    const canScrollLeft = hasOverflow && directoryTabList.scrollLeft > 1;
    const canScrollRight = hasOverflow && directoryTabList.scrollLeft < overflowWidth - 1;

    directoryTabs.classList.toggle("directory-tabs-overflowing", hasOverflow);
    scrollLeftButton.hidden = !canScrollLeft;
    scrollRightButton.hidden = !canScrollRight;
  }

  function scrollDirectoryTabs(direction) {
    if (!directoryTabList) {
      return;
    }

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
      .matches;
    const scrollDistance = Math.max(directoryTabList.clientWidth * 0.75, 200);

    directoryTabList.scrollBy({
      left: direction * scrollDistance,
      behavior: prefersReducedMotion ? "auto" : "smooth",
    });
  }

  function updatePlaceholder() {
    const activeTab = activeTabName();
    if (!searchInput) {
      return;
    }

    if (activeTab === "verified") {
      searchInput.placeholder = "Search verified users...";
      return;
    }

    if (activeTab === "public-records") {
      searchInput.placeholder = "Search attorneys...";
      return;
    }

    if (activeTab === "newsrooms") {
      searchInput.placeholder = "Search newsrooms...";
      return;
    }

    if (activeTab === "globaleaks") {
      searchInput.placeholder = "Search GlobaLeaks instances...";
      return;
    }

    if (activeTab === "securedrop") {
      searchInput.placeholder = "Search SecureDrop instances...";
      return;
    }

    searchInput.placeholder = "Search directory...";
  }

  function scopeLabel() {
    const activeTab = activeTabName();
    if (activeTab === "verified") {
      return "verified users";
    }

    if (activeTab === "public-records") {
      return "attorneys";
    }

    if (activeTab === "newsrooms") {
      return "newsrooms";
    }

    if (activeTab === "globaleaks") {
      return "GlobaLeaks instances";
    }

    if (activeTab === "securedrop") {
      return "SecureDrop instances";
    }

    return "directory entries";
  }

  function isAttorneyUser(user) {
    return user.account_category === "lawyer";
  }

  function isNewsroomUser(user) {
    return user.account_category === "newsroom";
  }

  function matchesAttorneyFilters(user) {
    const selectedCountry = attorneyCountryFilter?.value.trim() || "";
    const selectedRegion = attorneyRegionFilter?.value.trim() || "";

    if (selectedCountry && user.country !== selectedCountry) {
      return false;
    }

    if (
      selectedRegion &&
      user.subdivision_code !== selectedRegion &&
      user.subdivision !== selectedRegion
    ) {
      return false;
    }

    return true;
  }

  function matchesTab(user, tab) {
    if (
      tab === "verified" &&
      (
        !user.is_verified ||
        user.is_public_record ||
        user.is_globaleaks ||
        user.is_newsroom ||
        user.is_securedrop
      )
    ) {
      return false;
    }

    if (tab === "public-records") {
      if (!user.is_public_record && !isAttorneyUser(user)) {
        return false;
      }

      if (isAttorneyUser(user) && !matchesAttorneyFilters(user)) {
        return false;
      }
    }

    if (tab === "globaleaks" && !user.is_globaleaks) {
      return false;
    }

    if (tab === "newsrooms" && !user.is_newsroom) {
      if (!isNewsroomUser(user)) {
        return false;
      }
    }

    if (tab === "securedrop" && !user.is_securedrop) {
      return false;
    }

    return true;
  }

  function filterUsers(query, tab = activeTabName()) {
    const normalizedQuery = query.trim().toLowerCase();

    return usersForTab(tab).filter((user) => {
      if (!matchesTab(user, tab)) {
        return false;
      }

      if (normalizedQuery === "") {
        return true;
      }

      const countries = Array.isArray(user.countries) ? user.countries.join(" ") : "";
      const searchText = userSearch.normalizeSearchText([
        user.primary_username,
        user.display_name,
        user.bio,
        user.city,
        user.country,
        user.subdivision,
        countries,
      ]);
      return userSearch.matchesQuery(searchText, normalizedQuery);
    });
  }

  function allTabSortValue(user) {
    return user.display_name || user.primary_username || "";
  }

  function compareAllTabSortStrings(a, b) {
    if (a < b) {
      return -1;
    }

    if (a > b) {
      return 1;
    }

    return 0;
  }

  function allTabTransliteratedSortValue(user) {
    return (
      user.all_tab_sort_transliterated ??
      allTabSortValue(user).normalize("NFKC").toLowerCase()
    );
  }

  function allTabNormalizedSortValue(user) {
    return (
      user.all_tab_sort_normalized || allTabSortValue(user).normalize("NFKC").toLowerCase()
    );
  }

  function compareAllTabUsers(a, b) {
    if (a.is_admin !== b.is_admin) {
      return a.is_admin ? -1 : 1;
    }

    if (a.show_caution_badge !== b.show_caution_badge) {
      return a.show_caution_badge ? 1 : -1;
    }

    const transliteratedResult = compareAllTabSortStrings(
      allTabTransliteratedSortValue(a),
      allTabTransliteratedSortValue(b),
    );
    if (transliteratedResult !== 0) {
      return transliteratedResult;
    }

    return compareAllTabSortStrings(
      allTabNormalizedSortValue(a),
      allTabNormalizedSortValue(b),
    );
  }

  function sortAllTabUsers(users) {
    return [...users].sort(compareAllTabUsers);
  }

  function highlightMatch(text, query) {
    return userSearch.highlightQuery(text || "", query);
  }

  function buildBadges(user, tab) {
    let badgeContainer = "";

    if (user.is_public_record) {
      if (tab === "all") {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Attorney listing">⚖️ Attorney</span>';
      }
      if (user.is_automated) {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>';
      }
      return badgeContainer;
    }

    if (user.is_securedrop) {
      if (tab !== "securedrop") {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="SecureDrop listing">🛡️ SecureDrop</span>';
      }
      if (user.is_automated) {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>';
      }
      return badgeContainer;
    }

    if (user.is_newsroom) {
      if (tab !== "newsrooms") {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Newsroom listing">📰 Newsroom</span>';
      }
      if (user.is_automated) {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>';
      }
      return badgeContainer;
    }

    if (user.is_globaleaks) {
      if (tab !== "globaleaks") {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="GlobaLeaks listing">🌐 GlobaLeaks</span>';
      }
      if (user.is_automated) {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>';
      }
      return badgeContainer;
    }

    if (user.is_admin) {
      badgeContainer +=
        '<span class="badge" role="img" aria-label="Administrator account">⚙️ Admin</span>';
    }

    if (user.is_verified) {
      badgeContainer +=
        '<span class="badge" role="img" aria-label="Verified account">⭐️ Verified</span>';
    }

    if (user.show_caution_badge) {
      badgeContainer +=
        '<span class="badge badgeCaution" role="img" aria-label="Caution: display name may be mistaken for admin">⚠️ Caution</span>';
    }

    if (tab === "all" && !user.has_pgp_key) {
      badgeContainer +=
        '<span class="badge" role="img" aria-label="Info-only account">📇 Info Only</span>';
    }

    return badgeContainer;
  }

  function buildAutomatedListingCard(user, query, tab) {
    const safeDisplayName = userSearch.escapeHtml(user.display_name || "");
    const safeBio = userSearch.escapeHtml(user.bio || "No description");
    const safeProfileUrl = userSearch.escapeHtml(user.profile_url || "#");
    const displayNameHighlighted = highlightMatch(user.display_name, query);
    const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";
    let listingType = "SecureDrop listing";
    if (user.is_public_record) {
      listingType = "Public record listing";
    } else if (user.is_newsroom) {
      listingType = "Newsroom listing";
    } else if (user.is_globaleaks) {
      listingType = "GlobaLeaks listing";
    }
    const safeListingType = userSearch.escapeHtml(listingType);

    return `
      <article class="user" aria-label="${safeListingType}, Display name:${safeDisplayName}, Description: ${safeBio}">
        <h3>${displayNameHighlighted}</h3>
        <div class="badgeContainer">${buildBadges(user, tab)}</div>
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${safeProfileUrl}" aria-label="View read-only listing for ${safeDisplayName}">View Listing</a>
        </div>
      </article>
    `;
  }

  function buildUserCard(user, query, tab) {
    const safeDisplayName = userSearch.escapeHtml(
      user.display_name || user.primary_username || "",
    );
    const safeUsername = userSearch.escapeHtml(user.primary_username || "");
    const safeBio = userSearch.escapeHtml(user.bio || "No bio");
    const safeProfileUrl = userSearch.escapeHtml(user.profile_url || "#");
    const displayNameHighlighted = highlightMatch(
      user.display_name || user.primary_username,
      query,
    );
    const usernameHighlighted = highlightMatch(user.primary_username, query);
    const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";

    if (user.is_public_record || user.is_globaleaks || user.is_newsroom || user.is_securedrop) {
      return buildAutomatedListingCard(user, query, tab);
    }

    const userType = user.is_admin
      ? `${user.is_verified ? "Verified" : ""} admin user`
      : `${user.is_verified ? "Verified" : ""} User`;
    const safeUserType = userSearch.escapeHtml(userType);
    const badges = buildBadges(user, tab);

    return `
      <article class="user" aria-label="${safeUserType}, Display name:${safeDisplayName}, Username: ${safeUsername}, Bio: ${safeBio}">
        <h3>${displayNameHighlighted}</h3>
        <p class="meta">@${usernameHighlighted}</p>
        ${badges ? `<div class="badgeContainer">${badges}</div>` : ""}
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${safeProfileUrl}" aria-label="${safeDisplayName}'s profile">View Profile</a>
        </div>
      </article>
    `;
  }

  function appendSection(panel, label, users, query, tab) {
    if (!users.length) {
      return;
    }

    if (label) {
      const sectionLabel = document.createElement("p");
      sectionLabel.className = "label searchLabel";
      sectionLabel.textContent = label;
      panel.appendChild(sectionLabel);
    }

    const userListContainer = document.createElement("div");
    userListContainer.className = "user-list";
    userListContainer.innerHTML = users.map((user) => buildUserCard(user, query, tab)).join("");
    panel.appendChild(userListContainer);
  }

  function renderPanelContent(
    panel,
    users,
    query,
    tab,
    { introMarkup = "", showEmptyMessage = true } = {},
  ) {
    panel.innerHTML = introMarkup;

    if (users.length === 0) {
      if (showEmptyMessage) {
        panel.insertAdjacentHTML(
          "beforeend",
          '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>',
        );
      }
      return;
    }

    const realUsers = users.filter(
      (user) =>
        !user.is_public_record &&
        !user.is_globaleaks &&
        !user.is_newsroom &&
        !user.is_securedrop,
    );
    const withPgp = realUsers.filter((user) => user.has_pgp_key);
    const infoOnly = realUsers.filter((user) => !user.has_pgp_key);

    if (tab === "all") {
      appendSection(panel, "", sortAllTabUsers(users), query, tab);
      return;
    }

    if (tab === "verified") {
      appendSection(panel, "", withPgp, query, tab);
      appendSection(panel, "📇 Info-Only Accounts", infoOnly, query, tab);
      return;
    }

    appendSection(panel, "", users, query, tab);
  }

  function displayUsers(users, query) {
    const panel = activePanel();
    const tab = activeTabName();
    if (!panel) {
      return;
    }

    renderPanelContent(panel, users, query, tab);
  }

  function panelIntroMarkup(panelId) {
    return document.getElementById(panelId)?.querySelector(".dirMeta")?.outerHTML || "";
  }

  function buildDefaultPanelMarkup(tab) {
    const panel = document.createElement("div");
    const introMarkup = panelIntroMarkup(tab);
    const showEmptyMessage = tab !== "public-records";

    renderPanelContent(panel, filterUsers("", tab), "", tab, {
      introMarkup,
      showEmptyMessage,
    });

    return panel.innerHTML;
  }

  function refreshInitialMarkup() {
    ["public-records", "newsrooms", "all"].forEach((panelId) => {
      if (document.getElementById(panelId)) {
        initialMarkup.set(panelId, buildDefaultPanelMarkup(panelId));
      }
    });
  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    const panel = activePanel();
    const currentScopeLabel = scopeLabel();
    const hasQuery = query.length > 0;

    if (clearIcon) {
      clearIcon.style.visibility = hasQuery ? "visible" : "hidden";
      clearIcon.hidden = !hasQuery;
      clearIcon.setAttribute("aria-hidden", hasQuery ? "false" : "true");
    }

    if (query.length === 0) {
      if (panel && initialMarkup.has(panel.id)) {
        panel.innerHTML = initialMarkup.get(panel.id);
      }
      if (hasRenderedSearch) {
        setSearchStatus(`Showing all ${currentScopeLabel}.`);
      }
      hasRenderedSearch = false;
      return;
    }

    const filteredUsers = filterUsers(query);
    displayUsers(filteredUsers, query);
    setSearchStatus(
      filteredUsers.length === 1
        ? `Found 1 ${currentScopeLabel.slice(0, -1)} matching "${query}".`
        : `Found ${filteredUsers.length} ${currentScopeLabel} matching "${query}".`,
    );
    hasRenderedSearch = true;
  }

  function removeSearchParams(search, paramNames) {
    const params = new URLSearchParams(search);
    paramNames.forEach((paramName) => {
      params.delete(paramName);
    });
    const nextSearch = params.toString();
    return nextSearch ? `?${nextSearch}` : "";
  }

  function sharedDirectorySearch(search) {
    return removeSearchParams(search, ["all_country", "all_region", "all_listing_type"]);
  }

  function allTabDirectorySearch(search) {
    return removeSearchParams(search, [
      "country",
      "region",
      "newsroom_country",
      "newsroom_region",
    ]);
  }

  function createLocationFilterController(config) {
    const controller = {
      ...config,
      loading: false,
      metadata: { countries: [], regions: {} },
      metadataRequest: null,
    };

    if (!controller.countryFilter || !controller.regionFilter) {
      return null;
    }

    controller.hasActiveFilters = function () {
      return Boolean(
        controller.countryFilter.value.trim() ||
          controller.regionFilter.value.trim() ||
          controller.listingTypeFilter?.value.trim(),
      );
    };

    controller.updateToggle = function () {
      if (!controller.toggle || !controller.panel) {
        return;
      }

      const isExpanded = !controller.panel.hidden;
      controller.toggle.setAttribute("aria-expanded", isExpanded ? "true" : "false");
      controller.toggle.textContent = isExpanded ? "Hide Filters" : "Show Filters";
    };

    controller.updateVisibility = function () {
      const tabIsActive = activeTabName() === controller.tabName;

      if (controller.toggleShell) {
        controller.toggleShell.hidden = !tabIsActive;
      }

      if (controller.panelShell) {
        controller.panelShell.hidden = !tabIsActive;
      }
    };

    controller.resultsCount = function () {
      return filterUsers("", controller.tabName).length;
    };

    controller.updateCountBadge = function () {
      if (controller.countBadge) {
        controller.countBadge.textContent = controller.resultsCount().toString();
      }
    };

    controller.buildSearch = function () {
      const params = new URLSearchParams(window.location.search);
      const country = controller.countryFilter.value.trim();
      const region = controller.regionFilter.value.trim();

      if (country) {
        params.set(controller.countryParam, country);
      } else {
        params.delete(controller.countryParam);
      }

      if (region) {
        params.set(controller.regionParam, region);
      } else {
        params.delete(controller.regionParam);
      }

      if (controller.listingTypeParam) {
        const listingType = controller.listingTypeFilter?.value.trim() || "";
        if (listingType) {
          params.set(controller.listingTypeParam, listingType);
        } else {
          params.delete(controller.listingTypeParam);
        }
      }

      const nextSearch = params.toString();
      return nextSearch ? `?${nextSearch}` : "";
    };

    controller.setSelectExpandedState = function (select, isExpanded) {
      if (!select) {
        return;
      }

      select.dataset.showSelectedCount = isExpanded ? "true" : "false";
    };

    controller.setSelectOpenState = function (select, isOpen) {
      if (!select) {
        return;
      }

      select.classList.toggle("select-open", isOpen);
    };

    controller.updateClearVisibility = function () {
      if (!controller.panel) {
        return;
      }

      const resetActions = controller.panel.querySelector(`#${controller.actionsId}`);
      if (!resetActions) {
        return;
      }

      resetActions.hidden = !controller.hasActiveFilters();
    };

    controller.countryLabelForValue = function (value) {
      if (!value) {
        return "";
      }

      const country = Array.isArray(controller.metadata.countries)
        ? controller.metadata.countries.find((item) => item.code === value)
        : null;
      if (country?.label) {
        return country.label;
      }

      const selectedCountryOption = Array.from(controller.countryFilter.options).find(
        (option) => option.value === value,
      );
      if (selectedCountryOption?.textContent) {
        return selectedCountryOption.textContent.replace(/\s+\(\d+\)$/, "");
      }

      return normalizedCountryFilterValue(value);
    };

    controller.updateCountryLabels = function () {
      const selectedCountry = controller.countryFilter.value;
      const showSelectedCount = controller.countryFilter.dataset.showSelectedCount === "true";
      const countries = Array.isArray(controller.metadata.countries)
        ? [...controller.metadata.countries]
        : [];

      if (selectedCountry && !countries.some((country) => country.code === selectedCountry)) {
        countries.unshift({
          code: selectedCountry,
          label: controller.countryLabelForValue(selectedCountry),
          count: 0,
        });
      }

      controller.countryFilter.innerHTML = '<option value="">All</option>';

      countries.forEach((country) => {
        const option = document.createElement("option");
        option.value = country.code;
        option.textContent =
          country.code === selectedCountry && !showSelectedCount
            ? country.label
            : `${country.label} (${country.count})`;
        if (country.code === selectedCountry) {
          option.selected = true;
        }
        controller.countryFilter.appendChild(option);
      });

      if (!countries.some((country) => country.code === selectedCountry)) {
        controller.countryFilter.value = "";
      }
    };

    controller.updateListingTypeLabels = function () {
      if (!controller.listingTypeFilter) {
        return;
      }

      const selectedListingType = controller.listingTypeFilter.value;
      const showSelectedCount = controller.listingTypeFilter.dataset.showSelectedCount === "true";
      const listingTypes = Array.isArray(controller.metadata.listing_types)
        ? [...controller.metadata.listing_types]
        : [];
      const selectedListingTypeOption = Array.from(controller.listingTypeFilter.options).find(
        (option) => option.value === selectedListingType,
      );

      if (
        selectedListingType &&
        !listingTypes.some((listingType) => listingType.code === selectedListingType)
      ) {
        listingTypes.unshift({
          code: selectedListingType,
          label:
            selectedListingTypeOption?.textContent?.replace(/\s+\(\d+\)$/, "") ||
            selectedListingType,
          count: 0,
        });
      }

      controller.listingTypeFilter.innerHTML = '<option value="">All</option>';

      listingTypes.forEach((listingType) => {
        const option = document.createElement("option");
        option.value = listingType.code;
        option.textContent =
          listingType.code === selectedListingType && !showSelectedCount
            ? listingType.label
            : `${listingType.label} (${listingType.count})`;
        if (listingType.code === selectedListingType) {
          option.selected = true;
        }
        controller.listingTypeFilter.appendChild(option);
      });

      if (!listingTypes.some((listingType) => listingType.code === selectedListingType)) {
        controller.listingTypeFilter.value = "";
      }
    };

    controller.inferredCountryForRegionCode = function (regionCode) {
      if (!regionCode) {
        return "";
      }

      const normalizedRegionCode = regionCode.trim().toLowerCase();
      const regionsByCountry =
        controller.metadata.regions && typeof controller.metadata.regions === "object"
          ? controller.metadata.regions
          : {};

      for (const [countryName, countryRegions] of Object.entries(regionsByCountry)) {
        if (!Array.isArray(countryRegions)) {
          continue;
        }

        const matchingRegion = countryRegions.find(
          (region) => String(region.code).trim().toLowerCase() === normalizedRegionCode,
        );
        if (matchingRegion) {
          return countryName;
        }
      }

      return "";
    };

    controller.updateRegionOptions = function () {
      const selectedCountry = controller.countryFilter.value;
      const selectedRegion = controller.regionFilter.value;
      const showSelectedCount = controller.regionFilter.dataset.showSelectedCount === "true";
      const regionsByCountry =
        controller.metadata.regions && typeof controller.metadata.regions === "object"
          ? controller.metadata.regions
          : {};
      const availableRegions = selectedCountry
        ? Array.isArray(regionsByCountry[selectedCountry])
          ? regionsByCountry[selectedCountry]
          : []
        : Object.values(regionsByCountry).flatMap((countryRegions) =>
            Array.isArray(countryRegions) ? countryRegions : [],
          );

      controller.regionFilter.innerHTML = '<option value="">All</option>';

      if (selectedCountry) {
        availableRegions.forEach((region) => {
          const option = document.createElement("option");
          option.value = region.code;
          option.textContent =
            region.code === selectedRegion && !showSelectedCount
              ? region.label
              : `${region.label} (${region.count})`;
          if (region.code === selectedRegion) {
            option.selected = true;
          }
          controller.regionFilter.appendChild(option);
        });
      } else {
        Object.entries(regionsByCountry).forEach(([countryName, countryRegions]) => {
          if (!Array.isArray(countryRegions) || !countryRegions.length) {
            return;
          }

          const optgroup = document.createElement("optgroup");
          optgroup.label = countryName;

          countryRegions.forEach((region) => {
            const option = document.createElement("option");
            option.value = region.code;
            option.textContent =
              region.code === selectedRegion && !showSelectedCount
                ? region.label
                : `${region.label} (${region.count})`;
            if (region.code === selectedRegion) {
              option.selected = true;
            }
            optgroup.appendChild(option);
          });

          controller.regionFilter.appendChild(optgroup);
        });
      }

      if (!availableRegions.some((region) => region.code === selectedRegion)) {
        controller.regionFilter.value = "";
      }

      const disabledByCountry = !availableRegions.length;
      controller.regionFilter.dataset.disabledByCountry = disabledByCountry ? "true" : "false";
      controller.regionFilter.disabled = controller.loading || disabledByCountry;
      controller.updateClearVisibility();
    };

    controller.updateSelectExpandedLabels = function (isExpanded) {
      controller.setSelectExpandedState(controller.countryFilter, isExpanded);
      controller.setSelectExpandedState(controller.regionFilter, isExpanded);
      controller.setSelectExpandedState(controller.listingTypeFilter, isExpanded);
      controller.updateCountryLabels();
      controller.updateRegionOptions();
      controller.updateListingTypeLabels();
    };

    controller.applyFromSearch = function (search) {
      const params = new URLSearchParams(search);
      controller.countryFilter.value = normalizedCountryFilterValue(
        params.get(controller.countryParam),
      );
      controller.regionFilter.value = params.get(controller.regionParam) || "";
      if (controller.listingTypeFilter && controller.listingTypeParam) {
        controller.listingTypeFilter.value = params.get(controller.listingTypeParam) || "";
      }
      if (!controller.countryFilter.value && controller.regionFilter.value) {
        controller.countryFilter.value = controller.inferredCountryForRegionCode(
          controller.regionFilter.value,
        );
      }
      controller.updateCountryLabels();
      controller.updateRegionOptions();
      controller.updateListingTypeLabels();

      if (controller.panel) {
        controller.updateToggle();
        controller.updateClearVisibility();
      }
    };

    controller.setLoadingState = function (isLoading) {
      if (!controller.panel) {
        return;
      }

      controller.loading = isLoading;
      controller.panel.setAttribute("aria-busy", isLoading ? "true" : "false");
      controller.countryFilter.disabled = isLoading;

      const disabledByCountry = controller.regionFilter.dataset.disabledByCountry === "true";
      controller.regionFilter.disabled = isLoading || disabledByCountry;
      if (controller.listingTypeFilter) {
        controller.listingTypeFilter.disabled = isLoading;
      }

      const resetLink = controller.panel.querySelector("a");
      if (resetLink) {
        resetLink.setAttribute("aria-disabled", isLoading ? "true" : "false");
        resetLink.tabIndex = isLoading ? -1 : 0;
      }
    };

    controller.ensureMetadata = function (search = window.location.search) {
      if (controller.metadataRequest && controller.metadataSearch === search) {
        return controller.metadataRequest;
      }

      controller.metadataSearch = search;
      const metadataRequest = fetch(`${directoryPath}/${controller.metadataPath}${search}`)
        .then((response) => {
          if (!response.ok) {
            throw new Error("Network response was not ok");
          }
          return response.json();
        })
        .then((data) => {
          if (controller.metadataSearch !== search) {
            return data;
          }

          controller.metadata = data;
          controller.applyFromSearch(search);
          return data;
        })
        .catch((error) => {
          if (controller.metadataSearch === search) {
            controller.metadataRequest = null;
          }
          console.error(`Failed to load ${controller.resultsLabelPlural} filter metadata:`, error);
          return null;
        });

      controller.metadataRequest = metadataRequest;
      return metadataRequest;
    };

    controller.refreshResults = async function () {
      if (!controller.panel) {
        return;
      }

      const nextSearch = controller.buildSearch();
      if (controller.loading || loadedDirectorySearch === nextSearch) {
        return;
      }
      setSearchStatus(`Updating ${controller.resultsLabelPlural} results.`);
      setDirectoryUrl(nextSearch);

      try {
        await requestDirectoryData(nextSearch, { loadingController: controller });
        if (!searchInput.value.trim()) {
          const count = controller.resultsCount();
          setSearchStatus(
            count === 1
              ? `Showing 1 matching ${controller.resultsLabelSingular}.`
              : `Showing ${count} matching ${controller.resultsLabelPlural}.`,
          );
        }
      } catch (error) {
        if (error.name === "AbortError") {
          return;
        }

        setDirectoryUrl(loadedDirectorySearch);
        controller.applyFromSearch(loadedDirectorySearch);
        setSearchStatus(`Unable to update ${controller.resultsLabelPlural} results.`);
        console.error(`Failed to update ${controller.resultsLabelPlural} results:`, error);
      }
    };

    controller.bindEvents = function () {
      if (controller.toggle && controller.panel) {
        controller.updateToggle();
        controller.toggle.addEventListener("click", function () {
          controller.panel.hidden = !controller.panel.hidden;
          controller.updateToggle();
        });
      }

      if (!controller.panel) {
        return;
      }

      const resetLink = controller.panel.querySelector("a");
      const syncExpandedLabelsOnOpen = function (event) {
        if (
          event.type === "keydown" &&
          event.key !== "ArrowDown" &&
          event.key !== "ArrowUp" &&
          event.key !== "Enter" &&
          event.key !== " "
        ) {
          return;
        }

        controller.updateSelectExpandedLabels(true);
      };
      const syncExpandedLabelsOnClose = function () {
        controller.updateSelectExpandedLabels(false);
      };
      const syncChevronOnOpen = function (event) {
        if (
          event.type === "keydown" &&
          event.key !== "ArrowDown" &&
          event.key !== "ArrowUp" &&
          event.key !== "Enter" &&
          event.key !== " "
        ) {
          return;
        }

        controller.setSelectOpenState(event.currentTarget, true);
      };
      const syncChevronOnClose = function (event) {
        controller.setSelectOpenState(event.currentTarget, false);
      };

      controller.countryFilter.addEventListener("change", function () {
        controller.updateCountryLabels();
        controller.updateRegionOptions();
        syncExpandedLabelsOnClose();
        controller.setSelectOpenState(controller.countryFilter, false);
        void controller.refreshResults();
      });

      controller.regionFilter.addEventListener("change", function () {
        if (!controller.countryFilter.value && controller.regionFilter.value) {
          controller.countryFilter.value = controller.inferredCountryForRegionCode(
            controller.regionFilter.value,
          );
          controller.updateRegionOptions();
        }
        controller.updateCountryLabels();
        controller.updateClearVisibility();
        syncExpandedLabelsOnClose();
        controller.setSelectOpenState(controller.regionFilter, false);
        void controller.refreshResults();
      });

      if (controller.listingTypeFilter) {
        controller.listingTypeFilter.addEventListener("change", function () {
          controller.updateListingTypeLabels();
          controller.updateClearVisibility();
          syncExpandedLabelsOnClose();
          controller.setSelectOpenState(controller.listingTypeFilter, false);
          void controller.refreshResults();
        });
      }

      [controller.countryFilter, controller.regionFilter, controller.listingTypeFilter]
        .filter(Boolean)
        .forEach((select) => {
          select.addEventListener("focus", syncExpandedLabelsOnOpen);
          select.addEventListener("pointerdown", syncExpandedLabelsOnOpen);
          select.addEventListener("keydown", syncExpandedLabelsOnOpen);
          select.addEventListener("blur", syncExpandedLabelsOnClose);
          select.addEventListener("pointerdown", syncChevronOnOpen);
          select.addEventListener("keydown", syncChevronOnOpen);
          select.addEventListener("blur", syncChevronOnClose);
        });

      if (resetLink) {
        resetLink.addEventListener("click", function (event) {
          event.preventDefault();
          if (controller.loading) {
            return;
          }

          controller.countryFilter.value = "";
          controller.regionFilter.value = "";
          if (controller.listingTypeFilter) {
            controller.listingTypeFilter.value = "";
          }
          controller.updateCountryLabels();
          controller.updateRegionOptions();
          controller.updateListingTypeLabels();
          syncExpandedLabelsOnClose();
          void controller.refreshResults();
        });
      }
    };

    return controller;
  }

  const locationFilterControllers = [
    createLocationFilterController({
      tabName: "all",
      toggleShell: allFiltersToggleShell,
      panelShell: allFiltersPanelShell,
      toggle: allFiltersToggle,
      panel: allFiltersPanel,
      countryFilter: allCountryFilter,
      regionFilter: allRegionFilter,
      listingTypeFilter: allListingTypeFilter,
      actionsId: "all-filters-actions",
      metadataPath: "all-filters.json",
      countryParam: "all_country",
      regionParam: "all_region",
      listingTypeParam: "all_listing_type",
      resultsLabelSingular: "directory entry",
      resultsLabelPlural: "directory entries",
    }),
    createLocationFilterController({
      tabName: "public-records",
      countBadge: publicRecordCountBadge,
      toggleShell: attorneyFiltersToggleShell,
      panelShell: attorneyFiltersPanelShell,
      toggle: attorneyFiltersToggle,
      panel: attorneyFiltersPanel,
      countryFilter: attorneyCountryFilter,
      regionFilter: attorneyRegionFilter,
      actionsId: "attorney-filters-actions",
      metadataPath: "attorney-filters.json",
      countryParam: "country",
      regionParam: "region",
      resultsLabelSingular: "attorney",
      resultsLabelPlural: "attorneys",
    }),
    createLocationFilterController({
      tabName: "newsrooms",
      countBadge: newsroomCountBadge,
      toggleShell: newsroomFiltersToggleShell,
      panelShell: newsroomFiltersPanelShell,
      toggle: newsroomFiltersToggle,
      panel: newsroomFiltersPanel,
      countryFilter: newsroomCountryFilter,
      regionFilter: newsroomRegionFilter,
      actionsId: "newsroom-filters-actions",
      metadataPath: "newsroom-filters.json",
      countryParam: "newsroom_country",
      regionParam: "newsroom_region",
      resultsLabelSingular: "newsroom",
      resultsLabelPlural: "newsrooms",
    }),
  ].filter(Boolean);

  function updateLocationFilterVisibility() {
    locationFilterControllers.forEach((controller) => {
      controller.updateVisibility();
    });
  }

  function updateLocationFilterCountBadges() {
    locationFilterControllers.forEach((controller) => {
      controller.updateCountBadge();
    });
  }

  function refreshLocationFilterMetadata(search = window.location.search) {
    return Promise.all(
      locationFilterControllers.map((controller) => controller.ensureMetadata(search)),
    );
  }

  function setDirectoryUrl(search) {
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}${search}${window.location.hash}`,
    );
  }

  function loadData(search = window.location.search, options = {}) {
    const requestOptions = {};
    if (options.signal) {
      requestOptions.signal = options.signal;
    }

    const fetchUsers = (search) =>
      fetch(`${directoryPath}/users.json${search}`, requestOptions).then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      });

    return Promise.all([
      fetchUsers(sharedDirectorySearch(search)),
      fetchUsers(allTabDirectorySearch(search)),
      refreshLocationFilterMetadata(search),
    ]).then(([directoryData, nextAllTabUserData]) => {
      userData = directoryData;
      allTabUserData = nextAllTabUserData;
      loadedDirectorySearch = search;
      updateLocationFilterCountBadges();
      refreshInitialMarkup();
      handleSearchInput();
    });
  }

  function requestDirectoryData(search = window.location.search, options = {}) {
    const { loadingController = null } = options;

    if (directoryDataRequestController) {
      directoryDataRequestController.abort();
    }

    if (directoryDataLoadingController && directoryDataLoadingController !== loadingController) {
      directoryDataLoadingController.setLoadingState(false);
    }

    const controller = new AbortController();
    directoryDataRequestController = controller;
    directoryDataLoadingController = loadingController;

    if (loadingController) {
      loadingController.setLoadingState(true);
    }

    return loadData(search, { signal: controller.signal }).finally(() => {
      if (directoryDataRequestController === controller) {
        directoryDataRequestController = null;
        if (directoryDataLoadingController === loadingController) {
          if (loadingController) {
            loadingController.setLoadingState(false);
          }
          directoryDataLoadingController = null;
        }
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", handleSearchInput);
  }

  if (clearIcon) {
    clearIcon.addEventListener("click", function () {
      if (!searchInput) {
        return;
      }

      searchInput.value = "";
      clearIcon.style.visibility = "hidden";
      clearIcon.hidden = true;
      clearIcon.setAttribute("aria-hidden", "true");
      handleSearchInput();
    });
  }

  locationFilterControllers.forEach((controller) => {
    controller.bindEvents();
  });

  window.activateTab = function (selectedTab) {
    const targetPanel = document.getElementById(selectedTab.getAttribute("aria-controls"));
    if (!targetPanel) {
      return;
    }

    tabPanels.forEach((panel) => {
      panel.hidden = true;
      panel.style.display = "none";
      panel.classList.remove("active");
    });

    tabs.forEach((tab) => {
      tab.setAttribute("aria-selected", "false");
      tab.classList.remove("active");
    });

    selectedTab.setAttribute("aria-selected", "true");
    selectedTab.classList.add("active");
    targetPanel.hidden = false;
    targetPanel.style.display = "block";
    targetPanel.classList.add("active");
    selectedTab.scrollIntoView({ block: "nearest", inline: "nearest" });

    updateLocationFilterVisibility();
    updatePlaceholder();
    handleSearchInput();
    requestAnimationFrame(updateTabScrollControls);
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", function (event) {
      const clickedTab = event.currentTarget;
      const stickyShell = document.querySelector(".directory-sticky-shell");
      const directoryTabs = document.querySelector(".directory-tabs");
      const isStickyActiveTabClick =
        clickedTab.classList.contains("active") &&
        ((stickyShell && stickyShell.classList.contains("is-sticky")) ||
          (directoryTabs && directoryTabs.classList.contains("is-sticky")));

      if (isStickyActiveTabClick) {
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
          .matches;
        window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
        return;
      }

      window.activateTab(clickedTab);
    });
    tab.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      event.preventDefault();
      const tabArray = Array.from(tabs);
      const currentIndex = tabArray.indexOf(event.currentTarget);
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextIndex = (currentIndex + direction + tabArray.length) % tabArray.length;
      const nextTab = tabArray[nextIndex];
      if (nextTab) {
        window.activateTab(nextTab);
        nextTab.focus();
      }
    });
  });

  const defaultTab = document.querySelector(".tab.active") || tabs[0];
  if (defaultTab) {
    window.activateTab(defaultTab);
  }

  const stickyShell = document.querySelector(".directory-sticky-shell");
  const searchBox = document.querySelector(".directory-search");
  if (directoryTabs || stickyShell) {
    const updateStickyState = () => {
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight;
      const stickyAnchor = stickyShell || directoryTabs;

      if (stickyAnchor) {
        stickyAnchor.style.setProperty("--directory-sticky-top", `${stickyTop}px`);
        const stickyAnchorTop = stickyAnchor.getBoundingClientRect().top;
        const isSticky = window.scrollY > stickyTop + 1 && stickyAnchorTop <= stickyTop;
        stickyShell?.classList.toggle("is-sticky", isSticky);
        directoryTabs?.classList.toggle("is-sticky", isSticky);
        searchBox?.classList.toggle("is-sticky", isSticky);
      }
    };

    updateStickyState();
    window.addEventListener("scroll", updateStickyState, { passive: true });
    window.addEventListener("hashchange", () => {
      requestAnimationFrame(updateStickyState);
    });
    window.addEventListener("resize", updateStickyState);
  }

  if (directoryTabList && scrollLeftButton && scrollRightButton) {
    scrollLeftButton.addEventListener("click", function () {
      scrollDirectoryTabs(-1);
    });

    scrollRightButton.addEventListener("click", function () {
      scrollDirectoryTabs(1);
    });

    directoryTabList.addEventListener("scroll", updateTabScrollControls, { passive: true });
    window.addEventListener("resize", updateTabScrollControls);

    if (typeof desktopTabScrollMediaQuery.addEventListener === "function") {
      desktopTabScrollMediaQuery.addEventListener("change", updateTabScrollControls);
    } else if (typeof desktopTabScrollMediaQuery.addListener === "function") {
      desktopTabScrollMediaQuery.addListener(updateTabScrollControls);
    }

    updateTabScrollControls();
  }

  updatePlaceholder();
  locationFilterControllers.forEach((controller) => {
    void controller.ensureMetadata();
  });
  requestDirectoryData().catch((error) => {
    if (error.name === "AbortError") {
      return;
    }

    console.error("Failed to load user data:", error);
  });
});

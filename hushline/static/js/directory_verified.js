document.addEventListener("DOMContentLoaded", function () {
  const userSearch = window.HushlineUserSearch;
  const directoryPath = window.location.pathname.replace(/\/$/, "");
  const tabs = document.querySelectorAll(".tab[data-tab]");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const searchStatus = document.getElementById("directory-search-status");
  const publicRecordCountBadge = document.getElementById("public-record-count");
  const attorneyFiltersToggleShell = document.getElementById("attorney-filters-toggle-shell");
  const attorneyFiltersPanelShell = document.getElementById("attorney-filters-panel-shell");
  const attorneyFiltersToggle = document.getElementById("attorney-filters-toggle");
  const attorneyFiltersPanel = document.getElementById("attorney-filters-panel");
  const attorneyCountryFilter = document.getElementById("attorney-country-filter");
  const attorneyRegionFilter = document.getElementById("attorney-region-filter");
  const initialMarkup = new Map();
  let userData = [];
  let hasRenderedSearch = false;
  let attorneyFiltersLoading = false;
  let attorneyFilterMetadata = { countries: [], regions: {} };
  let attorneyFilterMetadataRequest = null;
  let directoryDataRequestController = null;
  let loadedDirectorySearch = window.location.search;

  tabPanels.forEach((panel) => {
    initialMarkup.set(panel.id, panel.innerHTML);
  });

  function setSearchStatus(message) {
    if (searchStatus) {
      searchStatus.textContent = message;
    }
  }

  function updateAttorneyFiltersToggle() {
    if (!attorneyFiltersToggle || !attorneyFiltersPanel) {
      return;
    }

    const isExpanded = !attorneyFiltersPanel.hidden;
    attorneyFiltersToggle.setAttribute("aria-expanded", isExpanded ? "true" : "false");
    attorneyFiltersToggle.textContent = isExpanded ? "Hide Filters" : "Show Filters";
  }

  function updateAttorneyFilterVisibility() {
    const attorneyTabIsActive = activeTabName() === "public-records";

    if (attorneyFiltersToggleShell) {
      attorneyFiltersToggleShell.hidden = !attorneyTabIsActive;
    }

    if (attorneyFiltersPanelShell) {
      attorneyFiltersPanelShell.hidden = !attorneyTabIsActive;
    }
  }

  function activeTabName() {
    return document.querySelector(".tab.active")?.getAttribute("data-tab") || "all";
  }

  function activePanel() {
    return document.querySelector(".tab-content.active") || document.getElementById("all");
  }

  function attorneyResultsCount() {
    return filterUsers("", "public-records").length;
  }

  function updatePublicRecordCountBadge() {
    if (publicRecordCountBadge) {
      publicRecordCountBadge.textContent = attorneyResultsCount().toString();
    }
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

    if (activeTab === "globaleaks") {
      return "GlobaLeaks instances";
    }

    if (activeTab === "securedrop") {
      return "SecureDrop instances";
    }

    return "directory entries";
  }

  function matchesTab(user, tab) {
    if (
      tab === "verified" &&
      (!user.is_verified || user.is_public_record || user.is_globaleaks || user.is_securedrop)
    ) {
      return false;
    }

    if (tab === "public-records" && !user.is_public_record) {
      return false;
    }

    if (tab === "globaleaks" && !user.is_globaleaks) {
      return false;
    }

    if (tab === "securedrop" && !user.is_securedrop) {
      return false;
    }

    return true;
  }

  function filterUsers(query, tab = activeTabName()) {
    const normalizedQuery = query.trim().toLowerCase();

    return userData.filter((user) => {
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

  function highlightMatch(text, query) {
    return userSearch.highlightQuery(text || "", query);
  }

  function sortedByDisplayName(entries) {
    return [...entries].sort((a, b) =>
      (a.display_name || "").localeCompare(b.display_name || "", undefined, {
        sensitivity: "base",
      }),
    );
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

    if (user.is_public_record || user.is_globaleaks || user.is_securedrop) {
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
      (user) => !user.is_public_record && !user.is_globaleaks && !user.is_securedrop,
    );
    const withPgp = realUsers.filter((user) => user.has_pgp_key);
    const infoOnly = realUsers.filter((user) => !user.has_pgp_key);

    if (tab === "all") {
      appendSection(panel, "", sortedByDisplayName(users), query, tab);
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
    if (document.getElementById("public-records")) {
      initialMarkup.set("public-records", buildDefaultPanelMarkup("public-records"));
    }

    if (document.getElementById("all")) {
      initialMarkup.set("all", buildDefaultPanelMarkup("all"));
    }
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

  function buildAttorneyFilterSearch() {
    const params = new URLSearchParams(window.location.search);
    const country = attorneyCountryFilter?.value.trim() || "";
    const region = attorneyRegionFilter?.value.trim() || "";

    if (country) {
      params.set("country", country);
    } else {
      params.delete("country");
    }

    if (region) {
      params.set("region", region);
    } else {
      params.delete("region");
    }

    const nextSearch = params.toString();
    return nextSearch ? `?${nextSearch}` : "";
  }

  function applyAttorneyFiltersFromSearch(search) {
    if (!attorneyCountryFilter || !attorneyRegionFilter) {
      return;
    }

    const params = new URLSearchParams(search);
    attorneyCountryFilter.value = params.get("country") || "";
    attorneyRegionFilter.value = params.get("region") || "";
    if (!attorneyCountryFilter.value && attorneyRegionFilter.value) {
      attorneyCountryFilter.value = inferredCountryForRegionCode(attorneyRegionFilter.value);
    }
    updateAttorneyCountryLabels();
    updateAttorneyRegionOptions();

    if (attorneyFiltersPanel) {
      attorneyFiltersPanel.hidden = !(attorneyCountryFilter.value || attorneyRegionFilter.value);
      updateAttorneyFiltersToggle();
      updateAttorneyFiltersClearVisibility();
    }
  }

  function setAttorneyFiltersLoadingState(isLoading) {
    if (!attorneyFiltersPanel) {
      return;
    }

    attorneyFiltersLoading = isLoading;
    attorneyFiltersPanel.setAttribute("aria-busy", isLoading ? "true" : "false");

    if (attorneyCountryFilter) {
      attorneyCountryFilter.disabled = isLoading;
    }

    if (attorneyRegionFilter) {
      const disabledByCountry = attorneyRegionFilter.dataset.disabledByCountry === "true";
      attorneyRegionFilter.disabled = isLoading || disabledByCountry;
    }

    const resetLink = attorneyFiltersPanel.querySelector("a");
    if (resetLink) {
      resetLink.setAttribute("aria-disabled", isLoading ? "true" : "false");
      resetLink.tabIndex = isLoading ? -1 : 0;
    }
  }

  function updateAttorneyFiltersClearVisibility() {
    if (!attorneyFiltersPanel || !attorneyCountryFilter || !attorneyRegionFilter) {
      return;
    }

    const resetActions = attorneyFiltersPanel.querySelector("#attorney-filters-actions");
    if (!resetActions) {
      return;
    }

    resetActions.hidden = !(attorneyCountryFilter.value || attorneyRegionFilter.value);
  }

  function updateAttorneyCountryLabels() {
    if (!attorneyCountryFilter) {
      return;
    }

    const selectedCountry = attorneyCountryFilter.value;
    const showSelectedCount = attorneyCountryFilter.dataset.showSelectedCount === "true";

    Array.from(attorneyCountryFilter.options).forEach((option) => {
      if (!option.value) {
        return;
      }

      const country = Array.isArray(attorneyFilterMetadata.countries)
        ? attorneyFilterMetadata.countries.find((item) => item.code === option.value)
        : null;
      if (!country) {
        return;
      }

      option.textContent =
        option.value === selectedCountry && !showSelectedCount
          ? country.label
          : `${country.label} (${country.count})`;
    });
  }

  function setAttorneySelectExpandedState(select, isExpanded) {
    if (!select) {
      return;
    }

    select.dataset.showSelectedCount = isExpanded ? "true" : "false";
  }

  function setAttorneySelectOpenState(select, isOpen) {
    if (!select) {
      return;
    }

    select.classList.toggle("select-open", isOpen);
  }

  function updateAttorneySelectExpandedLabels(isExpanded) {
    setAttorneySelectExpandedState(attorneyCountryFilter, isExpanded);
    setAttorneySelectExpandedState(attorneyRegionFilter, isExpanded);
    updateAttorneyCountryLabels();
    updateAttorneyRegionOptions();
  }

  function inferredCountryForRegionCode(regionCode) {
    if (!regionCode) {
      return "";
    }

    const normalizedRegionCode = regionCode.trim().toLowerCase();
    const regionsByCountry =
      attorneyFilterMetadata.regions && typeof attorneyFilterMetadata.regions === "object"
        ? attorneyFilterMetadata.regions
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
  }

  function updateAttorneyRegionOptions() {
    if (!attorneyCountryFilter || !attorneyRegionFilter) {
      return;
    }

    const selectedCountry = attorneyCountryFilter.value;
    const selectedRegion = attorneyRegionFilter.value;
    const showSelectedCount = attorneyRegionFilter.dataset.showSelectedCount === "true";
    const regionsByCountry =
      attorneyFilterMetadata.regions && typeof attorneyFilterMetadata.regions === "object"
        ? attorneyFilterMetadata.regions
        : {};
    const availableRegions = selectedCountry
      ? Array.isArray(regionsByCountry[selectedCountry])
        ? regionsByCountry[selectedCountry]
        : []
      : Object.values(regionsByCountry).flatMap((countryRegions) =>
          Array.isArray(countryRegions) ? countryRegions : [],
        );

    attorneyRegionFilter.innerHTML = '<option value="">All</option>';

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
        attorneyRegionFilter.appendChild(option);
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

        attorneyRegionFilter.appendChild(optgroup);
      });
    }

    if (!availableRegions.some((region) => region.code === selectedRegion)) {
      attorneyRegionFilter.value = "";
    }

    const disabledByCountry = !availableRegions.length;
    attorneyRegionFilter.dataset.disabledByCountry = disabledByCountry ? "true" : "false";
    attorneyRegionFilter.disabled = attorneyFiltersLoading || disabledByCountry;
    updateAttorneyFiltersClearVisibility();
  }

  function ensureAttorneyFilterMetadata() {
    if (!attorneyCountryFilter || !attorneyRegionFilter) {
      return Promise.resolve(null);
    }

    if (attorneyFilterMetadataRequest) {
      return attorneyFilterMetadataRequest;
    }

      attorneyFilterMetadataRequest = fetch(`${directoryPath}/attorney-filters.json`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then((data) => {
        attorneyFilterMetadata = data;
        updateAttorneyCountryLabels();
        updateAttorneyRegionOptions();
        return data;
      })
      .catch((error) => {
        attorneyFilterMetadataRequest = null;
        console.error("Failed to load attorney filter metadata:", error);
        return null;
      });

    return attorneyFilterMetadataRequest;
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

    return fetch(`${directoryPath}/users.json${search}`, requestOptions)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then((data) => {
        userData = data;
        loadedDirectorySearch = search;
        updatePublicRecordCountBadge();
        refreshInitialMarkup();
        handleSearchInput();
      });
  }

  function requestDirectoryData(search = window.location.search, options = {}) {
    const { showAttorneyFilterLoadingState = false } = options;

    if (directoryDataRequestController) {
      directoryDataRequestController.abort();
    }

    const controller = new AbortController();
    directoryDataRequestController = controller;

    if (showAttorneyFilterLoadingState) {
      setAttorneyFiltersLoadingState(true);
    }

    return loadData(search, { signal: controller.signal }).finally(() => {
      if (directoryDataRequestController === controller) {
        directoryDataRequestController = null;
        if (showAttorneyFilterLoadingState) {
          setAttorneyFiltersLoadingState(false);
        }
      }
    });
  }

  async function refreshAttorneyResults() {
    if (!attorneyFiltersPanel) {
      return;
    }

    const nextSearch = buildAttorneyFilterSearch();
    if (attorneyFiltersLoading || loadedDirectorySearch === nextSearch) {
      return;
    }
    setSearchStatus("Updating attorney results.");
    setDirectoryUrl(nextSearch);

    try {
      await requestDirectoryData(nextSearch, { showAttorneyFilterLoadingState: true });
      if (!searchInput.value.trim()) {
        const count = attorneyResultsCount();
        setSearchStatus(
          count === 1 ? "Showing 1 matching attorney." : `Showing ${count} matching attorneys.`,
        );
      }
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }

      setDirectoryUrl(loadedDirectorySearch);
      applyAttorneyFiltersFromSearch(loadedDirectorySearch);
      setSearchStatus("Unable to update attorney results.");
      console.error("Failed to update attorney results:", error);
    }
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

  if (attorneyFiltersToggle && attorneyFiltersPanel) {
    updateAttorneyFiltersToggle();
    attorneyFiltersToggle.addEventListener("click", function () {
      attorneyFiltersPanel.hidden = !attorneyFiltersPanel.hidden;
      updateAttorneyFiltersToggle();
    });
  }

  if (attorneyFiltersPanel && attorneyCountryFilter && attorneyRegionFilter) {
    const resetLink = attorneyFiltersPanel.querySelector("a");
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

      updateAttorneySelectExpandedLabels(true);
    };
    const syncExpandedLabelsOnClose = function () {
      updateAttorneySelectExpandedLabels(false);
    };
    const syncAttorneyChevronOnOpen = function (event) {
      if (
        event.type === "keydown" &&
        event.key !== "ArrowDown" &&
        event.key !== "ArrowUp" &&
        event.key !== "Enter" &&
        event.key !== " "
      ) {
        return;
      }

      setAttorneySelectOpenState(event.currentTarget, true);
    };
    const syncAttorneyChevronOnClose = function (event) {
      setAttorneySelectOpenState(event.currentTarget, false);
    };

    attorneyCountryFilter.addEventListener("change", async function () {
      await ensureAttorneyFilterMetadata();
      updateAttorneyCountryLabels();
      updateAttorneyRegionOptions();
      syncExpandedLabelsOnClose();
      setAttorneySelectOpenState(attorneyCountryFilter, false);
      void refreshAttorneyResults();
    });

    attorneyRegionFilter.addEventListener("change", function () {
      if (!attorneyCountryFilter.value && attorneyRegionFilter.value) {
        attorneyCountryFilter.value = inferredCountryForRegionCode(attorneyRegionFilter.value);
        updateAttorneyRegionOptions();
      }
      updateAttorneyCountryLabels();
      updateAttorneyFiltersClearVisibility();
      syncExpandedLabelsOnClose();
      setAttorneySelectOpenState(attorneyRegionFilter, false);
      void refreshAttorneyResults();
    });

    attorneyCountryFilter.addEventListener("focus", syncExpandedLabelsOnOpen);
    attorneyCountryFilter.addEventListener("pointerdown", syncExpandedLabelsOnOpen);
    attorneyCountryFilter.addEventListener("keydown", syncExpandedLabelsOnOpen);
    attorneyCountryFilter.addEventListener("blur", syncExpandedLabelsOnClose);
    attorneyCountryFilter.addEventListener("pointerdown", syncAttorneyChevronOnOpen);
    attorneyCountryFilter.addEventListener("keydown", syncAttorneyChevronOnOpen);
    attorneyCountryFilter.addEventListener("blur", syncAttorneyChevronOnClose);

    attorneyRegionFilter.addEventListener("focus", syncExpandedLabelsOnOpen);
    attorneyRegionFilter.addEventListener("pointerdown", syncExpandedLabelsOnOpen);
    attorneyRegionFilter.addEventListener("keydown", syncExpandedLabelsOnOpen);
    attorneyRegionFilter.addEventListener("blur", syncExpandedLabelsOnClose);
    attorneyRegionFilter.addEventListener("pointerdown", syncAttorneyChevronOnOpen);
    attorneyRegionFilter.addEventListener("keydown", syncAttorneyChevronOnOpen);
    attorneyRegionFilter.addEventListener("blur", syncAttorneyChevronOnClose);

    if (resetLink) {
      resetLink.addEventListener("click", function (event) {
        event.preventDefault();
        if (attorneyFiltersLoading) {
          return;
        }

        attorneyCountryFilter.value = "";
        attorneyRegionFilter.value = "";
        updateAttorneyCountryLabels();
        updateAttorneyRegionOptions();
        syncExpandedLabelsOnClose();
        void refreshAttorneyResults();
      });
    }
  }

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

    updateAttorneyFilterVisibility();
    updatePlaceholder();
    handleSearchInput();
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
  const directoryTabs = document.querySelector(".directory-tabs");
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

  updatePlaceholder();
  void ensureAttorneyFilterMetadata();
  requestDirectoryData().catch((error) => {
    if (error.name === "AbortError") {
      return;
    }

    console.error("Failed to load user data:", error);
  });
});

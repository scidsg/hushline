document.addEventListener("DOMContentLoaded", function () {
  const userSearch = window.HushlineUserSearch;
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const tabs = document.querySelectorAll(".tab[data-tab]");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const searchStatus = document.getElementById("directory-search-status");
  const initialMarkup = new Map();
  let userData = [];
  let hasRenderedSearch = false;

  tabPanels.forEach((panel) => {
    initialMarkup.set(panel.id, panel.innerHTML);
  });

  function setSearchStatus(message) {
    if (searchStatus) {
      searchStatus.textContent = message;
    }
  }

  function activeTabName() {
    return document.querySelector(".tab.active")?.getAttribute("data-tab") || "all";
  }

  function activePanel() {
    return document.querySelector(".tab-content.active") || document.getElementById("all");
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
      searchInput.placeholder = "Search public record firms...";
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
      return "public record firms";
    }

    return "directory entries";
  }

  function loadData() {
    fetch(`${pathPrefix}/directory/users.json`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then((data) => {
        userData = data;
        handleSearchInput();
      })
      .catch((error) => console.error("Failed to load user data:", error));
  }

  function filterUsers(query) {
    const tab = activeTabName();
    const normalizedQuery = query.trim().toLowerCase();

    return userData.filter((user) => {
      if (tab === "verified" && (!user.is_verified || user.is_public_record)) {
        return false;
      }

      if (tab === "public-records" && !user.is_public_record) {
        return false;
      }

      if (normalizedQuery === "") {
        return true;
      }

      const searchText = userSearch.normalizeSearchText([
        user.primary_username,
        user.display_name,
        user.bio,
      ]);
      return userSearch.matchesQuery(searchText, normalizedQuery);
    });
  }

  function highlightMatch(text, query) {
    return userSearch.highlightQuery(text || "", query);
  }

  function buildBadges(user) {
    let badgeContainer = "";

    if (user.is_public_record) {
      badgeContainer +=
        '<span class="badge" role="img" aria-label="Public record listing">🏛️ Public Record</span>';
      if (user.is_automated) {
        badgeContainer +=
          '<span class="badge" role="img" aria-label="Automated listing">🤖 Automated</span>';
      }
      return badgeContainer;
    }

    if (user.is_admin) {
      badgeContainer += '<span class="badge" role="img" aria-label="Administrator account">⚙️ Admin</span>';
    }

    if (user.is_verified) {
      badgeContainer += '<span class="badge" role="img" aria-label="Verified account">⭐️ Verified</span>';
    }

    return badgeContainer;
  }

  function buildPublicRecordCard(user, query) {
    const displayNameHighlighted = highlightMatch(user.display_name, query);
    const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";

    return `
      <article class="user" aria-label="Public record listing, Display name:${user.display_name}, Description: ${user.bio || "No description"}">
        <h3>${displayNameHighlighted}</h3>
        <div class="badgeContainer">${buildBadges(user)}</div>
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${user.profile_url}" aria-label="View read-only listing for ${user.display_name}">View Listing</a>
        </div>
      </article>
    `;
  }

  function buildUserCard(user, query) {
    const displayNameHighlighted = highlightMatch(
      user.display_name || user.primary_username,
      query,
    );
    const usernameHighlighted = highlightMatch(user.primary_username, query);
    const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";

    if (user.is_public_record) {
      return buildPublicRecordCard(user, query);
    }

    const isVerified = user.is_verified ? "Verified" : "";
    const userType = user.is_admin ? `${isVerified} admin user` : `${isVerified} User`;

    return `
      <article class="user" aria-label="${userType}, Display name:${user.display_name || user.primary_username}, Username: ${user.primary_username}, Bio: ${user.bio || "No bio"}">
        <h3>${displayNameHighlighted}</h3>
        <p class="meta">@${usernameHighlighted}</p>
        <div class="badgeContainer">${buildBadges(user)}</div>
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${user.profile_url}" aria-label="${user.display_name || user.primary_username}'s profile">View Profile</a>
        </div>
      </article>
    `;
  }

  function appendSection(panel, label, users, query) {
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
    userListContainer.innerHTML = users.map((user) => buildUserCard(user, query)).join("");
    panel.appendChild(userListContainer);
  }

  function displayUsers(users, query) {
    const panel = activePanel();
    const tab = activeTabName();
    if (!panel) {
      return;
    }

    panel.innerHTML = "";

    if (users.length === 0) {
      panel.innerHTML =
        '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>';
      return;
    }

    const publicRecords = users.filter((user) => user.is_public_record);
    const realUsers = users.filter((user) => !user.is_public_record);
    const withPgp = realUsers.filter((user) => user.has_pgp_key);
    const infoOnly = realUsers.filter((user) => !user.has_pgp_key);

    if (tab === "public-records") {
      appendSection(panel, "", publicRecords, query);
      return;
    }

    appendSection(panel, "", withPgp, query);
    appendSection(panel, "📇 Info-Only Accounts", infoOnly, query);

    if (tab === "all") {
      appendSection(panel, "🏛️ Public Record Firms", publicRecords, query);
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

  window.activateTab = function (selectedTab) {
    const targetPanel = document.getElementById(
      selectedTab.getAttribute("aria-controls"),
    );
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

    updatePlaceholder();
    handleSearchInput();
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", function (e) {
      window.activateTab(e.currentTarget);
    });
    tab.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      event.preventDefault();
      const tabArray = Array.from(tabs);
      const currentIndex = tabArray.indexOf(event.currentTarget);
      const direction = event.key === "ArrowRight" ? 1 : -1;
      const nextIndex =
        (currentIndex + direction + tabArray.length) % tabArray.length;
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

  const directoryTabs = document.querySelector(".directory-tabs");
  const searchBox = document.querySelector(".directory-search");
  if (directoryTabs) {
    let tabsInitialTop = null;
    let stickyStartY = null;
    const updateTabsInitialTop = () => {
      tabsInitialTop = directoryTabs.getBoundingClientRect().top + window.scrollY;
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight;
      stickyStartY = tabsInitialTop - stickyTop;
    };
    updateTabsInitialTop();

    const topLink = directoryTabs.querySelector(".tab-top-link");
    if (topLink) {
      topLink.addEventListener("click", (event) => {
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }

    const updateStickyState = () => {
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight;
      const tabsTop = directoryTabs.getBoundingClientRect().top;
      const isSticky = window.scrollY > stickyTop + 1 && tabsTop <= stickyTop;
      const showTopLink =
        stickyStartY !== null && window.scrollY > stickyStartY + 100;
      directoryTabs.classList.toggle("is-sticky", isSticky);
      directoryTabs.classList.toggle("show-top-link", showTopLink);
      directoryTabs.classList.toggle("top-link-visible", showTopLink);

      if (searchBox) {
        const tabsHeight = directoryTabs.getBoundingClientRect().height;
        const searchStickyTop = stickyTop + tabsHeight;
        searchBox.style.setProperty(
          "--directory-search-top",
          `${searchStickyTop}px`,
        );
        const searchTop = searchBox.getBoundingClientRect().top;
        const isSearchSticky =
          window.scrollY > searchStickyTop + 1 && searchTop <= searchStickyTop;
        searchBox.classList.toggle("is-sticky", isSearchSticky);
      }
    };

    updateStickyState();
    window.addEventListener("scroll", updateStickyState, { passive: true });
    window.addEventListener("hashchange", () => {
      updateTabsInitialTop();
      requestAnimationFrame(updateStickyState);
    });
    window.addEventListener("resize", () => {
      updateTabsInitialTop();
      updateStickyState();
    });
  }

  updatePlaceholder();
  loadData();
});

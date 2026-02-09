document.addEventListener("DOMContentLoaded", function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const tabs = document.querySelectorAll(".tab[data-tab]");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const initialMarkup = new Map();
  let userData = [];
  let hasRenderedSearch = false;

  tabPanels.forEach((panel) => {
    initialMarkup.set(panel.id, panel.innerHTML);
  });

  function updatePlaceholder() {
    const activeTabElement = document.querySelector(".tab.active");
    const activeTab = activeTabElement
      ? activeTabElement.getAttribute("data-tab")
      : "verified";
    searchInput.placeholder = `Search ${
      activeTab === "verified" ? "verified " : ""
    }users...`;
  }

  function loadData() {
    fetch(`${pathPrefix}/directory/users.json`)
      .then((response) => response.json())
      .then((data) => {
        userData = data;
        handleSearchInput();
      })
      .catch((error) => console.error("Failed to load user data:", error));
  }

  function filterUsers(query) {
    const activeTabElement = document.querySelector(".tab.active");
    const tab = activeTabElement
      ? activeTabElement.getAttribute("data-tab")
      : "verified";
    const q = query.trim().toLowerCase();

    return userData.filter((user) => {
      if (tab === "verified" && !user.is_verified) {
        return false;
      }

      if (q === "") {
        return true;
      }

      const searchText = `${user.primary_username} ${user.display_name} ${
        user.bio
      }`.toLowerCase();
      return searchText.includes(q);
    });
  }

  function highlightMatch(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, "gi");
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  function buildUserCard(user, query) {
    const displayNameHighlighted = highlightMatch(
      user.display_name || user.primary_username,
      query,
    );
    const usernameHighlighted = highlightMatch(user.primary_username, query);
    const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";

    let badgeContainer = "";

    if (user.is_admin) {
      badgeContainer += '<span class="badge" role="img" aria-label="Administrator account">⚙️ Admin</span>';
    }

    if (user.is_verified) {
      badgeContainer += '<span class="badge" role="img" aria-label="Verified account">⭐️ Verified</span>';
    }

    const isVerified = user.is_verified ? "Verified" : "";
    const userType = user.is_admin ? `${isVerified} admin user` : `${isVerified} User`;
    return `
      <article class="user" aria-label="${userType}, Display name:${user.display_name || user.primary_username}, Username: ${user.primary_username}, Bio: ${user.bio || "No bio"}">
        <h3>${displayNameHighlighted}</h3>
        <p class="meta">@${usernameHighlighted}</p>
        <div class="badgeContainer">${badgeContainer}</div>
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${pathPrefix}/to/${user.primary_username}" aria-label="${user.display_name || user.primary_username}'s profile">View Profile</a>
        </div>
      </article>
    `;
  }

  function displayUsers(users, query) {
    const activePanel = document.querySelector(".tab-content.active");
    if (!activePanel) {
      return;
    }

    activePanel.innerHTML = "";

    if (users.length === 0) {
      activePanel.innerHTML =
        '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>';
      return;
    }

    const withPgp = users.filter((user) => user.has_pgp_key);
    const infoOnly = users.filter((user) => !user.has_pgp_key);

    if (withPgp.length) {
      const userListContainer = document.createElement("div");
      userListContainer.className = "user-list";
      userListContainer.innerHTML = withPgp
        .map((user) => buildUserCard(user, query))
        .join("");
      activePanel.appendChild(userListContainer);
    }

    if (infoOnly.length) {
      const infoLabel = document.createElement("p");
      infoLabel.className = "label searchLabel";
      infoLabel.textContent = "📇 Info-Only Accounts";
      activePanel.appendChild(infoLabel);

      const infoListContainer = document.createElement("div");
      infoListContainer.className = "user-list";
      infoListContainer.innerHTML = infoOnly
        .map((user) => buildUserCard(user, query))
        .join("");
      activePanel.appendChild(infoListContainer);
    }

  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    const activePanel = document.querySelector(".tab-content.active");
    const hasQuery = query.length > 0;
    if (clearIcon) {
      clearIcon.style.visibility = hasQuery ? "visible" : "hidden";
      clearIcon.hidden = !hasQuery;
      clearIcon.setAttribute("aria-hidden", hasQuery ? "false" : "true");
    }
    if (query.length === 0) {
      if (activePanel && initialMarkup.has(activePanel.id)) {
        activePanel.innerHTML = initialMarkup.get(activePanel.id);
      }
      hasRenderedSearch = false;
      return;
    }
    const filteredUsers = filterUsers(query);
    displayUsers(filteredUsers, query);
    hasRenderedSearch = true;
  }

  searchInput.addEventListener("input", handleSearchInput);
  clearIcon.addEventListener("click", function () {
    searchInput.value = "";
    clearIcon.style.visibility = "hidden";
    clearIcon.hidden = true;
    clearIcon.setAttribute("aria-hidden", "true");
    handleSearchInput();
  });

  window.activateTab = function (selectedTab) {
    const targetPanel = document.getElementById(
      selectedTab.getAttribute("aria-controls"),
    );

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

  const verifiedTab = document.querySelector('.tab[data-tab="verified"]');
  if (verifiedTab) {
    window.activateTab(verifiedTab);
  } else {
    console.error("Verified tab not found");
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
        const header = document.querySelector("header");
        const banner = document.querySelector(".banner");
        const headerHeight = header ? header.getBoundingClientRect().height : 0;
        const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
        const stickyTop = headerHeight + bannerHeight;
        const tabsTop = directoryTabs.getBoundingClientRect().top;
        const isSticky = tabsTop <= stickyTop;
        if (!isSticky || tabsInitialTop === null) {
          updateTabsInitialTop();
        }
        const targetY = Math.max(0, tabsInitialTop - stickyTop);
        window.scrollTo({ top: targetY, behavior: "smooth" });
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

  loadData();
});

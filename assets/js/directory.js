document.addEventListener("DOMContentLoaded", function () {
  const userSearch = window.HushlineUserSearch;
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const searchStatus = document.getElementById("directory-search-status");
  const searchBox = document.querySelector(".directory-search");
  const stickyShell = document.querySelector(".directory-sticky-shell");
  const resultsContainer = document.getElementById("all");
  const initialMarkup = resultsContainer ? resultsContainer.innerHTML : "";
  let userData = [];
  let hasRenderedSearch = false;

  function setSearchStatus(message) {
    if (searchStatus) {
      searchStatus.textContent = message;
    }
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
    return userData.filter((user) => {
      const searchText = userSearch.normalizeSearchText([
        user.primary_username,
        user.display_name,
        user.bio,
      ]);
      return userSearch.matchesQuery(searchText, query);
    });
  }

  function highlightMatch(text, query) {
    return userSearch.highlightQuery(text, query);
  }

  function buildUserCard(user, query) {
    const safeDisplayName = userSearch.escapeHtml(
      user.display_name || user.primary_username || "",
    );
    const safeUsername = userSearch.escapeHtml(user.primary_username || "");
    const safeBio = userSearch.escapeHtml(user.bio || "No bio");
    const safeUserType = userSearch.escapeHtml(
      user.is_admin
        ? `${user.is_verified ? "Verified" : ""} admin user`
        : `${user.is_verified ? "Verified" : ""} User`,
    );
    const safeProfileUrl = userSearch.escapeHtml(`${pathPrefix}/to/${user.primary_username}`);
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

    return `
      <article class="user" aria-label="${safeUserType}, Display name:${safeDisplayName}, Username: ${safeUsername}, Bio: ${safeBio}">
        <h3>${displayNameHighlighted}</h3>
        <p class="meta">@${usernameHighlighted}</p>
        <div class="badgeContainer">${badgeContainer}</div>
        ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
        <div class="user-actions">
          <a href="${safeProfileUrl}" aria-label="${safeDisplayName}'s profile">View Profile</a>
        </div>
      </article>
    `;
  }

  function displayUsers(users, query) {
    if (!resultsContainer) {
      return;
    }

    resultsContainer.innerHTML = "";

    if (users.length === 0) {
      resultsContainer.innerHTML =
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
      resultsContainer.appendChild(userListContainer);
    }

    if (infoOnly.length) {
      const infoLabel = document.createElement("p");
      infoLabel.className = "label searchLabel";
      infoLabel.textContent = "📇 Info-Only Accounts";
      resultsContainer.appendChild(infoLabel);

      const infoListContainer = document.createElement("div");
      infoListContainer.className = "user-list";
      infoListContainer.innerHTML = infoOnly
        .map((user) => buildUserCard(user, query))
        .join("");
      resultsContainer.appendChild(infoListContainer);
    }

  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    const hasQuery = query.length > 0;
    if (clearIcon) {
      clearIcon.style.visibility = hasQuery ? "visible" : "hidden";
      clearIcon.hidden = !hasQuery;
      clearIcon.setAttribute("aria-hidden", hasQuery ? "false" : "true");
    }
    if (query.length === 0) {
      if (resultsContainer) {
        resultsContainer.innerHTML = initialMarkup;
      }
      if (hasRenderedSearch) {
        setSearchStatus("Showing all users.");
      }
      hasRenderedSearch = false;
      return;
    }
    const filteredUsers = filterUsers(query);
    displayUsers(filteredUsers, query);
    setSearchStatus(
      filteredUsers.length === 1
        ? `Found 1 user matching "${query}".`
        : `Found ${filteredUsers.length} users matching "${query}".`,
    );
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

  if (stickyShell || searchBox) {
    const updateStickyState = () => {
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight;
      const stickyAnchor = stickyShell || searchBox;

      if (stickyAnchor) {
        stickyAnchor.style.setProperty("--directory-sticky-top", `${stickyTop}px`);
        const stickyAnchorTop = stickyAnchor.getBoundingClientRect().top;
        const isSticky = window.scrollY > stickyTop + 1 && stickyAnchorTop <= stickyTop;
        stickyShell?.classList.toggle("is-sticky", isSticky);
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

  loadData();
});

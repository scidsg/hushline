document.addEventListener("DOMContentLoaded", function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const tabs = document.querySelectorAll(".tab");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const initialMarkup = new Map();
  let userData = [];
  let isSessionUser = false;
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

  async function checkIfSessionUser() {
    try {
      const response = await fetch(
        `${pathPrefix}/directory/get-session-user.json`,
      );
      const { logged_in } = await response.json();
      isSessionUser = logged_in;
    } catch (error) {
      console.error("Failed to check session user:", error);
    }
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

  function reportUser(username, bio) {
    const messageContent = `Reported user: ${username}\n\nBio: ${bio}\n\nReason:`;
    const encodedMessage = encodeURIComponent(messageContent);
    const submissionUrl = `${pathPrefix}/to/admin?prefill=${encodedMessage}`;
    window.location.href = submissionUrl;
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
      badgeContainer += '<p class="badge">⚙️ Admin</p>';
    }

    if (user.is_verified) {
      badgeContainer += '<p class="badge">⭐️ Verified</p>';
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
          <a href="${pathPrefix}/to/${user.primary_username}">View Profile</a>
          ${isSessionUser ? `<a href="#" class="report-link" data-username="${user.primary_username}" data-display-name="${user.display_name || user.primary_username}" data-bio="${user.bio ?? "No bio"}">Report Account</a>` : ``}
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
      infoLabel.className = "meta";
      infoLabel.textContent = "Information Only";
      activePanel.appendChild(infoLabel);

      const infoListContainer = document.createElement("div");
      infoListContainer.className = "user-list";
      infoListContainer.innerHTML = infoOnly
        .map((user) => buildUserCard(user, query))
        .join("");
      activePanel.appendChild(infoListContainer);
    }

    createReportEventListeners(".tab-content.active .user-list");
  }

  function createReportEventListeners(selector) {
    const reportLinks = document.querySelectorAll(selector + " .report-link");
    reportLinks.forEach((link) => {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        const username = this.getAttribute("data-username");
        const bio = this.getAttribute("data-bio");
        reportUser(username, bio);
      });
    });
  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    const activePanel = document.querySelector(".tab-content.active");
    if (query.length === 0) {
      if (
        hasRenderedSearch &&
        activePanel &&
        initialMarkup.has(activePanel.id)
      ) {
        activePanel.innerHTML = initialMarkup.get(activePanel.id);
        createReportEventListeners(`#${activePanel.id}`);
        hasRenderedSearch = false;
      }
      clearIcon.style.visibility = "hidden";
      return;
    }
    const filteredUsers = filterUsers(query);
    displayUsers(filteredUsers, query);
    clearIcon.style.visibility = query.length ? "visible" : "hidden";
    hasRenderedSearch = true;
  }

  searchInput.addEventListener("input", handleSearchInput);
  clearIcon.addEventListener("click", function () {
    searchInput.value = "";
    clearIcon.style.visibility = "hidden";
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
  });

  const verifiedTab = document.querySelector('.tab[data-tab="verified"]');
  if (verifiedTab) {
    window.activateTab(verifiedTab);
  } else {
    console.error("Verified tab not found");
  }

  checkIfSessionUser().then(() => {
    loadData();
  });
});

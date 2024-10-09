document.addEventListener("DOMContentLoaded", function () {
  // Get the path prefix
  // If window.location.pathname is /tips/directory, then prefix is /tips
  // If it's /directory, then prefix is /
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const tabs = document.querySelectorAll(".tab");
  const tabPanels = document.querySelectorAll(".tab-content");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  let userData = []; // Will hold the user data loaded from JSON
  let isSessionUser = false;

  function updatePlaceholder() {
    const activeTab = document
      .querySelector(".tab.active")
      .getAttribute("data-tab");
    searchInput.placeholder = `Search ${activeTab === "verified" ? "verified " : ""}users...`;
  }

  function loadData() {
    fetch(`${pathPrefix}/directory/users.json`)
      .then((response) => response.json())
      .then((data) => {
        userData = data;
        handleSearchInput(); // Initial display after data is loaded
      })
      .catch((error) => console.error("Failed to load user data:", error));
  }

  async function checkIfSessionUser() {
    const response = await fetch(
      `${pathPrefix}/directory/get-session-user.json`,
    );
    const { logged_in } = await response.json();
    isSessionUser = logged_in;
  }

  function filterUsers(query) {
    const tab = document.querySelector(".tab.active").getAttribute("data-tab");
    return userData.filter((user) => {
      const searchText =
        `${user.primary_username} ${user.display_name} ${user.bio}`.toLowerCase();
      const matchesTab =
        tab === "all" || (tab === "verified" && user.is_verified);
      return searchText.includes(query.toLowerCase()) && matchesTab;
    });
  }

  function highlightMatch(text, query) {
    if (!query) return text; // If no query, return the text unmodified
    const regex = new RegExp(`(${query})`, "gi"); // Case-insensitive matching
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  function reportUser(username, bio) {
    // Construct the message content with explicit line breaks
    const messageContent = `Reported user: ${username}\n\nBio: ${bio}\n\nReason:`;

    // Encode the message content to ensure line breaks and other special characters are correctly handled
    const encodedMessage = encodeURIComponent(messageContent);

    // Redirect to the message submission form for the admin with the pre-filled content
    const submissionUrl = `${pathPrefix}/to/admin?prefill=${encodedMessage}`;
    window.location.href = submissionUrl;
  }

  function displayUsers(users, query) {
    const userListContainer = document.querySelector(
      ".tab-content.active .user-list",
    );
    const activeTab = document
      .querySelector(".tab.active")
      .getAttribute("data-tab");
    userListContainer.innerHTML = "";

    if (users.length > 0) {
      users.forEach((user) => {
        const displayNameHighlighted = highlightMatch(
          user.display_name || user.primary_username,
          query,
        );
        const usernameHighlighted = highlightMatch(
          user.primary_username,
          query,
        );
        const bioHighlighted = user.bio ? highlightMatch(user.bio, query) : "";

        let badgeContainer = "";

        if (user.is_admin) {
          badgeContainer += '<p class="badge">⚙️ Admin</p>';
        }

        // Include the "Verified" badge if the "all" tab is active
        if (activeTab === "all" && user.is_verified) {
          badgeContainer += '<p class="badge">⭐️ Verified</p>';
        }

        // Include the "Verified" badge if the "verified" tab is active
        if (activeTab === "verified" && user.is_verified) {
          badgeContainer += '<p class="badge">⭐️ Verified</p>';
        }

        const userDiv = document.createElement("article");
        userDiv.className = "user";
        const isVerified = user.is_verified ? "Verified" : "";
        const userType = user.is_admin
          ? `${isVerified} admin user`
          : `${isVerified} User`;
        userDiv.setAttribute(
          "aria-label",
          `${userType}, Display name:${user.display_name || user.primary_username}, Username: ${user.primary_username}, Bio: ${user.bio || "No bio"}`,
        );
        userDiv.innerHTML = `
                    <h3>${displayNameHighlighted}</h3>
                    <p class="meta">@${usernameHighlighted}</p>
                    <div class="badgeContainer">${badgeContainer}</div>
                    ${bioHighlighted ? `<p class="bio">${bioHighlighted}</p>` : ""}
                    <div class="user-actions">
                        <a href="${pathPrefix}/to/${user.primary_username}">View Profile</a>
                        ${isSessionUser ? `<a href="#" class="report-link" data-username="${user.primary_username}" data-display-name="${user.display_name || user.primary_username}" data-bio="${user.bio ?? "No bio"}">Report Account</a>` : ``}
                    </div>
                `;
        userListContainer.appendChild(userDiv);
      });

      createReportEventListeners(".tab-content.active .user-list");
    } else {
      userListContainer.innerHTML =
        '<p class="empty-message"><span class="emoji-message">🫥</span><br>No users found.</p>';
    }
  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    const filteredUsers = filterUsers(query);
    displayUsers(filteredUsers, query);
    clearIcon.style.visibility = query.length ? "visible" : "hidden";
  }

  searchInput.addEventListener("input", handleSearchInput);
  clearIcon.addEventListener("click", function () {
    searchInput.value = "";
    clearIcon.style.visibility = "hidden";
    handleSearchInput();
  });

  tabs.forEach((tab) => {
    tab.addEventListener("click", function (e) {
      window.activateTab(e, tabs, tabPanels);
      handleSearchInput(); // Filter again when tab changes
      updatePlaceholder();
    });
    tab.addEventListener("keydown", function (e) {
      window.handleKeydown(e);
    });
  });

  function createReportEventListeners(selector) {
    document
      .querySelector(selector)
      .addEventListener("click", function (event) {
        if (event.target.classList.contains("report-link")) {
          event.preventDefault();
          const link = event.target;
          const username = link.getAttribute("data-username");
          const bio = link.getAttribute("data-bio");
          reportUser(username, bio);
        }
      });
  }
  checkIfSessionUser();
  updatePlaceholder(); // Initialize placeholder text
  loadData();
});

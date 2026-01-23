document.addEventListener("DOMContentLoaded", function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const resultsContainer = document.getElementById("all");
  const initialMarkup = resultsContainer ? resultsContainer.innerHTML : "";
  let userData = [];
  let isSessionUser = false;
  let hasRenderedSearch = false;

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

  async function checkIfSessionUser() {
    try {
      const response = await fetch(
        `${pathPrefix}/directory/get-session-user.json`,
      );
      if (!response.ok) {
        throw new Error("Network response was not ok");
      }
      const { logged_in } = await response.json();
      isSessionUser = logged_in;
    } catch (error) {
      console.error("Failed to check session user:", error);
    }
  }

  function filterUsers(query) {
    return userData.filter((user) => {
      const searchText =
        `${user.primary_username} ${user.display_name} ${user.bio}`.toLowerCase();
      return searchText.includes(query.toLowerCase());
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

    createReportEventListeners("#all");
  }

  function handleSearchInput() {
    const query = searchInput.value.trim();
    if (query.length === 0) {
      if (hasRenderedSearch && resultsContainer) {
        resultsContainer.innerHTML = initialMarkup;
        createReportEventListeners("#all");
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

  checkIfSessionUser().then(() => {
    loadData();
  });
});

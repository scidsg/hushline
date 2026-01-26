document.addEventListener("DOMContentLoaded", function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  const resultsContainer = document.getElementById("all");
  const initialMarkup = resultsContainer ? resultsContainer.innerHTML : "";
  let userData = [];
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
          <a href="${pathPrefix}/to/${user.primary_username}" aria-label="${user.display_name || user.primary_username}'s profile">View Profile</a>
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

  loadData();
});

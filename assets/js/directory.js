document.addEventListener("DOMContentLoaded", function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const searchInput = document.getElementById("searchInput");
  const clearIcon = document.getElementById("clearIcon");
  let userData = [];
  let isSessionUser = false;

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

  function displayUsers(users, query) {
    const userListContainer = document.querySelector(".user-list");
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
        if (user.is_verified) {
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
                        <a href="${pathPrefix}/to/${encodeURIComponent(user.primary_username)}">View Profile</a>
                        ${isSessionUser ? `<a href="#" class="report-link" data-username="${user.primary_username}" data-display-name="${user.display_name || user.primary_username}" data-bio="${user.bio ?? "No bio"}">Report Account</a>` : ``}
                    </div>
                `;
        userListContainer.appendChild(userDiv);
      });

      createReportEventListeners(".user-list");
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

  function createReportEventListeners(selector) {
    const links = document.querySelectorAll(selector + " .report-link");
    links.forEach((link) => {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        const username = this.getAttribute("data-username");
        const bio = this.getAttribute("data-bio");
        reportUser(username, bio);
      });
    });
  }

  checkIfSessionUser().then(() => {
    loadData();
  });
});

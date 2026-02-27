document.addEventListener("DOMContentLoaded", function () {
  const searchRoot = document.querySelector(".settings-search");
  const usersList = document.getElementById("admin-users-list");
  const emptyMessage = document.getElementById("admin-users-empty-message");
  const searchStatus = document.getElementById("admin-search-status");
  if (!searchRoot || !usersList) {
    return;
  }

  const searchInput = searchRoot.querySelector('input[type="text"]');
  const clearButton = searchRoot.querySelector("button");
  if (!searchInput || !clearButton) {
    return;
  }

  const userCards = Array.from(usersList.querySelectorAll(".user"));
  const searchIndex = new Map();
  const usernameNodes = new Map();
  const displayNameNodes = new Map();
  const originalUsernames = new Map();
  const originalDisplayNames = new Map();

  for (const card of userCards) {
    const usernameNode = card.querySelector("h5");
    const displayNameNode = card.querySelector(".admin-display-name");
    const username = (usernameNode?.textContent || "").trim();
    const displayName = (displayNameNode?.textContent || "").trim();
    usernameNodes.set(card, usernameNode);
    displayNameNodes.set(card, displayNameNode);
    originalUsernames.set(card, username);
    originalDisplayNames.set(card, displayName);
    searchIndex.set(card, `${username} ${displayName}`.toLowerCase().trim());
  }

  const setClearButtonState = (hasQuery) => {
    clearButton.style.visibility = hasQuery ? "visible" : "hidden";
    clearButton.hidden = !hasQuery;
    clearButton.setAttribute("aria-hidden", hasQuery ? "false" : "true");
  };

  const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const escapeHtml = (value) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const renderHighlight = (node, originalText, query) => {
    if (!node) {
      return;
    }
    if (!query) {
      node.textContent = originalText;
      return;
    }
    const regex = new RegExp(`(${escapeRegExp(query)})`, "gi");
    const safeText = escapeHtml(originalText);
    node.innerHTML = safeText.replace(
      regex,
      '<mark class="search-highlight">$1</mark>',
    );
  };

  const updateSearchStatus = (visibleCount, query) => {
    if (!searchStatus) {
      return;
    }

    if (!query) {
      searchStatus.textContent = "Showing all usernames.";
      return;
    }

    searchStatus.textContent =
      visibleCount === 0
        ? `No usernames found for "${query}".`
        : `Found ${visibleCount} username${visibleCount === 1 ? "" : "s"} for "${query}".`;
  };

  const applyFilter = () => {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    for (const card of userCards) {
      const haystack = searchIndex.get(card) || "";
      const isVisible = query === "" || haystack.includes(query);
      card.style.display = isVisible ? "" : "none";
      card.setAttribute("aria-hidden", isVisible ? "false" : "true");
      renderHighlight(
        usernameNodes.get(card),
        originalUsernames.get(card) || "",
        query,
      );
      renderHighlight(
        displayNameNodes.get(card),
        originalDisplayNames.get(card) || "",
        query,
      );
      if (isVisible) {
        visibleCount += 1;
      }
    }

    if (emptyMessage) {
      emptyMessage.hidden = visibleCount > 0;
    }
    setClearButtonState(query.length > 0);
    updateSearchStatus(visibleCount, query);
  };

  searchInput.addEventListener("input", applyFilter);
  clearButton.addEventListener("click", function () {
    searchInput.value = "";
    applyFilter();
    searchInput.focus();
  });

  applyFilter();
});

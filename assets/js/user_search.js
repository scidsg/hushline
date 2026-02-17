(function () {
  function normalizeSearchText(parts) {
    return parts
      .filter((part) => typeof part === "string" && part.trim().length > 0)
      .join(" ")
      .toLowerCase();
  }

  function matchesQuery(searchText, query) {
    const normalizedQuery = (query || "").trim().toLowerCase();
    if (!normalizedQuery) {
      return true;
    }
    return searchText.includes(normalizedQuery);
  }

  function escapeRegExp(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function highlightQuery(text, query) {
    if (!query) {
      return text;
    }
    const escapedQuery = escapeRegExp(query);
    const regex = new RegExp(`(${escapedQuery})`, "gi");
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  window.HushlineUserSearch = {
    highlightQuery,
    matchesQuery,
    normalizeSearchText,
  };
})();

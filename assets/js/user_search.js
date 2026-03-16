(function () {
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      switch (char) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        case "'":
          return "&#39;";
        default:
          return char;
      }
    });
  }

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
    const sourceText = String(text ?? "");
    if (!query) {
      return escapeHtml(sourceText);
    }
    const escapedQuery = escapeRegExp(query);
    const regex = new RegExp(`(${escapedQuery})`, "gi");
    let highlighted = "";
    let previousIndex = 0;

    for (const match of sourceText.matchAll(regex)) {
      const matchIndex = match.index ?? 0;
      highlighted += escapeHtml(sourceText.slice(previousIndex, matchIndex));
      highlighted += `<mark class="search-highlight">${escapeHtml(match[0])}</mark>`;
      previousIndex = matchIndex + match[0].length;
    }

    highlighted += escapeHtml(sourceText.slice(previousIndex));
    return highlighted;
  }

  window.HushlineUserSearch = {
    escapeHtml,
    highlightQuery,
    matchesQuery,
    normalizeSearchText,
  };
})();

document.addEventListener("DOMContentLoaded", function () {
  // Listen for clicks anywhere in the document
  document.addEventListener("click", function (event) {
    // Check if the clicked element or its parents have the 'btn-danger' class
    let targetElement = event.target;
    while (targetElement != null) {
      if (
        targetElement.classList &&
        targetElement.classList.contains("btn-danger")
      ) {
        // Confirm before deletion
        const confirmed = confirm(
          "Are you sure you want to delete this message? This cannot be undone.",
        );
        if (!confirmed) {
          event.preventDefault();
        }
        return; // Exit the loop and function after handling the click
      }
      targetElement = targetElement.parentElement;
    }
  });
});

document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab");
  const tabList = document.querySelectorAll(".tab-list .tab");
  const mainElement = document.querySelector("main");
  const inboxTabsNav = document.querySelector(".inbox-tabs-nav");
  const inboxPollIntervalMs = 5000;

  if (tabList.length >= 5) {
    mainElement.classList.add("inbox-main");
  }

  if (inboxTabsNav) {
    const updateStickyOffset = () => {
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const desktopOffset = window.matchMedia("(min-width: 641px)").matches
        ? Number.parseFloat(
            window.getComputedStyle(document.documentElement).fontSize,
          ) || 16
        : 0;
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight + desktopOffset;

      inboxTabsNav.style.setProperty(
        "--inbox-tabs-top",
        `${stickyTop}px`,
      );
    };

    updateStickyOffset();
    window.addEventListener("resize", updateStickyOffset);
    window.addEventListener("hashchange", () => {
      requestAnimationFrame(updateStickyOffset);
    });

    const replaceIfChanged = (selector, nextDocument) => {
      const currentElement = document.querySelector(selector);
      const nextElement = nextDocument.querySelector(selector);
      if (
        !currentElement ||
        !nextElement ||
        currentElement.innerHTML === nextElement.innerHTML
      ) {
        return false;
      }

      currentElement.replaceWith(nextElement);
      return true;
    };

    const refreshInbox = async () => {
      if (document.hidden) {
        return;
      }

      try {
        const response = await fetch(window.location.href, {
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) {
          return;
        }

        const nextHtml = await response.text();
        const nextDocument = new DOMParser().parseFromString(
          nextHtml,
          "text/html",
        );
        const changed = [
          replaceIfChanged(".message-list", nextDocument),
          replaceIfChanged(".inbox-tabs", nextDocument),
        ].some(Boolean);
        if (changed) {
          requestAnimationFrame(updateStickyOffset);
        }
      } catch (_error) {
        // Keep polling quiet; the next interval will retry.
      }
    };

    window.setInterval(refreshInbox, inboxPollIntervalMs);
  }
});

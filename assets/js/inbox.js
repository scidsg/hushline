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

  if (tabList.length >= 5) {
    mainElement.classList.add("inbox-main");
  }

  if (inboxTabsNav) {
    const updateStickyOffset = () => {
      const header = document.querySelector("header");
      const banner = document.querySelector(".banner");
      const rootFontSize = Number.parseFloat(
        window.getComputedStyle(document.documentElement).fontSize,
      ) || 16;
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const bannerHeight = banner ? banner.getBoundingClientRect().height : 0;
      const stickyTop = headerHeight + bannerHeight + rootFontSize;

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
  }
});

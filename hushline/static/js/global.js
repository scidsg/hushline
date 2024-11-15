function navController() {
  const mobileNavButton = document.querySelector(".mobileNav");
  const navMenu = document.querySelector("header nav ul");

  mobileNavButton.addEventListener("click", function () {
    navMenu.classList.toggle("show");
  });

  function setupDropdown() {
    const dropdownToggle = document.querySelector(".dropdown .dropbtn");
    if (!dropdownToggle) return;

    const dropdownContent = document.querySelector(".dropdown-content");
    const dropdownIcon = document.querySelector(".dropdown-icon");

    if (dropdownContent && dropdownIcon) {
      dropdownToggle.addEventListener("click", function (event) {
        event.preventDefault();
        dropdownContent.classList.toggle("show");
        dropdownContent.style.animation = dropdownContent.classList.contains(
          "show",
        )
          ? "fadeInSlideDown 0.3s ease forwards"
          : "fadeOutSlideUp 0.3s ease forwards";
        dropdownIcon.classList.toggle("rotate-icon");
        const expanded = this.getAttribute("aria-expanded") === "true" || false;
        this.setAttribute("aria-expanded", !expanded);
        dropdownContent.hidden = expanded;
      });

      window.addEventListener("click", function (event) {
        if (
          !dropdownToggle.contains(event.target) &&
          dropdownContent.classList.contains("show")
        ) {
          dropdownContent.classList.remove("show");
          dropdownIcon.classList.remove("rotate-icon");
          dropdownToggle.setAttribute("aria-expanded", "false");
          dropdownContent.hidden = true;
        }
      });
    }
  }

  setupDropdown();
}

document.addEventListener("DOMContentLoaded", function () {
  navController();

  window.handleKeydown = function (event) {
    const { key } = event;
    const currentTab = event.target;
    let newTab;

    switch (key) {
      case "ArrowLeft":
        newTab =
          currentTab.parentElement.previousElementSibling?.querySelector(
            ".tab",
          );
        break;
      case "ArrowRight":
        newTab =
          currentTab.parentElement.nextElementSibling?.querySelector(".tab");
        break;
      case "Home":
        newTab = tabs[0];
        break;
      case "End":
        newTab = tabs[tabs.length - 1];
        break;
      default:
        return;
    }

    if (newTab) {
      newTab.focus();
      newTab.click();
      event.preventDefault();
    }
  };

  window.activateTab = function (event, tabs, tabPanels) {
    const selectedTab = event.target;
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
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      panel.hidden = true;
      panel.style.display = "none";
    });

    selectedTab.setAttribute("aria-selected", "true");
    selectedTab.classList.add("active");
    targetPanel.hidden = false;
    targetPanel.style.display = "block";
    targetPanel.classList.add("active");
  };

  function getHexColorFromCSSVariable(variableName) {
    // Create a temporary element
    const tempElement = document.createElement("div");
    tempElement.style.display = "none";
    document.body.appendChild(tempElement);

    // Apply the CSS variable as a color
    tempElement.style.color = `var(${variableName})`;

    // Get the computed color (resolved to hex)
    const color = getComputedStyle(tempElement).color;

    // Remove the temporary element
    document.body.removeChild(tempElement);

    return color;
  }

  function updateThemeColor() {
    const themeColorMetaTag = document.querySelector(
      'meta[name="theme-color"]',
    );

    // Retrieve hex values of CSS variables
    const lightModeColor = getHexColorFromCSSVariable("--theme-color-light");
    const darkModeColor = getHexColorFromCSSVariable("--theme-color-dark");

    // Detect if user prefers dark mode
    const isDarkMode = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;

    // Set the meta tag with the appropriate color
    themeColorMetaTag.setAttribute(
      "content",
      isDarkMode ? darkModeColor : lightModeColor,
    );
  }

  // Initialize and add event listener for theme changes
  updateThemeColor();
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", updateThemeColor);
});

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

  function getCSSVariableValue(variableName) {
    // Fetch the CSS variable value directly from the :root element
    return getComputedStyle(document.documentElement)
      .getPropertyValue(variableName)
      .trim();
  }

  function updateThemeColor() {
    let themeColorMetaTag = document.querySelector('meta[name="theme-color"]');

    // Ensure the meta tag exists; create it if missing
    if (!themeColorMetaTag) {
      themeColorMetaTag = document.createElement("meta");
      themeColorMetaTag.setAttribute("name", "theme-color");
      document.head.appendChild(themeColorMetaTag);
    }

    // Fetch the CSS variables for light and dark mode
    const lightModeColor = getCSSVariableValue("--theme-color-light");
    const darkModeColor = getCSSVariableValue("--theme-color-dark");

    // Detect user preference for dark mode
    const isDarkMode = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;

    // Set the appropriate color in the meta tag
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

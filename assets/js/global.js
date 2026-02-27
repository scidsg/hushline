function navController() {
  const prefersReducedMotion = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setupDropdown() {
    const dropdownToggle = document.querySelector(".dropdown .dropbtn");
    if (!dropdownToggle) return;

    const dropdownContent = document.querySelector(".dropdown-content");
    const dropdownIcon = document.querySelector(".dropdown-icon");

    if (dropdownContent && dropdownIcon) {
      const closeDropdown = () => {
        dropdownContent.classList.remove("show");
        dropdownContent.style.animation = prefersReducedMotion()
          ? "none"
          : "fadeOutSlideUp 0.3s ease forwards";
        dropdownIcon.classList.remove("rotate-icon");
        dropdownToggle.setAttribute("aria-expanded", "false");
        dropdownContent.hidden = true;
      };

      dropdownToggle.addEventListener("click", function (event) {
        event.preventDefault();
        const expanded = this.getAttribute("aria-expanded") === "true" || false;
        if (expanded) {
          closeDropdown();
          return;
        }

        dropdownContent.classList.add("show");
        dropdownContent.style.animation = prefersReducedMotion()
          ? "none"
          : "fadeInSlideDown 0.3s ease forwards";
        dropdownIcon.classList.add("rotate-icon");
        this.setAttribute("aria-expanded", "true");
        dropdownContent.hidden = false;
      });

      document.addEventListener("click", function (event) {
        if (
          !dropdownToggle.contains(event.target) &&
          !dropdownContent.contains(event.target) &&
          dropdownContent.classList.contains("show")
        ) {
          closeDropdown();
        }
      });

      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && dropdownContent.classList.contains("show")) {
          closeDropdown();
          dropdownToggle.focus();
        }
      });
    }
  }

  function setupMobileNav() {
    const mobileNavToggle = document.querySelector(".mobileNav");
    const navList = document.querySelector("header nav ul");
    const nav = document.querySelector("header nav");

    if (mobileNavToggle && navList && nav) {
      const closeMobileNav = () => {
        navList.classList.remove("show");
        mobileNavToggle.setAttribute("aria-expanded", "false");
      };

      mobileNavToggle.addEventListener("click", function (event) {
        event.preventDefault();
        const expanded = this.getAttribute("aria-expanded") === "true" || false;
        if (expanded) {
          closeMobileNav();
          return;
        }

        navList.classList.add("show");
        this.setAttribute("aria-expanded", "true");
      });

      document.addEventListener("click", function (event) {
        if (
          mobileNavToggle.getAttribute("aria-expanded") === "true" &&
          !nav.contains(event.target)
        ) {
          closeMobileNav();
        }
      });

      document.addEventListener("keydown", function (event) {
        if (
          event.key === "Escape" &&
          mobileNavToggle.getAttribute("aria-expanded") === "true"
        ) {
          closeMobileNav();
          mobileNavToggle.focus();
        }
      });
    }
  }

  setupDropdown();
  setupMobileNav();
}

document.addEventListener("DOMContentLoaded", function () {
  navController();

  function setupFlashDismiss() {
    document.addEventListener("click", function (event) {
      const dismissButton = event.target.closest(".flash-dismiss");
      if (!dismissButton) return;
      const flashContainer = dismissButton.closest(".flash-messages");
      if (!flashContainer) return;
      flashContainer.classList.add("is-dismissing");
      const cleanup = () => {
        flashContainer.remove();
      };
      flashContainer.addEventListener("animationend", cleanup, { once: true });
      setTimeout(cleanup, 700);
    });
  }

  setupFlashDismiss();

  function setupSubmitSpinners() {
    const forms = document.querySelectorAll("form[data-submit-spinner='true']");
    forms.forEach((form) => {
      const method = (form.getAttribute("method") || "GET").toUpperCase();
      if (method !== "POST" && method !== "GET") {
        return;
      }

      const submitButton = form.querySelector(
        "button[type='submit'], input[type='submit']",
      );
      if (
        !submitButton ||
        submitButton.tagName !== "BUTTON" ||
        submitButton.dataset.submitSpinnerInit === "true"
      ) {
        return;
      }

      const labelText = submitButton.textContent.trim();
      submitButton.textContent = "";

      const label = document.createElement("span");
      label.className = "submit-button-label";
      label.textContent = labelText;

      const spinner = document.createElement("span");
      spinner.className = "submit-button-spinner";
      spinner.setAttribute("aria-hidden", "true");

      submitButton.appendChild(label);
      submitButton.appendChild(spinner);
      submitButton.dataset.submitSpinnerInit = "true";

      const setLoading = () => {
        submitButton.classList.add("is-loading");
        submitButton.setAttribute("aria-busy", "true");
      };

      const clearLoading = () => {
        submitButton.classList.remove("is-loading");
        submitButton.removeAttribute("aria-busy");
      };

      form.addEventListener("submit", function () {
        setLoading();
      });

      const observer = new MutationObserver(function () {
        if (submitButton.classList.contains("is-loading") && !submitButton.disabled) {
          clearLoading();
        }
      });
      observer.observe(submitButton, {
        attributes: true,
        attributeFilter: ["disabled"],
      });

      window.addEventListener("pageshow", function () {
        clearLoading();
      });
    });
  }

  setupSubmitSpinners();

  function setupStatusForm() {
    const statusForm = document.getElementById("statusForm");
    if (!statusForm) return;

    const statusField = statusForm.querySelector('[name="status"]');
    if (statusField) {
      statusField.addEventListener("change", function () {
        const formData = new FormData(statusForm);

        fetch(statusForm.action, {
          method: "POST",
          body: formData,
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error("Failed to update status");
            }
            return response.text(); // Expecting the server to return HTML
          })
          .then((html) => {
            // Parse and update flash messages without reload
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, "text/html");
            const flashMessages = doc.querySelector(".flash-messages");
            if (flashMessages) {
              const existingFlash = document.querySelector(".flash-messages");
              if (existingFlash) {
                existingFlash.replaceWith(flashMessages);
              } else {
                document.body.insertBefore(
                  flashMessages,
                  document.body.firstChild,
                );
              }
            }
          })
          .catch((error) => {
            console.error("Error updating status:", error);
          });
      });
    }
  }

  setupStatusForm();

  // Handle user guidance
  const guidanceDiv = document.querySelector("#guidance-modal.modal");
  if (guidanceDiv) {
    let activePage = 0;
    let previousFocus = null;

    const hasFinishedGuidance = localStorage.getItem("hasFinishedGuidance");
    if (!hasFinishedGuidance) {
      previousFocus = document.activeElement;
      guidanceDiv.classList.add("show");
      guidanceDiv.setAttribute("aria-hidden", "false");

      // Count the child divs of guidanceDiv, these are the pages
      const guidancePages = guidanceDiv.querySelectorAll(":scope > div");
      const pagesCount = guidancePages.length;

      function getFocusableElements() {
        const activePage = guidancePages[activePageIndex()];
        if (!activePage) {
          return [];
        }
        return Array.from(
          activePage.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
          ),
        ).filter(
          (el) => !el.hasAttribute("disabled") && el.offsetParent !== null,
        );
      }

      function activePageIndex() {
        return Math.max(0, Math.min(activePage, pagesCount - 1));
      }

      function trapFocus(event) {
        if (event.key !== "Tab" || !guidanceDiv.classList.contains("show")) {
          return;
        }
        const focusable = getFocusableElements();
        if (!focusable.length) {
          event.preventDefault();
          guidanceDiv.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }

      function showActivePage() {
        for (let i = 0; i < pagesCount; i++) {
          if (i == activePage) {
            guidancePages[i].classList.add("show");
            guidancePages[i].setAttribute("aria-hidden", "false");
            guidanceDiv
              .querySelectorAll(".page-bullet-" + i)
              .forEach((bullet) => {
                bullet.classList.add("active");
              });
          } else {
            guidancePages[i].classList.remove("show");
            guidancePages[i].setAttribute("aria-hidden", "true");
            guidanceDiv
              .querySelectorAll(".page-bullet-" + i)
              .forEach((bullet) => {
                bullet.classList.remove("active");
              });
          }
        }
        guidanceDiv.setAttribute(
          "aria-labelledby",
          "guidance-heading-" + activePage,
        );
      }

      function leaveClicked() {
        const exitButtonLink = document.querySelector(
          "#guidance-exit-button-link",
        );
        if (exitButtonLink) {
          const exitButtonLinkValue = exitButtonLink.value;
          try {
            const sanitizedUrl = new URL(exitButtonLinkValue);
            document.location.href = sanitizedUrl.href;
          } catch (e) {
            console.error(
              "Invalid URL in exit button link:",
              exitButtonLinkValue,
            );
          }
        } else {
          console.error("No exit button link found");
        }
      }

      function continueClicked() {
        if (activePage < pagesCount - 1) {
          activePage++;
          showActivePage();
        } else {
          console.error("No more pages to show");
        }
      }

      function backClicked() {
        if (activePage > 0) {
          activePage--;
          showActivePage();
        } else {
          console.error("No more pages to show");
        }
      }

      function doneClicked() {
        guidanceDiv.classList.remove("show");
        guidanceDiv.setAttribute("aria-hidden", "true");
        localStorage.setItem("hasFinishedGuidance", "true");
        if (previousFocus && typeof previousFocus.focus === "function") {
          previousFocus.focus();
        }
      }

      // If there are no pages, or if there's one page and it's blank, hide the modal
      if (
        pagesCount == 0 ||
        (pagesCount == 1 &&
          guidancePages[0].querySelector(".heading-text").textContent.trim() ==
            "" &&
          guidancePages[0].querySelector(".prompt-text").textContent.trim() ==
            "")
      ) {
        guidanceDiv.classList.remove("show");
        guidanceDiv.setAttribute("aria-hidden", "true");
      }

      // If there's just 1 page, hide the bullets
      if (pagesCount == 1) {
        guidanceDiv.querySelector(".page-bullets").classList.add("hide");
      }

      // Choose which buttons should be shown, and also attach event listeners
      for (let i = 0; i < pagesCount; i++) {
        const page = guidancePages[i];

        const leaveButton = page.querySelector(".leave");
        if (leaveButton) {
          leaveButton.addEventListener("click", leaveClicked);
          leaveButton.classList.add("show");
        }

        // Show done on the last page
        if (i == pagesCount - 1) {
          const doneButton = page.querySelector(".done");
          if (doneButton) {
            doneButton.addEventListener("click", doneClicked);
            doneButton.classList.add("show");
          }
        }
        // Show continue on any non-last pages
        else {
          const continueButton = page.querySelector(".continue");
          if (continueButton) {
            continueButton.addEventListener("click", continueClicked);
            continueButton.classList.add("show");
          }
        }

        // She back on any non-first pages
        if (i > 0) {
          const backButton = page.querySelector(".back");
          if (backButton) {
            backButton.addEventListener("click", backClicked);
            backButton.classList.add("show");
          }
        }

        // Attach listener for the bullets
        guidanceDiv.querySelectorAll(".page-bullet-" + i).forEach((bullet) => {
          bullet.addEventListener("click", function () {
            activePage = i;
            showActivePage();
          });
        });
      }

      // Show the first page
      showActivePage();
      guidanceDiv.focus();
      guidanceDiv.addEventListener("keydown", trapFocus);
    }
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("guidance-modal");
  let firstModalContent = null;
  if (modal) {
    firstModalContent = modal.querySelector(".modal-content");
  }

  if (modal && firstModalContent) {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      firstModalContent.classList.add("animate");
    }

    firstModalContent.addEventListener("animationend", () => {
      firstModalContent.classList.remove("animate");
      firstModalContent.style.opacity = "1";
    });
  }
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/js/service-worker.js')
      .then(() => console.log('Service Worker registered'))
      .catch((err) => console.error('Service Worker registration failed:', err));
  }
});

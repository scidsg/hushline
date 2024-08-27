document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab");
  const tabPanels = document.querySelectorAll(".tab-content");
  const bioCountEl = document.querySelector(".bio-count");

  // Restore the active tab on page load
  function restoreActiveTab() {
    const activeTab = localStorage.getItem("activeTab");
    if (activeTab) {
      // Deactivate all tabs and hide all tab contents
      tabs.forEach((tab) => {
        tab.classList.remove("active");
        tab.setAttribute("aria-selected", "false");
      });
      tabPanels.forEach((panel) => {
        panel.classList.remove("active");
        panel.setAttribute("hidden", "true");
      });

      // Activate the stored tab and show the corresponding content
      const activeTabElement = document.getElementById(`${activeTab}-tab`);
      const activePanelElement = document.getElementById(activeTab);

      if (activeTabElement && activePanelElement) {
        activeTabElement.classList.add("active");
        activeTabElement.setAttribute("aria-selected", "true");
        activePanelElement.classList.add("active");
        activePanelElement.removeAttribute("hidden");
      }
    }
  }

  // Save the active tab to localStorage
  function setActiveTab(tabName) {
    localStorage.setItem("activeTab", tabName);
  }

  // Initialize the page with the restored tab
  restoreActiveTab();

  // Deletion account confirmation logic
  document
    .getElementById("deleteAccountButton")
    ?.addEventListener("click", function (event) {
      const confirmed = confirm(
        "Are you sure you want to delete your account? This cannot be undone.",
      );
      if (!confirmed) {
        event.preventDefault();
      }
    });

  document
    .querySelector("input[name='show_in_directory']")
    .addEventListener("change", function (e) {
      // time out to let animation finish
      setTimeout(() => {
        document
          .querySelector("button[name='update_directory_visibility']")
          .click();
      }, 200);
    });

  document.getElementById("bio").addEventListener("keyup", function (e) {
    bioCountEl.textContent = e.target.value.length;
  });

  tabs.forEach((tab) => {
    tab.addEventListener("click", function (e) {
      window.activateTab(e, tabs, tabPanels);
      setActiveTab(this.getAttribute("data-tab"));
    });
    tab.addEventListener("keydown", function (e) {
      window.handleKeydown(e);
    });
  });

  var forwarding_enabled = document.querySelector(
    "input[id='forwarding_enabled']",
  ).checked;
  var forwarding_enabled_fieldset = document.querySelector(
    "fieldset[id='forwarding_enabled_fields']",
  );
  forwarding_enabled_fieldset.hidden = !forwarding_enabled;

  document
    .querySelector("input[id='forwarding_enabled']")
    .addEventListener("change", function (e) {
      // time out to let animation finish
      setTimeout(() => {
        var fieldset = document.querySelector(
          "fieldset[id='forwarding_enabled_fields']",
        );
        fieldset.hidden = !e.target.checked;

        // If the toggle is turned off, submit the form automatically
        if (!e.target.checked) {
          e.target.form.submit();
        }
      }, 200);
    });

  var custom_smtp_settings = document.querySelector(
    "input[id='custom_smtp_settings']",
  ).checked;
  var custom_smtp_settings_fields = document.querySelector(
    "fieldset[id='custom_smtp_settings_fields']",
  );
  custom_smtp_settings_fields.hidden = !custom_smtp_settings;

  document
    .querySelector("input[id='custom_smtp_settings']")
    .addEventListener("change", function (e) {
      // time out to let animation finish
      setTimeout(() => {
        var fieldset = document.querySelector(
          "fieldset[id='custom_smtp_settings_fields']",
        );
        fieldset.hidden = !e.target.checked;
      }, 200);
    });
});

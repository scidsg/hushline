document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab");
  const bioCountEl = document.querySelector(".bio-count");
  const mainElement = document.querySelector("main");
  const tabList = document.querySelectorAll(".tab-list .tab");

  // Apply "settings-main" class if there are 5 or more tabs
  if (tabList.length >= 5) {
    mainElement.classList.add("settings-main");
  }

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
    ?.addEventListener("change", function (e) {
      // time out to let animation finish
      setTimeout(() => {
        document
          .querySelector("button[name='update_directory_visibility']")
          .click();
      }, 200);
    });

  document.getElementById("bio")?.addEventListener("keyup", function (e) {
    bioCountEl.textContent = e.target.value.length;
  });

  const colorPicker = document.getElementById("brand-primary-color");
  if (colorPicker) {
    for (const eventName of ["input", "change"]) {
      colorPicker.addEventListener(eventName, function (event) {
        const brandColor = `oklch(from ${event.target.value} l c h)`;
        document.documentElement.style.setProperty("--color-brand", brandColor);
      });
    }
  }

  const appNameBox = document.getElementById("brand-app-name");
  if (appNameBox) {
    appNameBox.addEventListener("input", function (event) {
      document.querySelector("h1").innerText = event.target.value;
    });
  }

  var forwarding_enabled = document.querySelector(
    "input[id='forwarding_enabled']",
  )?.checked;
  var forwarding_enabled_fieldset = document.querySelector(
    "fieldset[id='forwarding_enabled_fields']",
  );
  if (forwarding_enabled_fieldset) {
    forwarding_enabled_fieldset.hidden = !forwarding_enabled;
  }

  document
    .querySelector("input[id='forwarding_enabled']")
    ?.addEventListener("change", function (e) {
      setTimeout(() => {
        document.querySelector(
          "fieldset[id='forwarding_enabled_fields']",
        ).hidden = !e.target.checked;
        if (!e.target.checked) e.target.form.submit();
      }, 200);
    });

  var custom_smtp_settings = document.querySelector(
    "input[id='custom_smtp_settings']",
  )?.checked;
  var custom_smtp_settings_fields = document.querySelector(
    "fieldset[id='custom_smtp_settings_fields']",
  );
  if (custom_smtp_settings_fields) {
    custom_smtp_settings_fields.hidden = !custom_smtp_settings;
  }

  document
    .querySelector("input[id='custom_smtp_settings']")
    ?.addEventListener("change", function (e) {
      setTimeout(() => {
        document.querySelector(
          "fieldset[id='custom_smtp_settings_fields']",
        ).hidden = !e.target.checked;
      }, 200);
    });

  // Reset guidance
  const resetGuidanceButton = document.querySelector(".reset-guidance-button");
  if (resetGuidanceButton) {
    resetGuidanceButton.addEventListener("click", function (event) {
      localStorage.removeItem("hasFinishedGuidance");
      location.reload();
    });
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const userGuidanceToggle = document.querySelector(
    "input[name='show_user_guidance']"
  );

  if (userGuidanceToggle) {
    userGuidanceToggle.addEventListener("change", function () {
      setTimeout(() => {
        const form = userGuidanceToggle.closest("form");

        if (form) {
          // Debugging: Log form submission for troubleshooting
          const formData = new FormData(form);
          console.debug("Submitting form data:", Object.fromEntries(formData));

          // Submit the form
          form.submit();
        } else {
          console.error("Form not found for user guidance toggle.");
        }
      }, 200); // Allow for animations or visual feedback
    });
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const tabs = document.querySelectorAll(".tab");
  const tabList = document.querySelectorAll(".tab-list .tab");
  const mainElement = document.querySelector("main");
  const settingsTabsNav = document.querySelector(".settings-tabs");

  if (tabList.length >= 5) {
    mainElement.classList.add("settings-main");
  }

  if (settingsTabsNav) {
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

      settingsTabsNav.style.setProperty(
        "--settings-tabs-top",
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

document.addEventListener("DOMContentLoaded", function () {
  const bioCountEl = document.querySelector(".bio-count");
  document.getElementById("bio")?.addEventListener("keyup", function (e) {
    bioCountEl.textContent = e.target.value.length;
  });
});

document.addEventListener("DOMContentLoaded", function () {
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
});

document.addEventListener("DOMContentLoaded", function () {
  document
    .getElementById("deleteAliasButton")
    ?.addEventListener("click", function (event) {
      const confirmed = confirm(
        "Are you sure you want to delete this alias? This cannot be undone.",
      );
      if (!confirmed) {
        event.preventDefault();
      }
    });
});

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".delete-user-button").forEach(function (button) {
    button.addEventListener("click", function (event) {
      const username = event.currentTarget.dataset.username || "this user";
      const confirmed = confirm(
        `Are you sure you want to delete ${username}? All aliases will be deleted too. This cannot be undone.`,
      );
      if (!confirmed) {
        event.preventDefault();
      }
    });
  });
});

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".delete-username-button").forEach(function (button) {
    button.addEventListener("click", function (event) {
      const username = event.currentTarget.dataset.username || "this alias";
      const confirmed = confirm(
        `Are you sure you want to delete alias ${username}? This cannot be undone.`,
      );
      if (!confirmed) {
        event.preventDefault();
      }
    });
  });
});

document.addEventListener("DOMContentLoaded", function () {
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
});

document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelector("input[name='show_user_guidance']")
    ?.addEventListener("change", function (e) {
      // time out to let animation finish
      setTimeout(() => {
        document.querySelector("button[name='update_user_guidance']").click();
      }, 200);
    });
});

document.addEventListener("DOMContentLoaded", function () {
  const colorPicker = document.getElementById("brand-primary-color");
  if (colorPicker) {
    for (const eventName of ["input", "change"]) {
      colorPicker.addEventListener(eventName, function (event) {
        const brandColor = CSS.supports(
          "color",
          `oklch(from ${event.target.value} l c h)`,
        )
          ? `oklch(from ${event.target.value} l c h)`
          : event.target.value;
        document.documentElement.style.setProperty("--color-brand", brandColor);
      });
    }
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const appNameBox = document.getElementById("brand-app-name");
  if (appNameBox) {
    appNameBox.addEventListener("input", function (event) {
      document.querySelector("h1").innerText = event.target.value;
    });
  }
});

document.addEventListener("DOMContentLoaded", function () {
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
});

document.addEventListener("DOMContentLoaded", function () {
  const resetGuidanceButton = document.querySelector(".reset-guidance-button");
  if (resetGuidanceButton) {
    resetGuidanceButton.addEventListener("click", function (event) {
      localStorage.removeItem("hasFinishedGuidance");
      location.reload();
    });
  }
});

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form.auto-submit").forEach((elem) => {
    const input = elem.querySelector(':scope input[type="checkbox"]');
    const toggle = elem.querySelector(":scope .toggle");
    const submitButton = elem.querySelector(
      ':scope button[type="submit"], :scope input[type="submit"]',
    );
    if (!input || !toggle || !submitButton) return;

    input.addEventListener("change", function () {
      submitButton.click();
    });

    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      input.checked = !input.checked;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
});

function bytesToBase64(bytes) {
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

async function provisionChatKey(form) {
  const passwordInput = form.querySelector("#chat-key-password");
  const status = document.getElementById("chat-key-provision-status");
  const submitButton = form.querySelector('button[type="submit"]');
  if (!passwordInput || !status || !submitButton) return;

  if (!window.crypto?.subtle) {
    status.textContent = "This browser cannot create a chat key.";
    return;
  }

  submitButton.disabled = true;
  status.textContent = "Creating chat key...";
  let privateJwk = null;

  try {
    const textEncoder = new TextEncoder();
    const salt = window.crypto.getRandomValues(new Uint8Array(16));
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const keyPair = await window.crypto.subtle.generateKey(
      {
        name: "ECDH",
        namedCurve: "P-256",
      },
      true,
      ["deriveKey"],
    );
    const publicJwk = await window.crypto.subtle.exportKey(
      "jwk",
      keyPair.publicKey,
    );
    privateJwk = await window.crypto.subtle.exportKey("jwk", keyPair.privateKey);
    const passwordKey = await window.crypto.subtle.importKey(
      "raw",
      textEncoder.encode(passwordInput.value),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    const wrappingKey = await window.crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt,
        iterations: 310000,
        hash: "SHA-256",
      },
      passwordKey,
      {
        name: "AES-GCM",
        length: 256,
      },
      false,
      ["encrypt"],
    );
    const encryptedBytes = new Uint8Array(
      await window.crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv,
        },
        wrappingKey,
        textEncoder.encode(JSON.stringify(privateJwk)),
      ),
    );
    const payload = {
      public_key: JSON.stringify(publicJwk),
      encrypted_private_key: JSON.stringify({
        algorithm: "AES-GCM",
        iv: bytesToBase64(iv),
        ciphertext: bytesToBase64(encryptedBytes),
      }),
      kdf_algorithm: "PBKDF2-SHA-256",
      kdf_params: {
        iterations: 310000,
        hash: "SHA-256",
      },
      kdf_salt: bytesToBase64(salt),
      wrapping_algorithm: "AES-GCM",
    };
    const headers = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    if (form.dataset.csrfToken) {
      headers["X-CSRFToken"] = form.dataset.csrfToken;
    }

    const response = await fetch(form.dataset.chatKeyUrl, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("Chat key creation failed");
    }
    status.textContent = "Chat key created.";
    form.hidden = true;
  } catch (error) {
    status.textContent = "Chat key creation failed.";
  } finally {
    privateJwk = null;
    passwordInput.value = "";
    submitButton.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const chatKeyForm = document.getElementById("chat-key-provision-form");
  chatKeyForm?.addEventListener("submit", function (event) {
    event.preventDefault();
    provisionChatKey(event.currentTarget);
  });
});

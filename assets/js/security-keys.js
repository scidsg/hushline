function decodeBase64Url(value) {
  const padded = value
    .replace(/-/g, "+")
    .replace(/_/g, "/")
    .padEnd(Math.ceil(value.length / 4) * 4, "=");
  const decoded = window.atob(padded);
  return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
}

function encodeBase64Url(value) {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return window
    .btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function registrationOptions(payload) {
  payload.challenge = decodeBase64Url(payload.challenge);
  payload.user.id = decodeBase64Url(payload.user.id);
  payload.excludeCredentials = (payload.excludeCredentials || []).map(
    (credential) => ({
      ...credential,
      id: decodeBase64Url(credential.id),
    }),
  );
  return payload;
}

function registrationResponse(credential) {
  return {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      attestationObject: encodeBase64Url(
        credential.response.attestationObject,
      ),
      clientDataJSON: encodeBase64Url(credential.response.clientDataJSON),
      transports:
        typeof credential.response.getTransports === "function"
          ? credential.response.getTransports()
          : [],
    },
  };
}

async function responseJson(response) {
  try {
    return await response.json();
  } catch (_error) {
    return {};
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("security-key-enrollment-form");
  if (!form) return;

  const button = document.getElementById("security-key-enroll-button");
  const nameInput = document.getElementById("security-key-name");
  const status = document.getElementById("security-key-status");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

  if (
    !window.isSecureContext ||
    typeof window.PublicKeyCredential === "undefined" ||
    typeof navigator.credentials?.create !== "function"
  ) {
    button.disabled = true;
    status.textContent =
      "This browser cannot enroll security keys. Use a supported browser in a secure connection.";
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    button.disabled = true;
    status.textContent = "Waiting for your security key…";
    const name = nameInput.value.trim();
    const headers = {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken || "",
    };

    try {
      const optionsResponse = await fetch(form.dataset.optionsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: JSON.stringify({ name }),
      });
      const options = await responseJson(optionsResponse);
      if (!optionsResponse.ok) {
        throw new Error(options.error || "Enrollment could not be started.");
      }

      const credential = await navigator.credentials.create({
        publicKey: registrationOptions(options),
      });
      if (!credential) throw new Error("No security key response was received.");

      status.textContent = "Verifying your security key…";
      const verifyResponse = await fetch(form.dataset.verifyUrl, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: JSON.stringify({
          name,
          credential: registrationResponse(credential),
        }),
      });
      const result = await responseJson(verifyResponse);
      if (!verifyResponse.ok) {
        throw new Error(
          result.error || "The security key could not be verified.",
        );
      }

      status.textContent =
        result.message ||
        "Security key added. Keep a backup key in a separate safe place.";
      form.hidden = true;
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        status.textContent =
          "Enrollment was canceled or timed out. No security key was added.";
      } else if (error?.name === "SecurityError") {
        status.textContent =
          "This site cannot use security keys in the current browser context. No key was added.";
      } else if (error instanceof TypeError) {
        status.textContent = [
          "A network or browser error interrupted enrollment.",
          "Reload this page to check whether the key was added before trying again.",
        ].join(" ");
      } else {
        status.textContent =
          error?.message || "Enrollment failed. No security key was added.";
      }
      button.disabled = false;
    }
  });
});

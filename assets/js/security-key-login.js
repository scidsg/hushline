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

function authenticationOptions(payload) {
  payload.challenge = decodeBase64Url(payload.challenge);
  payload.allowCredentials = (payload.allowCredentials || []).map(
    (credential) => ({
      ...credential,
      id: decodeBase64Url(credential.id),
    }),
  );
  return payload;
}

function authenticationResponse(credential) {
  return {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      authenticatorData: encodeBase64Url(credential.response.authenticatorData),
      clientDataJSON: encodeBase64Url(credential.response.clientDataJSON),
      signature: encodeBase64Url(credential.response.signature),
      userHandle: credential.response.userHandle
        ? encodeBase64Url(credential.response.userHandle)
        : null,
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

function initializeSecurityKeyLogin() {
  const container = document.getElementById("security-key-login");
  if (!container) return;

  const button = document.getElementById("security-key-login-button");
  const status = document.getElementById("security-key-login-status");
  if (!button || !status || button.dataset.securityKeyLoginBound === "true")
    return;
  button.dataset.securityKeyLoginBound = "true";
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
  const isSettingsConfirmation = container.dataset.context === "settings";
  const failureSuffix = isSettingsConfirmation
    ? "Your settings were not changed."
    : "You are not logged in.";

  if (
    !window.isSecureContext ||
    typeof window.PublicKeyCredential === "undefined" ||
    typeof navigator.credentials?.get !== "function"
  ) {
    button.disabled = true;
    status.textContent = [
      "This browser cannot use security keys.",
      isSettingsConfirmation
        ? "Use an enrolled authenticator app or a supported browser in a secure connection."
        : "Use a configured alternative or a supported browser in a secure connection.",
    ].join(" ");
    return;
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Waiting for your security key…";
    const headers = {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken || "",
    };

    try {
      const optionsResponse = await fetch(container.dataset.optionsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: "{}",
      });
      const options = await responseJson(optionsResponse);
      if (!optionsResponse.ok) {
        throw new Error(
          options.error || "Security key verification could not be started.",
        );
      }

      const credential = await navigator.credentials.get({
        publicKey: authenticationOptions(options),
      });
      if (!credential)
        throw new Error("No security key response was received.");

      status.textContent = "Verifying your security key…";
      const verifyResponse = await fetch(container.dataset.verifyUrl, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: JSON.stringify({
          credential: authenticationResponse(credential),
        }),
      });
      const result = await responseJson(verifyResponse);
      if (!verifyResponse.ok) {
        throw new Error(
          result.error || "The security key could not be verified.",
        );
      }
      if (
        typeof result.redirect !== "string" ||
        !result.redirect.startsWith("/") ||
        result.redirect.startsWith("//")
      ) {
        throw new Error(
          "Login completed, but the redirect was invalid. Reload this page.",
        );
      }
      window.location.assign(result.redirect);
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        status.textContent = `Security key verification was canceled or timed out. ${failureSuffix}`;
      } else if (error?.name === "SecurityError") {
        status.textContent = [
          "This site cannot use security keys in the current browser context.",
          failureSuffix,
        ].join(" ");
      } else if (error instanceof TypeError) {
        status.textContent = `A network or browser error interrupted verification. ${failureSuffix}`;
      } else {
        status.textContent =
          error?.message ||
          `Security key verification failed. ${failureSuffix}`;
      }
      button.disabled = false;
    }
  });
}

// Password login can replace the document while retaining the chat-key runtime.
// Imported script tags do not execute during that transition.
document.addEventListener("DOMContentLoaded", initializeSecurityKeyLogin);
document.addEventListener(
  "hushline:document-replaced",
  initializeSecurityKeyLogin,
);

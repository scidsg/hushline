(function () {
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();
  let unlockedChatPrivateKey = null;
  const state = {
    status: "empty",
    keyVersion: null,
    lastError: null,
  };

  function bytesToBase64(bytes) {
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary);
  }

  function base64ToBytes(value) {
    const binary = atob(value);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  function assertCryptoSupport() {
    if (!window.crypto?.subtle) {
      throw new Error("Web Crypto is unavailable.");
    }
  }

  async function deriveWrappingKey(password, salt, kdfParams, usages) {
    const passwordKey = await window.crypto.subtle.importKey(
      "raw",
      textEncoder.encode(password),
      "PBKDF2",
      false,
      ["deriveKey"],
    );
    return window.crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt,
        iterations: Number(kdfParams?.iterations || 310000),
        hash: kdfParams?.hash || "SHA-256",
      },
      passwordKey,
      {
        name: "AES-GCM",
        length: 256,
      },
      false,
      usages,
    );
  }

  async function decryptPrivateJwk(chatKey, password) {
    const encryptedPrivateKey = JSON.parse(chatKey.encrypted_private_key);
    const wrappingKey = await deriveWrappingKey(
      password,
      base64ToBytes(chatKey.kdf_salt),
      chatKey.kdf_params,
      ["decrypt"],
    );
    const privateJwkBytes = await window.crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: base64ToBytes(encryptedPrivateKey.iv),
      },
      wrappingKey,
      base64ToBytes(encryptedPrivateKey.ciphertext),
    );
    return JSON.parse(textDecoder.decode(privateJwkBytes));
  }

  async function importPrivateKey(privateJwk) {
    return window.crypto.subtle.importKey(
      "jwk",
      privateJwk,
      {
        name: "ECDH",
        namedCurve: privateJwk.crv || "P-256",
      },
      false,
      ["deriveBits"],
    );
  }

  async function unlockFromPassword(chatKey, password) {
    if (!chatKey) {
      clearChatKeyMaterial();
      state.status = "no-key";
      return true;
    }

    assertCryptoSupport();
    let privateJwk = null;
    try {
      privateJwk = await decryptPrivateJwk(chatKey, password);
      unlockedChatPrivateKey = await importPrivateKey(privateJwk);
      state.status = "unlocked";
      state.keyVersion = chatKey.key_version;
      state.lastError = null;
      return true;
    } catch (error) {
      clearChatKeyMaterial();
      state.status = "locked";
      state.keyVersion = chatKey.key_version || null;
      state.lastError = "Chat key unlock failed.";
      return false;
    } finally {
      privateJwk = null;
    }
  }

  async function encryptPrivateJwk(privateJwk, password) {
    const salt = window.crypto.getRandomValues(new Uint8Array(16));
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const wrappingKey = await deriveWrappingKey(password, salt, {
      iterations: 310000,
      hash: "SHA-256",
    }, ["encrypt"]);
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

    return {
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
  }

  async function rewrapForPasswordChange(chatKey, oldPassword, newPassword) {
    assertCryptoSupport();
    let privateJwk = null;
    try {
      privateJwk = await decryptPrivateJwk(chatKey, oldPassword);
      const wrapped = await encryptPrivateJwk(privateJwk, newPassword);
      return {
        public_key: chatKey.public_key,
        recovery_state: "available",
        ...wrapped,
      };
    } finally {
      privateJwk = null;
    }
  }

  async function fetchChatKey(chatKeyUrl) {
    const response = await fetch(chatKeyUrl, {
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error("Chat key lookup failed.");
    }
    const payload = await response.json();
    return payload.chat_key || null;
  }

  function clearChatKeyMaterial() {
    unlockedChatPrivateKey = null;
    state.status = "empty";
    state.keyVersion = null;
    state.lastError = null;
  }

  function replaceDocument(responseText, responseUrl) {
    const parsedDocument = new DOMParser().parseFromString(
      responseText,
      "text/html",
    );
    document.title = parsedDocument.title;
    document.head.replaceWith(document.importNode(parsedDocument.head, true));
    document.body.replaceWith(document.importNode(parsedDocument.body, true));
    window.history.replaceState({}, "", responseUrl);
    bindPage();
  }

  function chatKeyUrlFromCurrentOrigin() {
    return new URL("/settings/chat-key.json", window.location.origin).toString();
  }

  async function handleLoginSubmit(event) {
    const form = event.currentTarget;
    const passwordInput = form.querySelector("input[name='password']");
    if (!passwordInput?.value || !window.fetch || !window.FormData) {
      return;
    }

    event.preventDefault();
    const password = passwordInput.value;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(form),
      });
      const responseUrl = new URL(response.url);
      const responseText = await response.text();
      if (response.redirected && responseUrl.pathname !== "/login") {
        if (responseUrl.pathname !== "/verify-2fa-login") {
          const chatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
          await unlockFromPassword(chatKey, password);
        }
        replaceDocument(responseText, response.url);
        return;
      }
      replaceDocument(responseText, response.url);
    } catch (error) {
      HTMLFormElement.prototype.submit.call(form);
    }
  }

  async function handlePasswordChangeSubmit(event) {
    const form = event.currentTarget;
    const chatKeyUrl = form.dataset.chatKeyUrl;
    const rewrappedInput = form.querySelector("#rewrapped_chat_key");
    const oldPasswordInput = form.querySelector("#old_password");
    const newPasswordInput = form.querySelector("#new_password");
    const submitButton = form.querySelector("[name='change_password']");
    const status = document.getElementById("chat-key-rewrap-status");
    if (
      !chatKeyUrl ||
      rewrappedInput?.value ||
      !oldPasswordInput?.value ||
      !newPasswordInput?.value
    ) {
      return;
    }

    event.preventDefault();
    if (status) {
      status.textContent = "Unlocking chat key...";
    }

    try {
      const chatKey = await fetchChatKey(chatKeyUrl);
      if (chatKey) {
        const rewrappedPayload = await rewrapForPasswordChange(
          chatKey,
          oldPasswordInput.value,
          newPasswordInput.value,
        );
        rewrappedInput.value = JSON.stringify(rewrappedPayload);
        if (status) {
          status.textContent = "Chat key rewrapped.";
        }
      }
      if (submitButton?.click) {
        submitButton.click();
      } else {
        HTMLFormElement.prototype.submit.call(form);
      }
    } catch (error) {
      if (status) {
        status.textContent = "Chat key unlock failed. Password was not changed.";
      }
    }
  }

  function bindLogoutCleanup() {
    document.querySelectorAll("a[href$='/logout']").forEach((link) => {
      link.addEventListener("click", clearChatKeyMaterial);
    });
  }

  function bindPage() {
    if (document.body?.dataset.authenticated !== "true") {
      clearChatKeyMaterial();
    }

    document
      .querySelector("form[action$='/login']")
      ?.addEventListener("submit", handleLoginSubmit);
    document
      .getElementById("change-password-form")
      ?.addEventListener("submit", handlePasswordChangeSubmit);
    document
      .querySelector("form[action*='password-reset']")
      ?.addEventListener("submit", clearChatKeyMaterial);
    bindLogoutCleanup();
  }

  window.HushLineChatKeys = {
    clear: clearChatKeyMaterial,
    fetchChatKey,
    get state() {
      return { ...state };
    },
    rewrapForPasswordChange,
    unlockFromPassword,
  };

  document.addEventListener("DOMContentLoaded", function () {
    bindPage();
  });
})();

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

  async function importPublicKey(publicKeyValue) {
    const publicJwk = typeof publicKeyValue === "string"
      ? JSON.parse(publicKeyValue)
      : publicKeyValue;
    return window.crypto.subtle.importKey(
      "jwk",
      publicJwk,
      {
        name: "ECDH",
        namedCurve: publicJwk.crv || "P-256",
      },
      false,
      [],
    );
  }

  async function deriveChatMessageKey(publicKey, privateKey, usages) {
    return window.crypto.subtle.deriveKey(
      {
        name: "ECDH",
        public: publicKey,
      },
      privateKey,
      {
        name: "AES-GCM",
        length: 256,
      },
      false,
      usages,
    );
  }

  async function encryptForPublicKey(plaintext, publicKeyValue) {
    assertCryptoSupport();
    const recipientPublicKey = await importPublicKey(publicKeyValue);
    const ephemeralKeyPair = await window.crypto.subtle.generateKey(
      {
        name: "ECDH",
        namedCurve: "P-256",
      },
      true,
      ["deriveKey"],
    );
    const messageKey = await deriveChatMessageKey(
      recipientPublicKey,
      ephemeralKeyPair.privateKey,
      ["encrypt"],
    );
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = new Uint8Array(
      await window.crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv,
        },
        messageKey,
        textEncoder.encode(plaintext),
      ),
    );
    const ephemeralPublicJwk = await window.crypto.subtle.exportKey(
      "jwk",
      ephemeralKeyPair.publicKey,
    );

    return JSON.stringify({
      algorithm: "ECDH-P256-AES-GCM",
      ephemeral_public_key: JSON.stringify(ephemeralPublicJwk),
      iv: bytesToBase64(iv),
      ciphertext: bytesToBase64(ciphertext),
    });
  }

  async function decryptChatCiphertext(encryptedPayload) {
    if (!unlockedChatPrivateKey) {
      throw new Error("Chat key is locked.");
    }
    assertCryptoSupport();
    const envelope = JSON.parse(encryptedPayload);
    if (envelope.algorithm !== "ECDH-P256-AES-GCM") {
      throw new Error("Unsupported chat ciphertext.");
    }
    const ephemeralPublicKey = await importPublicKey(envelope.ephemeral_public_key);
    const messageKey = await deriveChatMessageKey(
      ephemeralPublicKey,
      unlockedChatPrivateKey,
      ["decrypt"],
    );
    const plaintextBytes = await window.crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: base64ToBytes(envelope.iv),
      },
      messageKey,
      base64ToBytes(envelope.ciphertext),
    );
    return textDecoder.decode(plaintextBytes);
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

  function jsonFromScript(id, fallback) {
    const script = document.getElementById(id);
    if (!script?.textContent) {
      return fallback;
    }

    try {
      return JSON.parse(script.textContent);
    } catch (error) {
      return fallback;
    }
  }

  function setConversationStatus(message) {
    const status = document.getElementById("conversation-chat-status");
    if (status) {
      status.textContent = message;
    }
  }

  async function decryptConversationMessages() {
    const copies = jsonFromScript("conversationMessageCopies", []);
    for (const copy of copies) {
      if (!copy.encrypted_payload) {
        continue;
      }

      const messageElement = document.querySelector(
        `[data-conversation-message-id="${copy.message_id}"] .conversation-message-body`,
      );
      if (!messageElement) {
        continue;
      }

      try {
        messageElement.textContent = await decryptChatCiphertext(copy.encrypted_payload);
      } catch (error) {
        messageElement.textContent = "This message cannot be decrypted in this browser.";
      }
    }
  }

  function setConversationComposeEnabled(enabled) {
    const form = document.getElementById("conversation-compose-form");
    const body = document.getElementById("conversation-compose-body");
    const submit = document.getElementById("conversation-compose-submit");
    if (!form) {
      return;
    }

    if (body) {
      body.disabled = !enabled;
    }
    if (submit) {
      submit.disabled = !enabled;
    }
  }

  function conversationCsrfToken() {
    return document
      .getElementById("conversation-compose-form")
      ?.querySelector("input[name='csrf_token']")
      ?.value;
  }

  async function sendConversationPresence() {
    const root = document.getElementById("conversation-chat");
    if (!root?.dataset.presenceUrl) {
      return;
    }

    try {
      await fetch(root.dataset.presenceUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": conversationCsrfToken() || "",
        },
      });
    } catch (error) {
      return;
    }
  }

  function bindConversationPresence(root) {
    if (root.dataset.presenceBound === "true") {
      return;
    }
    root.dataset.presenceBound = "true";

    const configuredInterval = Number.parseInt(root.dataset.presenceIntervalMs, 10);
    const intervalMs = Number.isFinite(configuredInterval)
      ? Math.max(15000, configuredInterval)
      : 60000;
    const sendIfVisible = () => {
      if (document.visibilityState === "visible") {
        void sendConversationPresence();
      }
    };

    sendIfVisible();
    window.setInterval(sendIfVisible, intervalMs);
    document.addEventListener("visibilitychange", sendIfVisible);
    window.addEventListener("focus", sendIfVisible);
  }

  async function unlockConversationFromPassword() {
    const passwordInput = document.getElementById("conversation-chat-password");
    if (!passwordInput?.value) {
      setConversationStatus("Enter your account password to unlock your chat key.");
      return;
    }

    setConversationStatus("Unlocking chat key...");
    try {
      const chatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
      if (!chatKey) {
        setConversationStatus("Create a Hush Line chat key before reading this conversation.");
        return;
      }
      const unlocked = await unlockFromPassword(chatKey, passwordInput.value);
      if (!unlocked) {
        setConversationStatus("Chat key unlock failed.");
        return;
      }
      await decryptConversationMessages();
      const root = document.getElementById("conversation-chat");
      setConversationComposeEnabled(root?.dataset.canCompose === "true");
      setConversationStatus("Chat key unlocked in this browser.");
      passwordInput.value = "";
    } catch (error) {
      setConversationStatus("Chat key unlock failed.");
    }
  }

  async function handleConversationSubmit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const root = document.getElementById("conversation-chat");
    const body = document.getElementById("conversation-compose-body");
    const plaintext = body?.value.trim();
    const participantKeys = jsonFromScript("conversationParticipantPublicKeys", []);
    if (!root?.dataset.messageUrl || !plaintext) {
      return;
    }
    if (state.status !== "unlocked") {
      setConversationStatus("Unlock your chat key before replying.");
      return;
    }

    setConversationStatus("Encrypting reply...");
    try {
      const encryptedCopies = {};
      for (const participantKey of participantKeys) {
        encryptedCopies[String(participantKey.participant_id)] = await encryptForPublicKey(
          plaintext,
          participantKey.public_key,
        );
      }
      const csrfToken = form.querySelector("input[name='csrf_token']")?.value;
      const response = await fetch(root.dataset.messageUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken || "",
        },
        body: JSON.stringify({
          encrypted_copies: encryptedCopies,
        }),
      });
      if (!response.ok) {
        setConversationStatus("Reply could not be saved.");
        return;
      }
      body.value = "";
      window.location.reload();
    } catch (error) {
      setConversationStatus("Reply could not be encrypted.");
    }
  }

  function bindConversation() {
    const root = document.getElementById("conversation-chat");
    if (!root) {
      return;
    }

    bindConversationPresence(root);

    document
      .getElementById("conversation-chat-unlock")
      ?.addEventListener("click", unlockConversationFromPassword);

    const form = document.getElementById("conversation-compose-form");
    if (form && form.dataset.bound !== "true") {
      form.dataset.bound = "true";
      form.addEventListener("submit", handleConversationSubmit);
    }

    if (state.status === "unlocked") {
      decryptConversationMessages();
      setConversationComposeEnabled(root.dataset.canCompose === "true");
      setConversationStatus("Chat key unlocked in this browser.");
    }
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
    bindConversation();
  }

  window.HushLineChatKeys = {
    clear: clearChatKeyMaterial,
    fetchChatKey,
    get state() {
      return { ...state };
    },
    decryptChatCiphertext,
    encryptForPublicKey,
    rewrapForPasswordChange,
    unlockFromPassword,
  };

  document.addEventListener("DOMContentLoaded", function () {
    bindPage();
  });
})();

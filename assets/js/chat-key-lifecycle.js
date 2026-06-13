(function () {
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();
  const sessionStorageKey = "hushline:chat-private-jwk";
  const browserStorageKey = "hushline:chat-private-jwk:browser-session";
  const browserStorageMaxAgeMs = 12 * 60 * 60 * 1000;
  const crossTabChannelName = "hushline:chat-key-session";
  const crossTabRequestTimeoutMs = 750;
  const conversationPollMinIntervalMs = 3000;
  const tabId = window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
  let crossTabChannel = null;
  let crossTabSharingBound = false;
  let unlockedChatPrivateKey = null;
  let pendingLoginPassword = null;
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
    const importJwk = {
      ...privateJwk,
      key_ops: ["deriveKey"],
    };
    return window.crypto.subtle.importKey(
      "jwk",
      importJwk,
      {
        name: "ECDH",
        namedCurve: importJwk.crv || "P-256",
      },
      false,
      ["deriveKey"],
    );
  }

  function rememberUnlockedPrivateJwk(privateJwk, chatKey) {
    const storedValue = JSON.stringify({
      key_version: chatKey.key_version,
      public_key: chatKey.public_key,
      private_jwk: privateJwk,
      expires_at: Date.now() + browserStorageMaxAgeMs,
    });

    try {
      sessionStorage.setItem(sessionStorageKey, storedValue);
    } catch (error) {
      // Continue with browser storage below when tab storage is unavailable.
    }

    try {
      localStorage.setItem(browserStorageKey, storedValue);
    } catch (error) {
      return;
    }
  }

  function forgetUnlockedPrivateJwk() {
    try {
      sessionStorage.removeItem(sessionStorageKey);
    } catch (error) {
      // Keep clearing other storage locations.
    }
    try {
      localStorage.removeItem(browserStorageKey);
    } catch (error) {
      return;
    }
  }

  function privateJwkFromStoredValue(storedValue, chatKey) {
    if (!storedValue) {
      return null;
    }

    try {
      const stored = JSON.parse(storedValue);
      if (
        stored?.key_version !== chatKey.key_version
        || stored.public_key !== chatKey.public_key
        || !stored.private_jwk
        || !stored.expires_at
      ) {
        return null;
      }
      if (Date.now() > Number(stored.expires_at)) {
        forgetUnlockedPrivateJwk();
        return null;
      }
      return stored.private_jwk;
    } catch (error) {
      return null;
    }
  }

  function rememberedPrivateJwkForChatKey(chatKey) {
    try {
      const privateJwk = privateJwkFromStoredValue(
        sessionStorage.getItem(sessionStorageKey),
        chatKey,
      );
      if (privateJwk) {
        return privateJwk;
      }
    } catch (error) {
      // Fall through to browser storage.
    }

    try {
      const privateJwk = privateJwkFromStoredValue(
        localStorage.getItem(browserStorageKey),
        chatKey,
      );
      if (privateJwk) {
        return privateJwk;
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  async function restoreUnlockedChatKeyFromJwk(chatKey, privateJwk) {
    unlockedChatPrivateKey = await importPrivateKey(privateJwk);
    rememberUnlockedPrivateJwk(privateJwk, chatKey);
    state.status = "unlocked";
    state.keyVersion = chatKey.key_version;
    state.lastError = null;
    return true;
  }

  async function restoreUnlockedChatKey(chatKey) {
    if (!chatKey) {
      return false;
    }

    try {
      const privateJwk = rememberedPrivateJwkForChatKey(chatKey);
      if (!privateJwk) {
        forgetUnlockedPrivateJwk();
        return false;
      }

      return restoreUnlockedChatKeyFromJwk(chatKey, privateJwk);
    } catch (error) {
      clearChatKeyMaterial();
      return false;
    }
  }

  function chatKeyBroadcastChannel() {
    if (!("BroadcastChannel" in window)) {
      return null;
    }
    if (!crossTabChannel) {
      crossTabChannel = new BroadcastChannel(crossTabChannelName);
    }
    return crossTabChannel;
  }

  function postChatKeyBroadcast(message) {
    const channel = chatKeyBroadcastChannel();
    if (!channel) {
      return false;
    }
    channel.postMessage({
      v: 1,
      source_tab_id: tabId,
      ...message,
    });
    return true;
  }

  function bindCrossTabChatKeySharing() {
    if (crossTabSharingBound || document.body?.dataset.authenticated !== "true") {
      return;
    }
    const channel = chatKeyBroadcastChannel();
    if (!channel) {
      return;
    }

    crossTabSharingBound = true;
    channel.addEventListener("message", (event) => {
      const message = event.data || {};
      if (
        message.v !== 1
        || message.source_tab_id === tabId
        || message.type !== "request-unlocked-chat-key"
        || !message.request_id
      ) {
        return;
      }

      const privateJwk = rememberedPrivateJwkForChatKey(message.chat_key);
      if (!privateJwk) {
        return;
      }

      postChatKeyBroadcast({
        type: "unlocked-chat-key",
        request_id: message.request_id,
        chat_key: message.chat_key,
        private_jwk: privateJwk,
      });
    });
  }

  async function restoreUnlockedChatKeyFromOtherTab(chatKey) {
    const channel = chatKeyBroadcastChannel();
    if (!channel || !chatKey) {
      return false;
    }

    const requestId = window.crypto?.randomUUID
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;

    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => {
        channel.removeEventListener("message", onMessage);
        resolve(false);
      }, crossTabRequestTimeoutMs);

      async function onMessage(event) {
        const message = event.data || {};
        if (
          message.v !== 1
          || message.source_tab_id === tabId
          || message.type !== "unlocked-chat-key"
          || message.request_id !== requestId
          || message.chat_key?.key_version !== chatKey.key_version
          || message.chat_key?.public_key !== chatKey.public_key
          || !message.private_jwk
        ) {
          return;
        }

        window.clearTimeout(timeout);
        channel.removeEventListener("message", onMessage);
        try {
          await restoreUnlockedChatKeyFromJwk(chatKey, message.private_jwk);
          resolve(true);
        } catch (error) {
          clearChatKeyMaterial();
          resolve(false);
        }
      }

      channel.addEventListener("message", onMessage);
      postChatKeyBroadcast({
        type: "request-unlocked-chat-key",
        request_id: requestId,
        chat_key: {
          key_version: chatKey.key_version,
          public_key: chatKey.public_key,
        },
      });
    });
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
      rememberUnlockedPrivateJwk(privateJwk, chatKey);
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

  async function createChatKeyPayload(password) {
    assertCryptoSupport();
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
    const privateJwk = await window.crypto.subtle.exportKey("jwk", keyPair.privateKey);
    const wrapped = await encryptPrivateJwk(privateJwk, password);

    return {
      privateJwk,
      payload: {
        public_key: JSON.stringify(publicJwk),
        ...wrapped,
      },
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

  function csrfTokenFromDocument(sourceDocument = document) {
    return sourceDocument
      ?.querySelector("input[name='csrf_token'], meta[name='csrf-token']")
      ?.getAttribute("value")
      || sourceDocument
        ?.querySelector("meta[name='csrf-token']")
        ?.getAttribute("content")
      || "";
  }

  async function provisionChatKey(chatKeyUrl, password, sourceDocument = document) {
    const created = await createChatKeyPayload(password);
    const headers = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    const csrfToken = csrfTokenFromDocument(sourceDocument);
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }

    const response = await fetch(chatKeyUrl, {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(created.payload),
    });
    if (!response.ok) {
      throw new Error("Chat key creation failed.");
    }

    const responsePayload = await response.json();
    const chatKey = responsePayload.chat_key;
    if (!chatKey) {
      throw new Error("Created chat key was unavailable.");
    }
    await restoreUnlockedChatKeyFromJwk(chatKey, created.privateJwk);
    return chatKey;
  }

  async function ensureChatKeyUnlockedAfterAuth(password, sourceDocument = document) {
    const chatKeyUrl = chatKeyUrlFromCurrentOrigin();
    const chatKey = await fetchChatKey(chatKeyUrl);
    if (chatKey) {
      return unlockFromPassword(chatKey, password);
    }
    await provisionChatKey(chatKeyUrl, password, sourceDocument);
    return true;
  }

  async function populateLoginChatKeyPayload(form, password) {
    const payloadInput = form.querySelector("#login-chat-key-payload");
    if (!payloadInput || payloadInput.value) {
      return;
    }

    try {
      const created = await createChatKeyPayload(password);
      payloadInput.value = JSON.stringify(created.payload);
    } catch (error) {
      payloadInput.value = "";
    }
  }

  function clearChatKeyMaterial() {
    forgetUnlockedPrivateJwk();
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

  function setConversationUnlockVisible(visible) {
    const panel = document.getElementById("conversation-key-locked");
    if (panel) {
      panel.hidden = !visible;
    }
  }

  function setConversationSecureBadgeVisible(visible) {
    const badge = document.querySelector(".conversation-secure-badge");
    if (badge) {
      badge.hidden = !visible;
    }
  }

  function currentConversationParticipantId() {
    const root = document.getElementById("conversation-chat");
    return root?.dataset.participantId || "";
  }

  function conversationMessageIds(sourceDocument = document) {
    return Array.from(
      sourceDocument.querySelectorAll("[data-conversation-message-id]"),
    ).map((messageElement) => messageElement.dataset.conversationMessageId || "");
  }

  function conversationMessagesSignature(sourceDocument = document) {
    return conversationMessageIds(sourceDocument).join(",");
  }

  function conversationThreadIsNearBottom() {
    const thread = document.querySelector(".conversation-thread");
    if (!thread) {
      return true;
    }
    return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 96;
  }

  function scrollConversationThreadToLatest(behavior = "auto") {
    const thread = document.querySelector(".conversation-thread");
    if (!thread) {
      return;
    }

    window.requestAnimationFrame(() => {
      thread.scrollTo({
        top: thread.scrollHeight,
        behavior,
      });
    });
  }

  async function refreshConversationMessages({ force = false, scroll = false } = {}) {
    const root = document.getElementById("conversation-chat");
    if (!root || state.status !== "unlocked") {
      return false;
    }

    const thread = document.querySelector(".conversation-thread");
    const currentCopies = document.getElementById("conversationMessageCopies");
    if (!thread || !currentCopies) {
      return false;
    }

    const shouldScroll = scroll || conversationThreadIsNearBottom();
    const response = await fetch(window.location.href, {
      credentials: "same-origin",
      headers: {
        Accept: "text/html",
        "X-Hushline-Conversation-Refresh": "true",
      },
    });
    if (!response.ok) {
      return false;
    }

    const nextDocument = new DOMParser().parseFromString(
      await response.text(),
      "text/html",
    );
    const nextThread = nextDocument.querySelector(".conversation-thread");
    const nextCopies = nextDocument.getElementById("conversationMessageCopies");
    if (!nextThread || !nextCopies) {
      return false;
    }

    if (
      !force
      && conversationMessagesSignature(nextDocument) === conversationMessagesSignature()
    ) {
      return false;
    }

    currentCopies.textContent = nextCopies.textContent;
    thread.replaceChildren(...Array.from(nextThread.children).map((child) => {
      return document.importNode(child, true);
    }));
    await decryptConversationMessages();
    if (shouldScroll) {
      scrollConversationThreadToLatest("smooth");
    }
    return true;
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
      const messageContainer = document.querySelector(
        `[data-conversation-message-id="${copy.message_id}"]`,
      );
      if (!messageElement) {
        continue;
      }

      try {
        messageElement.textContent = await decryptChatCiphertext(copy.encrypted_payload);
        if (messageContainer) {
          const isOwnMessage = String(copy.sender_participant_id)
            === currentConversationParticipantId();
          messageContainer.classList.toggle("is-own-message", isOwnMessage);
          messageContainer.classList.toggle("is-other-message", !isOwnMessage);
        }
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

  function resizeConversationComposer() {
    const body = document.getElementById("conversation-compose-body");
    if (!body) {
      return;
    }

    body.style.height = "auto";
    body.style.height = `${body.scrollHeight}px`;
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
      setConversationStatus("Chat key is still unlocking in this browser.");
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
      resizeConversationComposer();
      await refreshConversationMessages({ force: true, scroll: true });
      setConversationStatus("Reply sent.");
    } catch (error) {
      setConversationStatus("Reply could not be encrypted.");
    }
  }

  function handleConversationComposerKeydown(event) {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }

    const form = document.getElementById("conversation-compose-form");
    const body = document.getElementById("conversation-compose-body");
    if (!form || body?.disabled) {
      return;
    }

    event.preventDefault();
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  }

  function conversationCsrfToken() {
    const root = document.getElementById("conversation-chat");
    return root?.dataset.csrfToken
      || document
      .getElementById("conversation-compose-form")
      ?.querySelector("input[name='csrf_token']")
      ?.value
      || csrfTokenFromDocument();
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

  function bindConversationPolling(root) {
    if (root.dataset.pollBound === "true") {
      return;
    }
    root.dataset.pollBound = "true";

    const configuredInterval = Number.parseInt(root.dataset.pollIntervalMs, 10);
    const intervalMs = Number.isFinite(configuredInterval)
      ? Math.max(conversationPollMinIntervalMs, configuredInterval)
      : 5000;
    let isRefreshing = false;
    const refreshIfVisible = async () => {
      if (document.visibilityState !== "visible" || state.status !== "unlocked") {
        return;
      }
      if (isRefreshing) {
        return;
      }
      isRefreshing = true;
      try {
        await refreshConversationMessages();
      } catch (error) {
        return;
      } finally {
        isRefreshing = false;
      }
    };

    window.setInterval(refreshIfVisible, intervalMs);
    document.addEventListener("visibilitychange", refreshIfVisible);
    window.addEventListener("focus", refreshIfVisible);
  }

  async function restoreConversationFromSession() {
    const root = document.getElementById("conversation-chat");
    if (!root) {
      return;
    }

    try {
      const chatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
      if (!chatKey) {
        setConversationUnlockVisible(true);
        setConversationSecureBadgeVisible(false);
        setConversationStatus("No active chat key is available for this account.");
        return;
      }
      if (await restoreUnlockedChatKey(chatKey)) {
        await decryptConversationMessages();
        setConversationComposeEnabled(root.dataset.canCompose === "true");
        setConversationUnlockVisible(false);
        setConversationSecureBadgeVisible(true);
        setConversationStatus("Chat key unlocked for this session.");
        scrollConversationThreadToLatest();
        return;
      }
      setConversationStatus("Checking for an unlocked chat session...");
      if (await restoreUnlockedChatKeyFromOtherTab(chatKey)) {
        await decryptConversationMessages();
        setConversationComposeEnabled(root.dataset.canCompose === "true");
        setConversationUnlockVisible(false);
        setConversationSecureBadgeVisible(true);
        setConversationStatus("Chat key unlocked for this session.");
        scrollConversationThreadToLatest();
        return;
      }
      setConversationUnlockVisible(true);
      setConversationSecureBadgeVisible(false);
      setConversationStatus("Chat key could not be restored in this browser.");
    } catch (error) {
      setConversationUnlockVisible(true);
      setConversationSecureBadgeVisible(false);
      setConversationStatus("Chat could not be unlocked in this browser session.");
    }
  }

  function bindConversation() {
    const root = document.getElementById("conversation-chat");
    if (!root) {
      return;
    }

    bindConversationPresence(root);
    bindConversationPolling(root);

    const form = document.getElementById("conversation-compose-form");
    if (form && form.dataset.bound !== "true") {
      form.dataset.bound = "true";
      form.addEventListener("submit", handleConversationSubmit);
      document
        .getElementById("conversation-compose-body")
        ?.addEventListener("input", resizeConversationComposer);
      document
        .getElementById("conversation-compose-body")
        ?.addEventListener("keydown", handleConversationComposerKeydown);
      resizeConversationComposer();
    }

    if (state.status === "unlocked") {
      void decryptConversationMessages().then(scrollConversationThreadToLatest);
      setConversationComposeEnabled(root.dataset.canCompose === "true");
      setConversationUnlockVisible(false);
      setConversationSecureBadgeVisible(true);
      setConversationStatus("Chat key unlocked in this browser.");
      return;
    }

    void restoreConversationFromSession();
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
      await populateLoginChatKeyPayload(form, password);
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(form),
      });
      const responseUrl = new URL(response.url);
      const responseText = await response.text();
      const responseDocument = new DOMParser().parseFromString(
        responseText,
        "text/html",
      );
      if (response.redirected && responseUrl.pathname !== "/login") {
        if (responseUrl.pathname === "/verify-2fa-login") {
          pendingLoginPassword = password;
        } else {
          try {
            await ensureChatKeyUnlockedAfterAuth(password, responseDocument);
          } catch (error) {
            clearChatKeyMaterial();
          } finally {
            pendingLoginPassword = null;
          }
        }
        replaceDocument(responseText, response.url);
        return;
      }
      replaceDocument(responseText, response.url);
    } catch (error) {
      HTMLFormElement.prototype.submit.call(form);
    }
  }

  async function handleTwoFactorSubmit(event) {
    const form = event.currentTarget;
    if (!pendingLoginPassword || !window.fetch || !window.FormData) {
      return;
    }

    event.preventDefault();
    const password = pendingLoginPassword;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(form),
      });
      const responseUrl = new URL(response.url);
      const responseText = await response.text();
      const responseDocument = new DOMParser().parseFromString(
        responseText,
        "text/html",
      );
      if (response.redirected && responseUrl.pathname !== "/verify-2fa-login") {
        try {
          await ensureChatKeyUnlockedAfterAuth(password, responseDocument);
        } catch (error) {
          clearChatKeyMaterial();
        } finally {
          pendingLoginPassword = null;
        }
        replaceDocument(responseText, response.url);
        return;
      }
      replaceDocument(responseText, response.url);
    } catch (error) {
      pendingLoginPassword = null;
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
      crossTabSharingBound = false;
    }
    bindCrossTabChatKeySharing();

    document
      .querySelector("form[action$='/login']")
      ?.addEventListener("submit", handleLoginSubmit);
    document
      .querySelector("form[action$='/verify-2fa-login']")
      ?.addEventListener("submit", handleTwoFactorSubmit);
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
    ensureChatKeyUnlockedAfterAuth,
    provisionChatKey,
    rewrapForPasswordChange,
    unlockFromPassword,
  };

  document.addEventListener("DOMContentLoaded", function () {
    bindPage();
  });
})();

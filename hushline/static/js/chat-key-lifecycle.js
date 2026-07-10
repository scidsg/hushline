/******/ (() => { // webpackBootstrap
/*!*****************************************!*\
  !*** ./assets/js/chat-key-lifecycle.js ***!
  \*****************************************/
(function () {
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();
  const sessionStorageKey = "hushline:chat-private-jwk";
  const legacyBrowserStorageKey = "hushline:chat-private-jwk:browser-session";
  const crossTabChannelName = "hushline:chat-key-session";
  const crossTabRequestTimeoutMs = 750;
  const conversationPollMinIntervalMs = 3000;
  const tabId = window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
  let crossTabChannel = null;
  let crossTabSharingBound = false;
  let unlockedChatPrivateKey = null;
  let unlockedChatSigningPrivateKey = null;
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

  function canonicalStringify(value) {
    if (Array.isArray(value)) {
      return `[${value.map((item) => canonicalStringify(item)).join(",")}]`;
    }
    if (value && typeof value === "object") {
      return `{${Object.keys(value)
        .sort()
        .map(
          (key) => `${JSON.stringify(key)}:${canonicalStringify(value[key])}`,
        )
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  function normalizePrivateKeyBundle(value) {
    if (value?.ecdh_private_jwk) {
      return value;
    }
    return {
      ecdh_private_jwk: value,
      signing_private_jwk: null,
    };
  }

  function assertCryptoSupport() {
    if (!window.crypto?.subtle) {
      throw new Error("Web Crypto is unavailable.");
    }
  }

  function chatKeySessionId(sourceDocument = document) {
    return sourceDocument.body?.dataset.chatKeySessionId || "";
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

  async function decryptPrivateKeyBundle(chatKey, password) {
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
    return normalizePrivateKeyBundle(
      JSON.parse(textDecoder.decode(privateJwkBytes)),
    );
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

  async function importSigningPrivateKey(privateJwk) {
    if (!privateJwk) {
      return null;
    }
    const importJwk = {
      ...privateJwk,
      key_ops: ["sign"],
    };
    return window.crypto.subtle.importKey(
      "jwk",
      importJwk,
      {
        name: "ECDSA",
        namedCurve: importJwk.crv || "P-256",
      },
      false,
      ["sign"],
    );
  }

  function rememberUnlockedPrivateKeyBundle(
    privateKeyBundle,
    chatKey,
    sourceDocument = document,
  ) {
    const sessionId = chatKeySessionId(sourceDocument);
    const storedValue = JSON.stringify({
      key_version: chatKey.key_version,
      public_key: chatKey.public_key,
      public_signing_key: chatKey.public_signing_key || null,
      private_key_bundle: privateKeyBundle,
      session_id: sessionId,
    });

    try {
      sessionStorage.setItem(sessionStorageKey, storedValue);
    } catch (error) {
      // Private key material must not be persisted beyond this tab.
    }
  }

  function forgetUnlockedPrivateJwk() {
    try {
      sessionStorage.removeItem(sessionStorageKey);
    } catch (error) {
      // Keep clearing other storage locations.
    }
    try {
      localStorage.removeItem(legacyBrowserStorageKey);
    } catch (error) {
      return;
    }
  }

  function privateKeyBundleFromStoredValue(storedValue, chatKey) {
    if (!storedValue) {
      return null;
    }

    try {
      const stored = JSON.parse(storedValue);
      if (
        stored?.key_version !== chatKey.key_version ||
        stored.public_key !== chatKey.public_key ||
        (stored.public_signing_key || null) !==
          (chatKey.public_signing_key || null) ||
        !(stored.private_key_bundle || stored.private_jwk) ||
        stored.session_id !== chatKeySessionId()
      ) {
        return null;
      }
      return normalizePrivateKeyBundle(
        stored.private_key_bundle || stored.private_jwk,
      );
    } catch (error) {
      return null;
    }
  }

  function rememberedPrivateKeyBundleForChatKey(chatKey) {
    try {
      const privateKeyBundle = privateKeyBundleFromStoredValue(
        sessionStorage.getItem(sessionStorageKey),
        chatKey,
      );
      if (privateKeyBundle) {
        return privateKeyBundle;
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function touchUnlockedChatKeyUse() {
    return Boolean(unlockedChatPrivateKey || unlockedChatSigningPrivateKey);
  }

  async function restoreUnlockedChatKeyFromBundle(
    chatKey,
    privateKeyBundle,
    sourceDocument = document,
  ) {
    unlockedChatPrivateKey = await importPrivateKey(
      privateKeyBundle.ecdh_private_jwk,
    );
    unlockedChatSigningPrivateKey = await importSigningPrivateKey(
      privateKeyBundle.signing_private_jwk,
    );
    rememberUnlockedPrivateKeyBundle(privateKeyBundle, chatKey, sourceDocument);
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
      const privateKeyBundle = rememberedPrivateKeyBundleForChatKey(chatKey);
      if (!privateKeyBundle) {
        forgetUnlockedPrivateJwk();
        return false;
      }

      return restoreUnlockedChatKeyFromBundle(chatKey, privateKeyBundle);
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
    const sessionId = chatKeySessionId();
    if (!channel) {
      return false;
    }
    channel.postMessage({
      v: 1,
      source_tab_id: tabId,
      session_id: sessionId,
      ...message,
    });
    return true;
  }

  function bindCrossTabChatKeySharing() {
    if (
      crossTabSharingBound ||
      document.body?.dataset.authenticated !== "true" ||
      !chatKeySessionId()
    ) {
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
        message.v !== 1 ||
        message.source_tab_id === tabId ||
        message.session_id !== chatKeySessionId() ||
        message.type !== "request-unlocked-chat-key" ||
        !message.request_id
      ) {
        return;
      }

      const privateKeyBundle = rememberedPrivateKeyBundleForChatKey(
        message.chat_key,
      );
      if (!privateKeyBundle) {
        return;
      }

      postChatKeyBroadcast({
        type: "unlocked-chat-key",
        request_id: message.request_id,
        chat_key: message.chat_key,
        private_key_bundle: privateKeyBundle,
      });
    });
  }

  async function restoreUnlockedChatKeyFromOtherTab(chatKey) {
    const channel = chatKeyBroadcastChannel();
    const sessionId = chatKeySessionId();
    if (!channel || !chatKey || !sessionId) {
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
          message.v !== 1 ||
          message.source_tab_id === tabId ||
          message.session_id !== sessionId ||
          message.type !== "unlocked-chat-key" ||
          message.request_id !== requestId ||
          message.chat_key?.key_version !== chatKey.key_version ||
          message.chat_key?.public_key !== chatKey.public_key ||
          (message.chat_key?.public_signing_key || null) !==
            (chatKey.public_signing_key || null) ||
          !message.private_key_bundle
        ) {
          return;
        }

        window.clearTimeout(timeout);
        channel.removeEventListener("message", onMessage);
        try {
          await restoreUnlockedChatKeyFromBundle(
            chatKey,
            message.private_key_bundle,
          );
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
        session_id: sessionId,
        chat_key: {
          key_version: chatKey.key_version,
          public_key: chatKey.public_key,
          public_signing_key: chatKey.public_signing_key || null,
        },
      });
    });
  }

  async function signingPrivateKeyForChatKey(chatKey) {
    if (!chatKey) {
      return null;
    }
    if (await restoreUnlockedChatKey(chatKey)) {
      return unlockedChatSigningPrivateKey;
    }
    if (await restoreUnlockedChatKeyFromOtherTab(chatKey)) {
      return unlockedChatSigningPrivateKey;
    }
    return null;
  }

  async function unlockFromPassword(
    chatKey,
    password,
    sourceDocument = document,
  ) {
    if (!chatKey) {
      clearChatKeyMaterial();
      state.status = "no-key";
      return true;
    }

    assertCryptoSupport();
    let privateKeyBundle = null;
    try {
      privateKeyBundle = await decryptPrivateKeyBundle(chatKey, password);
      return restoreUnlockedChatKeyFromBundle(
        chatKey,
        privateKeyBundle,
        sourceDocument,
      );
    } catch (error) {
      clearChatKeyMaterial();
      state.status = "locked";
      state.keyVersion = chatKey.key_version || null;
      state.lastError = "Chat key unlock failed.";
      return false;
    } finally {
      privateKeyBundle = null;
    }
  }

  async function encryptPrivateKeyBundle(privateKeyBundle, password) {
    const salt = window.crypto.getRandomValues(new Uint8Array(16));
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const wrappingKey = await deriveWrappingKey(
      password,
      salt,
      {
        iterations: 310000,
        hash: "SHA-256",
      },
      ["encrypt"],
    );
    const encryptedBytes = new Uint8Array(
      await window.crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv,
        },
        wrappingKey,
        textEncoder.encode(JSON.stringify(privateKeyBundle)),
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
    const signingKeyMaterial = await createSigningKeyMaterial();
    const publicJwk = await window.crypto.subtle.exportKey(
      "jwk",
      keyPair.publicKey,
    );
    const privateKeyBundle = {
      ecdh_private_jwk: await window.crypto.subtle.exportKey(
        "jwk",
        keyPair.privateKey,
      ),
      signing_private_jwk: signingKeyMaterial.signingPrivateJwk,
    };
    const wrapped = await encryptPrivateKeyBundle(privateKeyBundle, password);

    return {
      privateKeyBundle,
      payload: {
        public_key: JSON.stringify(publicJwk),
        public_signing_key: JSON.stringify(signingKeyMaterial.publicSigningJwk),
        ...wrapped,
      },
    };
  }

  async function createSigningKeyMaterial() {
    const signingKeyPair = await window.crypto.subtle.generateKey(
      {
        name: "ECDSA",
        namedCurve: "P-256",
      },
      true,
      ["sign", "verify"],
    );
    return {
      publicSigningJwk: await window.crypto.subtle.exportKey(
        "jwk",
        signingKeyPair.publicKey,
      ),
      signingPrivateJwk: await window.crypto.subtle.exportKey(
        "jwk",
        signingKeyPair.privateKey,
      ),
    };
  }

  async function rewrapForPasswordChange(chatKey, oldPassword, newPassword) {
    assertCryptoSupport();
    let privateKeyBundle = null;
    try {
      privateKeyBundle = await decryptPrivateKeyBundle(chatKey, oldPassword);
      let publicSigningKey = chatKey.public_signing_key || null;
      if (!publicSigningKey || !privateKeyBundle.signing_private_jwk) {
        const signingKeyMaterial = await createSigningKeyMaterial();
        privateKeyBundle = {
          ...privateKeyBundle,
          signing_private_jwk: signingKeyMaterial.signingPrivateJwk,
        };
        publicSigningKey = JSON.stringify(signingKeyMaterial.publicSigningJwk);
      }
      const wrapped = await encryptPrivateKeyBundle(
        privateKeyBundle,
        newPassword,
      );
      return {
        public_key: chatKey.public_key,
        public_signing_key: publicSigningKey,
        recovery_state: "available",
        ...wrapped,
      };
    } finally {
      privateKeyBundle = null;
    }
  }

  async function importPublicKey(publicKeyValue) {
    const publicJwk =
      typeof publicKeyValue === "string"
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

  async function importSigningPublicKey(publicKeyValue) {
    if (!publicKeyValue) {
      return null;
    }
    const publicJwk =
      typeof publicKeyValue === "string"
        ? JSON.parse(publicKeyValue)
        : publicKeyValue;
    return window.crypto.subtle.importKey(
      "jwk",
      publicJwk,
      {
        name: "ECDSA",
        namedCurve: publicJwk.crv || "P-256",
      },
      false,
      ["verify"],
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

  async function signChatEnvelope(envelope) {
    if (!unlockedChatSigningPrivateKey) {
      return null;
    }
    if (!touchUnlockedChatKeyUse()) {
      return null;
    }
    const signedPayload = {
      v: envelope.v,
      algorithm: envelope.algorithm,
      ephemeral_public_key: envelope.ephemeral_public_key,
      iv: envelope.iv,
      ciphertext: envelope.ciphertext,
      context: envelope.context,
    };
    const signature = new Uint8Array(
      await window.crypto.subtle.sign(
        {
          name: "ECDSA",
          hash: "SHA-256",
        },
        unlockedChatSigningPrivateKey,
        textEncoder.encode(canonicalStringify(signedPayload)),
      ),
    );
    return bytesToBase64(signature);
  }

  async function verifyChatEnvelope(envelope, senderPublicSigningKey) {
    if (envelope.v !== 2) {
      return true;
    }
    const verificationKey = await importSigningPublicKey(
      senderPublicSigningKey,
    );
    if (!verificationKey || !envelope.signature) {
      return false;
    }
    const signedPayload = {
      v: envelope.v,
      algorithm: envelope.algorithm,
      ephemeral_public_key: envelope.ephemeral_public_key,
      iv: envelope.iv,
      ciphertext: envelope.ciphertext,
      context: envelope.context,
    };
    return window.crypto.subtle.verify(
      {
        name: "ECDSA",
        hash: "SHA-256",
      },
      verificationKey,
      base64ToBytes(envelope.signature),
      textEncoder.encode(canonicalStringify(signedPayload)),
    );
  }

  async function encryptForPublicKey(
    plaintext,
    publicKeyValue,
    context = null,
  ) {
    assertCryptoSupport();
    const recipientPublicKeyValue =
      typeof publicKeyValue === "object" && publicKeyValue?.public_key
        ? publicKeyValue.public_key
        : publicKeyValue;
    const recipientPublicKey = await importPublicKey(recipientPublicKeyValue);
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
    const envelopeContext =
      context && publicKeyValue?.participant_id && unlockedChatSigningPrivateKey
        ? {
            ...context,
            recipient_participant_id: String(publicKeyValue.participant_id),
            recipient_key_version: publicKeyValue.key_version || null,
            recipient_public_key_fingerprint:
              publicKeyValue.public_key_fingerprint || null,
          }
        : null;
    const encryptParams = {
      name: "AES-GCM",
      iv,
    };
    if (envelopeContext) {
      encryptParams.additionalData = textEncoder.encode(
        canonicalStringify(envelopeContext),
      );
    }
    const ciphertext = new Uint8Array(
      await window.crypto.subtle.encrypt(
        encryptParams,
        messageKey,
        textEncoder.encode(plaintext),
      ),
    );
    const ephemeralPublicJwk = await window.crypto.subtle.exportKey(
      "jwk",
      ephemeralKeyPair.publicKey,
    );

    const envelope = {
      algorithm: "ECDH-P256-AES-GCM",
      ephemeral_public_key: JSON.stringify(ephemeralPublicJwk),
      iv: bytesToBase64(iv),
      ciphertext: bytesToBase64(ciphertext),
    };
    if (envelopeContext) {
      envelope.v = 2;
      envelope.context = envelopeContext;
      envelope.signature = await signChatEnvelope(envelope);
    }
    return JSON.stringify(envelope);
  }

  async function decryptChatCiphertext(
    encryptedPayload,
    senderPublicSigningKey = null,
  ) {
    if (!unlockedChatPrivateKey) {
      throw new Error("Chat key is locked.");
    }
    if (!touchUnlockedChatKeyUse()) {
      throw new Error("Chat key is locked.");
    }
    assertCryptoSupport();
    const envelope = JSON.parse(encryptedPayload);
    if (envelope.algorithm !== "ECDH-P256-AES-GCM") {
      throw new Error("Unsupported chat ciphertext.");
    }
    if (
      envelope.v === 2 &&
      !(await verifyChatEnvelope(envelope, senderPublicSigningKey))
    ) {
      throw new Error("Chat signature verification failed.");
    }
    const ephemeralPublicKey = await importPublicKey(
      envelope.ephemeral_public_key,
    );
    const messageKey = await deriveChatMessageKey(
      ephemeralPublicKey,
      unlockedChatPrivateKey,
      ["decrypt"],
    );
    const decryptParams = {
      name: "AES-GCM",
      iv: base64ToBytes(envelope.iv),
    };
    if (envelope.v === 2) {
      decryptParams.additionalData = textEncoder.encode(
        canonicalStringify(envelope.context),
      );
    }
    const plaintextBytes = await window.crypto.subtle.decrypt(
      decryptParams,
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
    return (
      sourceDocument
        ?.querySelector("input[name='csrf_token'], meta[name='csrf-token']")
        ?.getAttribute("value") ||
      sourceDocument
        ?.querySelector("meta[name='csrf-token']")
        ?.getAttribute("content") ||
      ""
    );
  }

  async function provisionChatKey(
    chatKeyUrl,
    password,
    sourceDocument = document,
  ) {
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
    await restoreUnlockedChatKeyFromBundle(
      chatKey,
      created.privateKeyBundle,
      sourceDocument,
    );
    return chatKey;
  }

  async function upgradeChatKeySigningCapability(
    chatKey,
    password,
    chatKeyUrl,
    sourceDocument = document,
  ) {
    if (!chatKey || chatKey.public_signing_key) {
      return chatKey;
    }

    let privateKeyBundle = null;
    try {
      privateKeyBundle = await decryptPrivateKeyBundle(chatKey, password);
      const signingKeyMaterial = await createSigningKeyMaterial();
      const upgradedPrivateKeyBundle = {
        ...privateKeyBundle,
        signing_private_jwk: signingKeyMaterial.signingPrivateJwk,
      };
      const wrapped = await encryptPrivateKeyBundle(
        upgradedPrivateKeyBundle,
        password,
      );
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
        body: JSON.stringify({
          public_key: chatKey.public_key,
          public_signing_key: JSON.stringify(
            signingKeyMaterial.publicSigningJwk,
          ),
          recovery_state: "available",
          ...wrapped,
        }),
      });
      if (!response.ok) {
        throw new Error("Chat key signing upgrade failed.");
      }

      const responsePayload = await response.json();
      const upgradedChatKey = responsePayload.chat_key;
      if (!upgradedChatKey) {
        throw new Error("Upgraded chat key was unavailable.");
      }
      await restoreUnlockedChatKeyFromBundle(
        upgradedChatKey,
        upgradedPrivateKeyBundle,
        sourceDocument,
      );
      return upgradedChatKey;
    } finally {
      privateKeyBundle = null;
    }
  }

  async function ensureChatKeyUnlockedAfterAuth(
    password,
    sourceDocument = document,
  ) {
    const chatKeyUrl = chatKeyUrlFromCurrentOrigin();
    const chatKey = await fetchChatKey(chatKeyUrl);
    if (chatKey) {
      const unlocked = await unlockFromPassword(
        chatKey,
        password,
        sourceDocument,
      );
      if (unlocked && !chatKey.public_signing_key) {
        try {
          await upgradeChatKeySigningCapability(
            chatKey,
            password,
            chatKeyUrl,
            sourceDocument,
          );
        } catch (error) {
          return unlocked;
        }
      }
      return unlocked;
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
    const hadUnlockedKey = Boolean(
      unlockedChatPrivateKey ||
        unlockedChatSigningPrivateKey ||
        state.status === "unlocked",
    );
    forgetUnlockedPrivateJwk();
    unlockedChatPrivateKey = null;
    unlockedChatSigningPrivateKey = null;
    state.status = "empty";
    state.keyVersion = null;
    state.lastError = null;
    if (hadUnlockedKey) {
      updateConversationLockedAfterKeyClear();
    }
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
    document.dispatchEvent(new CustomEvent("hushline:document-replaced"));
    bindPage();
  }

  function chatKeyUrlFromCurrentOrigin() {
    return new URL(
      "/settings/chat-key.json",
      window.location.origin,
    ).toString();
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
    const statuses = document.querySelectorAll("[data-conversation-status]");
    statuses.forEach((status) => {
      status.textContent = message;
    });
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

  function updateConversationLockedAfterKeyClear() {
    const root = document.getElementById("conversation-chat");
    if (!root) {
      return;
    }

    setConversationComposeEnabled(false);
    setConversationUnlockVisible(true);
    setConversationSecureBadgeVisible(false);
    setConversationStatus(
      "Chat key expired for this browser session. Secure replies are paused.",
    );
  }

  function currentConversationParticipantId() {
    const root = document.getElementById("conversation-chat");
    return root?.dataset.participantId || "";
  }

  function conversationParticipantPublicKeys() {
    return jsonFromScript("conversationParticipantPublicKeys", []);
  }

  function conversationParticipantSigningPublicKeys() {
    return jsonFromScript("conversationParticipantSigningPublicKeys", []);
  }

  function participantPublicKeyById(participantId) {
    return conversationParticipantPublicKeys().find(
      (participantKey) =>
        String(participantKey.participant_id) === String(participantId),
    );
  }

  function conversationMessageIds(sourceDocument = document) {
    return Array.from(
      sourceDocument.querySelectorAll("[data-conversation-message-id]"),
    ).map(
      (messageElement) => messageElement.dataset.conversationMessageId || "",
    );
  }

  function conversationMessagesSignature(sourceDocument = document) {
    const copies =
      sourceDocument.getElementById("conversationMessageCopies")?.textContent ||
      "";
    return `${conversationMessageIds(sourceDocument).join(",")}:${copies}`;
  }

  function conversationMessageSenderIdFromPayload(encryptedPayload) {
    if (!encryptedPayload || typeof encryptedPayload !== "string") {
      return null;
    }
    try {
      const envelope = JSON.parse(encryptedPayload);
      return envelope?.context?.sender_participant_id || null;
    } catch (error) {
      return null;
    }
  }

  function conversationMessageSenderSigningFingerprintFromPayload(
    encryptedPayload,
  ) {
    if (!encryptedPayload || typeof encryptedPayload !== "string") {
      return null;
    }
    try {
      const envelope = JSON.parse(encryptedPayload);
      return envelope?.context?.sender_public_signing_key_fingerprint || null;
    } catch (error) {
      return null;
    }
  }

  function participantPublicKeyBySigningFingerprint(fingerprint) {
    if (!fingerprint) {
      return null;
    }
    return (
      conversationParticipantPublicKeys().find(
        (participantKey) =>
          participantKey.public_signing_key_fingerprint === fingerprint,
      ) ||
      conversationParticipantSigningPublicKeys().find(
        (participantKey) =>
          participantKey.public_signing_key_fingerprint === fingerprint,
      )
    );
  }

  function conversationMessagePayloadFromPlaintext(plaintext) {
    try {
      const parsed = JSON.parse(plaintext);
      if (
        parsed &&
        typeof parsed === "object" &&
        typeof parsed.content === "string"
      ) {
        return {
          content: parsed.content,
          createdAt:
            typeof parsed.created_at === "string" ? parsed.created_at : null,
        };
      }
    } catch (error) {
      // Legacy payloads still contain raw plaintext.
    }
    return { content: plaintext, createdAt: null };
  }

  function formatConversationMessageTimestamp(createdAt) {
    if (typeof createdAt !== "string") {
      return "";
    }
    const date = new Date(createdAt);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
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

  async function refreshConversationMessages({
    force = false,
    scroll = false,
  } = {}) {
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
      cache: "no-store",
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
      !force &&
      conversationMessagesSignature(nextDocument) ===
        conversationMessagesSignature()
    ) {
      return false;
    }

    currentCopies.textContent = nextCopies.textContent;
    thread.replaceChildren(
      ...Array.from(nextThread.children).map((child) => {
        return document.importNode(child, true);
      }),
    );
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
      const messageTimeElement = messageContainer?.querySelector(
        "[data-conversation-message-time]",
      );
      if (!messageElement) {
        continue;
      }

      try {
        const senderParticipantId = conversationMessageSenderIdFromPayload(
          copy.encrypted_payload,
        );
        const senderKey =
          participantPublicKeyById(senderParticipantId) ||
          participantPublicKeyBySigningFingerprint(
            conversationMessageSenderSigningFingerprintFromPayload(
              copy.encrypted_payload,
            ),
          );
        const plaintext = await decryptChatCiphertext(
          copy.encrypted_payload,
          senderKey?.public_signing_key || null,
        );
        const messagePayload =
          conversationMessagePayloadFromPlaintext(plaintext);
        messageElement.textContent = messagePayload.content;
        if (messageTimeElement) {
          messageTimeElement.setAttribute(
            "datetime",
            messagePayload.createdAt || "",
          );
          messageTimeElement.textContent = formatConversationMessageTimestamp(
            messagePayload.createdAt,
          );
        }
      } catch (error) {
        messageElement.textContent =
          "This message cannot be decrypted in this browser.";
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
      body.setAttribute("aria-disabled", enabled ? "false" : "true");
    }
    if (submit) {
      submit.disabled = !enabled;
      submit.setAttribute("aria-disabled", enabled ? "false" : "true");
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
    const participantKeys = conversationParticipantPublicKeys();
    if (!root?.dataset.messageUrl || !plaintext) {
      return;
    }
    if (root.dataset.canCompose !== "true") {
      setConversationStatus(
        "Replies are unavailable until you have an active signing-capable Hush Line chat key and every participant has an active chat key.",
      );
      return;
    }

    setConversationStatus("Encrypting reply...");
    try {
      const encryptedCopies = {};
      const timestamp = new Date().toISOString();
      const context = {
        purpose: "hushline.chat.message",
        conversation_public_id: root.dataset.conversationPublicId || "",
        sender_participant_id: currentConversationParticipantId(),
      };
      const plaintextPayload = JSON.stringify({
        content: plaintext,
        created_at: timestamp,
      });
      for (const participantKey of participantKeys) {
        encryptedCopies[String(participantKey.participant_id)] =
          await encryptForPublicKey(plaintextPayload, participantKey, context);
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
      form.dispatchEvent(
        new Event("submit", { cancelable: true, bubbles: true }),
      );
    }
  }

  function conversationCsrfToken() {
    const root = document.getElementById("conversation-chat");
    return (
      root?.dataset.csrfToken ||
      document
        .getElementById("conversation-compose-form")
        ?.querySelector("input[name='csrf_token']")?.value ||
      csrfTokenFromDocument()
    );
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

    const configuredInterval = Number.parseInt(
      root.dataset.presenceIntervalMs,
      10,
    );
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
      if (
        document.visibilityState !== "visible" ||
        state.status !== "unlocked"
      ) {
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
        setConversationStatus(
          "No active chat key is available for this account.",
        );
        return;
      }
      if (await restoreUnlockedChatKey(chatKey)) {
        await decryptConversationMessages();
        await refreshConversationMessages({ force: true });
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
        await refreshConversationMessages({ force: true });
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
      setConversationStatus(
        "Chat could not be unlocked in this browser session.",
      );
    }
  }

  function bindConversation() {
    const root = document.getElementById("conversation-chat");
    if (!root) {
      return;
    }
    setConversationComposeEnabled(root.dataset.canCompose === "true");

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
        status.textContent =
          "Chat key unlock failed. Password was not changed.";
      }
    }
  }

  function bindChatKeyCleanupTriggers() {
    if (document.documentElement.dataset.chatKeyCleanupBound === "true") {
      return;
    }
    document.documentElement.dataset.chatKeyCleanupBound = "true";
    document.addEventListener("click", (event) => {
      const trigger = event.target?.closest?.(
        "[data-clear-chat-key-material='true']",
      );
      if (trigger) {
        clearChatKeyMaterial();
      }
    });
    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (form?.matches?.("[data-clear-chat-key-material='true']")) {
        clearChatKeyMaterial();
      }
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
    bindChatKeyCleanupTriggers();
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
    signingPrivateKeyForChatKey,
    unlockFromPassword,
  };

  document.addEventListener("DOMContentLoaded", function () {
    bindPage();
  });
})();

/******/ })()
;
//# sourceMappingURL=chat-key-lifecycle.js.map
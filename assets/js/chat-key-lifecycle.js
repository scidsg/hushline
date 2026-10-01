(function () {
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();
  const sessionStorageKey = "hushline:chat-private-jwk";
  const legacyBrowserStorageKey = "hushline:chat-private-jwk:browser-session";
  const crossTabChannelName = "hushline:chat-key-session";
  const pqDeviceSessionStorageKey = "hushline:pq-device-session";
  const crossTabRequestTimeoutMs = 750;
  const conversationPollMinIntervalMs = 3000;
  const tabId = window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
  let crossTabChannel = null;
  let crossTabSharingBound = false;
  let unlockedChatPrivateKey = null;
  let unlockedChatSigningPrivateKey = null;
  let unlockedPqAccountRoot = null;
  let unlockedPqAccountIdentityPrivateKey = null;
  let unlockedPqAccountIdentityPublicKey = null;
  let pendingLoginPassword = null;
  let conversationSubmitInFlight = false;
  let sessionLockTimer = null;
  const state = {
    status: "empty",
    keyVersion: null,
    lastError: null,
  };
  const pqDeviceState = {
    accountId: null,
    deviceId: null,
    status: "unavailable",
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

  function base64UrlToBytes(value) {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    return base64ToBytes(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
  }

  function bytesToBase64Url(value) {
    return bytesToBase64(value)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/u, "");
  }

  function createPqAccountRoot() {
    const root = window.crypto.getRandomValues(new Uint8Array(32));
    try {
      return bytesToBase64Url(root);
    } finally {
      root.fill(0);
    }
  }

  function safeBase64UrlToBytes(value) {
    try {
      return base64UrlToBytes(value);
    } catch (error) {
      return null;
    }
  }

  function joinBytes(...values) {
    const length = values.reduce((total, value) => total + value.length, 0);
    const joined = new Uint8Array(length);
    let offset = 0;
    values.forEach((value) => {
      joined.set(value, offset);
      offset += value.length;
    });
    return joined;
  }

  async function verifyEd25519Json(publicKey, signature, domain, value) {
    const verificationKey = await window.crypto.subtle.importKey(
      "raw",
      base64UrlToBytes(publicKey),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return window.crypto.subtle.verify(
      { name: "Ed25519" },
      verificationKey,
      base64UrlToBytes(signature),
      joinBytes(
        textEncoder.encode(domain),
        new Uint8Array([0]),
        textEncoder.encode(canonicalStringify(value)),
      ),
    );
  }

  async function signEd25519Json(privateKey, domain, value) {
    return bytesToBase64Url(
      new Uint8Array(
        await window.crypto.subtle.sign(
          { name: "Ed25519" },
          privateKey,
          joinBytes(
            textEncoder.encode(domain),
            new Uint8Array([0]),
            textEncoder.encode(canonicalStringify(value)),
          ),
        ),
      ),
    );
  }

  async function createEd25519KeyMaterial() {
    const keyPair = await window.crypto.subtle.generateKey(
      { name: "Ed25519" },
      true,
      ["sign", "verify"],
    );
    return {
      privateJwk: await window.crypto.subtle.exportKey("jwk", keyPair.privateKey),
      publicKey: bytesToBase64Url(
        new Uint8Array(
          await window.crypto.subtle.exportKey("raw", keyPair.publicKey),
        ),
      ),
    };
  }

  function importEd25519PrivateKey(privateJwk) {
    return window.crypto.subtle.importKey(
      "jwk",
      { ...privateJwk, key_ops: ["sign"] },
      { name: "Ed25519" },
      false,
      ["sign"],
    );
  }

  async function sha256Hex(value) {
    const digest = new Uint8Array(
      await window.crypto.subtle.digest("SHA-256", value),
    );
    return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join(
      "",
    );
  }

  async function verifyPqMembership(
    accountIdentityPublicKey,
    device,
    minimumMembershipSequence = 0,
    expectedAccountId = null,
    allowExpired = false,
  ) {
    try {
      const membership = device?.membership;
      const expiresAt = Date.parse(membership?.expires_at);
      const signingKey = base64UrlToBytes(
        membership?.device_signing_public_key || "",
      );
      const protocolIdentity = base64UrlToBytes(
        membership?.protocol_identity_public_key || "",
      );
      if (
        !membership ||
        membership.status !== "active" ||
        membership.capabilities?.length !== 1 ||
        membership.capabilities[0] !== "HL-PQCHAT-1" ||
        membership.archive_suites?.length !== 1 ||
        membership.archive_suites[0] !==
          "MLKEM768-X25519-HKDF-SHA256-AES256GCM" ||
        (expectedAccountId && membership.account_id !== expectedAccountId) ||
        !Number.isInteger(membership.membership_sequence) ||
        membership.membership_sequence < minimumMembershipSequence ||
        !Number.isInteger(membership.one_time_prekey_start) ||
        !Number.isInteger(membership.one_time_prekey_end) ||
        membership.one_time_prekey_start < 1 ||
        membership.one_time_prekey_start > membership.one_time_prekey_end ||
        signingKey.length !== 32 ||
        protocolIdentity.length !== 33 ||
        protocolIdentity[0] !== 0x05 ||
        !Number.isInteger(membership.protocol_registration_id) ||
        membership.protocol_registration_id < 1 ||
        membership.protocol_registration_id > 16380 ||
        !Number.isFinite(expiresAt) ||
        (!allowExpired && expiresAt <= Date.now())
      ) {
        return false;
      }
      const membershipBytes = textEncoder.encode(
        canonicalStringify(membership),
      );
      if ((await sha256Hex(membershipBytes)) !== device.membership_sha256) {
        return false;
      }
      return await verifyEd25519Json(
        accountIdentityPublicKey,
        device.membership_signature,
        "HushLine/HL-PQCHAT-1/device-membership/v1",
        membership,
      );
    } catch (error) {
      return false;
    }
  }

  async function verifyPqPrekeyClaim(
    claim,
    minimumMembershipSequence = 0,
    expectedAccountId = null,
    expectedAccountIdentityPublicKey = null,
  ) {
    const device = claim?.device;
    if (
      (expectedAccountIdentityPublicKey &&
        claim?.account_identity_public_key !==
          expectedAccountIdentityPublicKey) ||
      !(await verifyPqMembership(
        claim?.account_identity_public_key,
        device,
        minimumMembershipSequence,
        expectedAccountId,
      ))
    ) {
      return false;
    }
    const membership = device.membership;
    const verificationKey = membership.device_signing_public_key;
    const claimExpiresAt = Date.parse(claim?.claim_expires_at);
    if (!Number.isFinite(claimExpiresAt) || claimExpiresAt <= Date.now()) {
      return false;
    }
    const entries = [
      ["signed", claim.signed_prekey],
      ["one-time", claim.one_time_prekey],
    ];
    for (const [kind, key] of entries) {
      const classicalPublicKey = safeBase64UrlToBytes(
        key?.classical_public_key || "",
      );
      const pqPublicKey = safeBase64UrlToBytes(key?.pq_public_key || "");
      const keyExpiresAt = Date.parse(key?.expires_at);
      if (
        !classicalPublicKey ||
        classicalPublicKey.length !== 33 ||
        classicalPublicKey[0] !== 0x05 ||
        !pqPublicKey ||
        pqPublicKey.length !== 1569 ||
        pqPublicKey[0] !== 0x08 ||
        !Number.isInteger(key?.key_id) ||
        (kind === "signed" &&
          key.key_id !== membership.signed_prekey_id) ||
        (kind === "one-time" &&
          (key.key_id < membership.one_time_prekey_start ||
            key.key_id > membership.one_time_prekey_end)) ||
        !Number.isFinite(keyExpiresAt) ||
        keyExpiresAt <= Date.now()
      ) {
        return false;
      }
      const unsignedKey = { ...key };
      delete unsignedKey.device_signature;
      let verified = false;
      try {
        verified = await verifyEd25519Json(
          verificationKey,
          key.device_signature,
          "HushLine/HL-PQCHAT-1/prekey-publication/v1",
          {
            device_id: membership.device_id,
            key: unsignedKey,
            kind,
            membership_sequence: membership.membership_sequence,
            protocol: "HL-PQCHAT-1",
          },
        );
      } catch (error) {
        return false;
      }
      if (!verified) {
        return false;
      }
    }
    return true;
  }

  async function verifyPqArchive(
    account,
    minimumMembershipSequence = 0,
    expectedAccountIdentityPublicKey = null,
  ) {
    try {
      const archive = account?.archive;
      const publicKey = safeBase64UrlToBytes(archive?.public_key || "");
      if (
        account?.protocol !== "HL-PQCHAT-1" ||
        (expectedAccountIdentityPublicKey &&
          account.identity_public_key !== expectedAccountIdentityPublicKey) ||
        archive?.suite !== "MLKEM768-X25519-HKDF-SHA256-AES256GCM" ||
        !Number.isInteger(archive?.epoch) ||
        archive.epoch < 1 ||
        !Number.isInteger(account?.membership_sequence) ||
        account.membership_sequence < minimumMembershipSequence ||
        !publicKey ||
        publicKey.length !== 1216 ||
        !Array.isArray(account.devices) ||
        account.devices.length === 0
      ) {
        return false;
      }
      const publicKeySha256 = await sha256Hex(publicKey);
      for (const device of account.devices) {
        if (
          !(await verifyPqMembership(
            account.identity_public_key,
            device,
            0,
            account.account_id,
          )) ||
          device.membership.membership_sequence >
            account.membership_sequence ||
          device.membership.archive_epoch !== archive.epoch ||
          device.membership.archive_public_key_sha256 !== publicKeySha256
        ) {
          return false;
        }
      }
      return true;
    } catch (error) {
      return false;
    }
  }

  function normalizePrivateKeyBundle(value) {
    if (value?.ecdh_private_jwk) {
      return {
        ...value,
        pq_account_root: value.pq_account_root || null,
        pq_account_identity_private_jwk:
          value.pq_account_identity_private_jwk || null,
      };
    }
    return {
      ecdh_private_jwk: value,
      pq_account_root: null,
      pq_account_identity_private_jwk: null,
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
    const accountRoot = privateKeyBundle.pq_account_root
      ? safeBase64UrlToBytes(privateKeyBundle.pq_account_root)
      : null;
    if (accountRoot && accountRoot.length !== 32) {
      throw new Error("PQ account root is malformed.");
    }
    unlockedPqAccountRoot = privateKeyBundle.pq_account_root || null;
    unlockedPqAccountIdentityPrivateKey = privateKeyBundle
      .pq_account_identity_private_jwk
      ? await importEd25519PrivateKey(
          privateKeyBundle.pq_account_identity_private_jwk,
        )
      : null;
    unlockedPqAccountIdentityPublicKey =
      privateKeyBundle.pq_account_identity_private_jwk?.x || null;
    rememberUnlockedPrivateKeyBundle(privateKeyBundle, chatKey, sourceDocument);
    state.status = "unlocked";
    state.keyVersion = chatKey.key_version;
    state.lastError = null;
    restorePqDeviceState(sourceDocument);
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
        message.session_id !== chatKeySessionId()
      ) {
        return;
      }
      if (message.type === "lock-chat-key") {
        clearChatKeyMaterial({ broadcast: false });
        return;
      }
      if (message.type !== "request-unlocked-chat-key" || !message.request_id) {
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
    const pqAccountIdentity = await createEd25519KeyMaterial();
    const publicJwk = await window.crypto.subtle.exportKey(
      "jwk",
      keyPair.publicKey,
    );
    const privateKeyBundle = {
      ecdh_private_jwk: await window.crypto.subtle.exportKey(
        "jwk",
        keyPair.privateKey,
      ),
      pq_account_root: createPqAccountRoot(),
      pq_account_identity_private_jwk: pqAccountIdentity.privateJwk,
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
      if (!privateKeyBundle.pq_account_root) {
        privateKeyBundle = {
          ...privateKeyBundle,
          pq_account_root: createPqAccountRoot(),
        };
      }
      if (!privateKeyBundle.pq_account_identity_private_jwk) {
        const identity = await createEd25519KeyMaterial();
        privateKeyBundle = {
          ...privateKeyBundle,
          pq_account_identity_private_jwk: identity.privateJwk,
        };
      }
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
    lockIfAuthenticationEnded(response);
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

  async function postPqDeviceJson(path, payload, sourceDocument = document) {
    const headers = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    const csrfToken = csrfTokenFromDocument(sourceDocument);
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }
    const response = await fetch(new URL(path, window.location.origin), {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify(payload || {}),
    });
    lockIfAuthenticationEnded(response);
    const body = await response.json();
    if (!response.ok) {
      const error = new Error(body?.error || "PQ device enrollment failed.");
      error.code = body?.error || "INTERNAL_ERROR";
      throw error;
    }
    return body;
  }

  function pqTimestamp(date) {
    return date.toISOString().replace(/\.\d{3}Z$/u, "Z");
  }

  async function signUnlockValue(value, domain) {
    if (!unlockedChatSigningPrivateKey) {
      throw new Error("PQ device enrollment requires an unlocked chat key.");
    }
    const signature = new Uint8Array(
      await window.crypto.subtle.sign(
        { hash: "SHA-256", name: "ECDSA" },
        unlockedChatSigningPrivateKey,
        joinBytes(
          textEncoder.encode(domain),
          new Uint8Array([0]),
          textEncoder.encode(canonicalStringify(value)),
        ),
      ),
    );
    return bytesToBase64Url(signature);
  }

  async function preparePqDeviceEnrollment(account) {
    const protocol = window.HushLinePqProtocol;
    if (
      !protocol?.createWorkerClient ||
      !unlockedPqAccountIdentityPrivateKey ||
      !unlockedPqAccountRoot
    ) {
      throw new Error("PQ device enrollment capability is unavailable.");
    }

    const deviceId = window.crypto.randomUUID();
    const membershipSequence = account.membership_sequence + 1;
    const signedPrekeyId = 1;
    const oneTimePrekeyStart = 1;
    const prekeyCount = 100;
    const client = protocol.createWorkerClient();
    try {
      const created = await client.createDevice({
        address: {
          deviceId: 1,
          name: `${account.account_id}.${deviceId}`,
        },
        prekeyCount,
        prekeyStart: oneTimePrekeyStart,
        signedPrekeyId,
      });
      const deviceSigning = await createEd25519KeyMaterial();
      const now = new Date();
      const membershipExpiresAt = new Date(
        now.getTime() + 30 * 24 * 60 * 60 * 1000,
      );
      const signedPrekeyExpiresAt = new Date(
        now.getTime() + 7 * 24 * 60 * 60 * 1000,
      );
      let archive = [...(account.archive_epochs || [])]
        .filter((value) => !value.retired_at)
        .sort((left, right) => right.epoch - left.epoch)[0];
      let enrollmentArchive = null;
      if (!archive) {
        const nextArchiveEpoch =
          Math.max(
            0,
            ...(account.archive_epochs || []).map((value) => value.epoch),
          ) + 1;
        archive = await createPqArchiveEpoch(
          { accountId: account.account_id, epoch: nextArchiveEpoch },
          { client },
        );
        enrollmentArchive = {
          encrypted_private_key: archive.encryptedPrivateKey,
          epoch: archive.epoch,
          public_key: archive.publicKey,
        };
        archive = {
          encrypted_private_key: archive.encryptedPrivateKey,
          epoch: archive.epoch,
          public_key: archive.publicKey,
        };
      }
      const membership = {
        account_id: account.account_id,
        archive_epoch: archive.epoch,
        archive_public_key_sha256: await sha256Hex(
          base64UrlToBytes(archive.public_key),
        ),
        archive_suites: ["MLKEM768-X25519-HKDF-SHA256-AES256GCM"],
        capabilities: ["HL-PQCHAT-1"],
        device_id: deviceId,
        device_signing_public_key: deviceSigning.publicKey,
        expires_at: pqTimestamp(membershipExpiresAt),
        identity_version: Math.max(1, account.identity_version),
        issued_at: pqTimestamp(now),
        membership_sequence: membershipSequence,
        one_time_prekey_end: oneTimePrekeyStart + prekeyCount - 1,
        one_time_prekey_start: oneTimePrekeyStart,
        protocol_identity_public_key: created.publicBundle.identityKey,
        protocol_registration_id: created.publicBundle.registrationId,
        signed_prekey_id: signedPrekeyId,
        status: "active",
      };
      const accountIdentityPublicKey = unlockedPqAccountIdentityPublicKey;
      if (!accountIdentityPublicKey) {
        throw new Error("PQ account identity is unavailable.");
      }
      const membershipSignature = await signEd25519Json(
        unlockedPqAccountIdentityPrivateKey,
        "HushLine/HL-PQCHAT-1/device-membership/v1",
        membership,
      );

      async function signedPrekey(kind, value) {
        const proof = {
          device_id: deviceId,
          key: value,
          kind,
          membership_sequence: membershipSequence,
          protocol: "HL-PQCHAT-1",
        };
        return {
          ...value,
          device_signature: await signEd25519Json(
            await importEd25519PrivateKey(deviceSigning.privateJwk),
            "HushLine/HL-PQCHAT-1/prekey-publication/v1",
            proof,
          ),
        };
      }

      const signed = await signedPrekey("signed", {
        classical_public_key: created.publicBundle.signedPrekey.publicKey,
        classical_signature: created.publicBundle.signedPrekey.signature,
        expires_at: pqTimestamp(signedPrekeyExpiresAt),
        key_id: created.publicBundle.signedPrekey.id,
        pq_public_key: created.publicBundle.prekeys[0].kyberPrekey.publicKey,
        pq_signature: created.publicBundle.prekeys[0].kyberPrekey.signature,
      });
      const oneTimePrekeys = [];
      for (const prekey of created.publicBundle.prekeys) {
        oneTimePrekeys.push(
          await signedPrekey("one-time", {
            classical_public_key: prekey.publicKey,
            expires_at: pqTimestamp(membershipExpiresAt),
            key_id: prekey.id,
            pq_public_key: prekey.kyberPrekey.publicKey,
            pq_signature: prekey.kyberPrekey.signature,
          }),
        );
      }
      const publication = {
        device_id: deviceId,
        membership_sequence: membershipSequence,
        one_time_prekeys: oneTimePrekeys,
        protocol: "HL-PQCHAT-1",
        signed_prekey: signed,
      };
      const unlockValue = {
        account_identity_public_key: accountIdentityPublicKey,
        membership,
      };
      return {
        deviceSigningPrivateJwk: deviceSigning.privateJwk,
        enrollment: {
          account_identity_public_key: accountIdentityPublicKey,
          archive: enrollmentArchive,
          membership,
          membership_signature: membershipSignature,
          unlock_signature: await signUnlockValue(
            unlockValue,
            "HushLine/HL-PQCHAT-1/unlock-enrollment/v1",
          ),
        },
        protocolState: created.state,
        publication: {
          publication,
          signature: await signEd25519Json(
            await importEd25519PrivateKey(deviceSigning.privateJwk),
            "HushLine/HL-PQCHAT-1/prekey-publication/v1",
            publication,
          ),
        },
      };
    } finally {
      client.close();
    }
  }

  async function persistPqDeviceState(
    prepared,
    accountId,
    deviceId,
    sourceDocument,
  ) {
    const rawStorageKey = window.crypto.getRandomValues(new Uint8Array(32));
    const storageKey = await window.HushLinePqBrowserState.importStorageKey(
      rawStorageKey,
    );
    const adapter = await window.HushLinePqBrowserState.create({
      accountId,
      deviceId,
      sessionBinding: chatKeySessionId(sourceDocument),
      storageKey,
    });
    const lease = await adapter.acquireLease(tabId);
    try {
      await adapter.initializeSession({
        lease,
        sessionId: `device:${deviceId}`,
        state: prepared.protocolState,
        stateDigest: await sha256Hex(
          textEncoder.encode(canonicalStringify(prepared.protocolState)),
        ),
      });
    } finally {
      await adapter.releaseLease(lease);
      adapter.lock();
    }
    return bytesToBase64Url(rawStorageKey);
  }

  function announcePqDeviceState(status, accountId = null, deviceId = null) {
    pqDeviceState.status = status;
    pqDeviceState.accountId = accountId;
    pqDeviceState.deviceId = deviceId;
    document.dispatchEvent(
      new CustomEvent("hushline:pq-device-state", {
        detail: { accountId, deviceId, status },
      }),
    );
  }

  function restorePqDeviceState(sourceDocument = document) {
    try {
      const stored = JSON.parse(
        window.sessionStorage.getItem(pqDeviceSessionStorageKey) || "null",
      );
      if (
        stored?.sessionId !== chatKeySessionId(sourceDocument) ||
        typeof stored.accountId !== "string" ||
        typeof stored.deviceId !== "string" ||
        typeof stored.storageKey !== "string" ||
        !stored.deviceSigningPrivateJwk
      ) {
        return null;
      }
      announcePqDeviceState("ready", stored.accountId, stored.deviceId);
      return stored;
    } catch (error) {
      return null;
    }
  }

  async function enrollPqDevice(prepared, sourceDocument = document) {
    if (!prepared?.enrollment || !prepared?.publication) {
      throw new Error("PQ device enrollment material is unavailable.");
    }
    const enrolled = await postPqDeviceJson(
      "/api/pq/devices",
      prepared.enrollment,
      sourceDocument,
    );
    const deviceId = enrolled?.device?.membership?.device_id;
    const accountId = enrolled?.device?.membership?.account_id;
    if (!deviceId || !accountId) {
      throw new Error("PQ device enrollment response is incomplete.");
    }
    await postPqDeviceJson(
      `/api/pq/devices/${encodeURIComponent(deviceId)}/prekeys`,
      prepared.publication,
      sourceDocument,
    );
    const storageKey = await persistPqDeviceState(
      prepared,
      accountId,
      deviceId,
      sourceDocument,
    );
    window.sessionStorage.setItem(
      pqDeviceSessionStorageKey,
      JSON.stringify({
        accountId,
        deviceId,
        deviceSigningPrivateJwk: prepared.deviceSigningPrivateJwk,
        sessionId: chatKeySessionId(sourceDocument),
        storageKey,
      }),
    );
    announcePqDeviceState("ready", accountId, deviceId);
    return { accountId, deviceId };
  }

  async function ensurePqDeviceEnrollment(chatKey, sourceDocument = document) {
    if (restorePqDeviceState(sourceDocument)) {
      return true;
    }
    const browserState = window.HushLinePqBrowserState;
    if (
      !window.HushLinePqProtocol?.createWorkerClient ||
      !browserState?.create ||
      !unlockedChatSigningPrivateKey ||
      !unlockedPqAccountRoot ||
      !unlockedPqAccountIdentityPrivateKey
    ) {
      announcePqDeviceState("unavailable");
      return false;
    }
    announcePqDeviceState("enrolling");
    try {
      const account = await postPqDeviceJson(
        "/api/pq/account",
        {},
        sourceDocument,
      );
      const prepared = await preparePqDeviceEnrollment(account, chatKey);
      await enrollPqDevice(prepared, sourceDocument);
      return true;
    } catch (error) {
      try {
        window.sessionStorage.removeItem(pqDeviceSessionStorageKey);
      } catch (storageError) {
        // The recoverable state below remains available without storage.
      }
      announcePqDeviceState("recoverable-error");
      return false;
    }
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
    lockIfAuthenticationEnded(response);
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
    if (!chatKey) {
      return chatKey;
    }

    let privateKeyBundle = null;
    try {
      privateKeyBundle = await decryptPrivateKeyBundle(chatKey, password);
      const needsSigningKey =
        !chatKey.public_signing_key ||
        !privateKeyBundle.signing_private_jwk;
      const needsAccountRoot = !privateKeyBundle.pq_account_root;
      const needsPqAccountIdentity =
        !privateKeyBundle.pq_account_identity_private_jwk;
      if (!needsSigningKey && !needsAccountRoot && !needsPqAccountIdentity) {
        return chatKey;
      }
      const signingKeyMaterial = needsSigningKey
        ? await createSigningKeyMaterial()
        : null;
      const pqAccountIdentity = needsPqAccountIdentity
        ? await createEd25519KeyMaterial()
        : null;
      const upgradedPrivateKeyBundle = {
        ...privateKeyBundle,
        pq_account_root:
          privateKeyBundle.pq_account_root ||
          createPqAccountRoot(),
        pq_account_identity_private_jwk:
          pqAccountIdentity?.privateJwk ||
          privateKeyBundle.pq_account_identity_private_jwk,
        signing_private_jwk:
          signingKeyMaterial?.signingPrivateJwk ||
          privateKeyBundle.signing_private_jwk,
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
          public_signing_key: signingKeyMaterial
            ? JSON.stringify(signingKeyMaterial.publicSigningJwk)
            : chatKey.public_signing_key,
          recovery_state: "available",
          ...wrapped,
        }),
      });
      lockIfAuthenticationEnded(response);
      if (!response.ok) {
        throw new Error("Chat key capability upgrade failed.");
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
    let chatKey = await fetchChatKey(chatKeyUrl);
    if (chatKey) {
      const unlocked = await unlockFromPassword(
        chatKey,
        password,
        sourceDocument,
      );
      if (unlocked) {
        try {
          chatKey = await upgradeChatKeySigningCapability(
            chatKey,
            password,
            chatKeyUrl,
            sourceDocument,
          );
        } catch (error) {
          return unlocked;
        }
      }
      if (unlocked) {
        await ensurePqDeviceEnrollment(chatKey, sourceDocument);
      }
      return unlocked;
    }
    chatKey = await provisionChatKey(chatKeyUrl, password, sourceDocument);
    await ensurePqDeviceEnrollment(chatKey, sourceDocument);
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

  async function callPqArchiveWithUnlockedRoot(
    operation,
    args,
    options = {},
  ) {
    if (!unlockedPqAccountRoot) {
      const error = new Error("PQ archive key is locked.");
      error.code = "AUTHENTICATION_FAILED";
      throw error;
    }
    const client =
      options.client || window.HushLinePqProtocol?.createWorkerClient?.();
    if (!client || typeof client[operation] !== "function") {
      const error = new Error("PQ archive capability is unavailable.");
      error.code = "CAPABILITY_UNAVAILABLE";
      throw error;
    }
    try {
      return await client[operation]({
        ...args,
        accountRoot: unlockedPqAccountRoot,
      });
    } finally {
      if (!options.client) client.close();
    }
  }

  function createPqArchiveEpoch(args, options) {
    return callPqArchiveWithUnlockedRoot(
      "createArchiveEpoch",
      args,
      options,
    );
  }

  function openPqArchive(args, options) {
    return callPqArchiveWithUnlockedRoot("archiveOpen", args, options);
  }

  async function revokePqDevice(deviceId, sourceDocument = document) {
    const chatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
    if (!chatKey || !(await restoreUnlockedChatKey(chatKey))) {
      throw new Error("The chat key is locked.");
    }
    let currentDevice = restorePqDeviceState(sourceDocument);
    if (!currentDevice) {
      if (!(await ensurePqDeviceEnrollment(chatKey, sourceDocument))) {
        throw new Error("PQ device enrollment failed.");
      }
      currentDevice = restorePqDeviceState(sourceDocument);
    }
    if (!currentDevice || !unlockedPqAccountIdentityPrivateKey) {
      throw new Error("PQ device revocation capability is unavailable.");
    }

    const account = await postPqDeviceJson(
      "/api/pq/account",
      {},
      sourceDocument,
    );
    const nextEpoch =
      Math.max(0, ...(account.archive_epochs || []).map((value) => value.epoch)) +
      1;
    const rotated = await createPqArchiveEpoch({
      accountId: account.account_id,
      epoch: nextEpoch,
    });
    const archive = {
      encrypted_private_key: rotated.encryptedPrivateKey,
      epoch: rotated.epoch,
      public_key: rotated.publicKey,
    };
    const revocation = {
      account_id: account.account_id,
      archive_epoch: archive.epoch,
      archive_public_key_sha256: await sha256Hex(
        base64UrlToBytes(archive.public_key),
      ),
      device_id: deviceId,
      membership_sequence: account.membership_sequence + 1,
      revoked_at: pqTimestamp(new Date()),
      status: "revoked",
    };
    const payload = {
      archive,
      revocation,
      signature: await signEd25519Json(
        unlockedPqAccountIdentityPrivateKey,
        "HushLine/HL-PQCHAT-1/device-revocation/v1",
        revocation,
      ),
      unlock_signature: await signUnlockValue(
        { archive, revocation },
        "HushLine/HL-PQCHAT-1/unlock-revocation/v1",
      ),
    };
    const result = await postPqDeviceJson(
      `/api/pq/devices/${encodeURIComponent(deviceId)}/revoke`,
      payload,
      sourceDocument,
    );

    clearChatKeyMaterial();
    return { ...result, reenrolled: false };
  }

  async function pqJson(path, { body, deviceId, method = "GET" } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = csrfTokenFromDocument();
    }
    if (deviceId) {
      headers["X-Hushline-Device-ID"] = deviceId;
    }
    const response = await fetch(new URL(path, window.location.origin), {
      method,
      credentials: "same-origin",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    lockIfAuthenticationEnded(response);
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      // The stable error below does not expose a remote response body.
    }
    if (!response.ok) {
      const requestError = new Error(payload?.error || "PQ request failed.");
      requestError.code = payload?.error || "INTERNAL_ERROR";
      throw requestError;
    }
    return payload;
  }

  async function ensurePqDeliveryDevice({ verifyCurrent = false } = {}) {
    const chatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
    if (!chatKey || !(await restoreUnlockedChatKey(chatKey))) {
      throw new Error("The chat key is locked.");
    }
    let device = restorePqDeviceState();
    if (device && verifyCurrent) {
      try {
        await pqJson(
          `/api/pq/accounts/${encodeURIComponent(device.accountId)}/devices`,
          { deviceId: device.deviceId },
        );
      } catch (error) {
        if (error?.code !== "STALE_MEMBERSHIP") {
          throw error;
        }
        await clearPqDeviceMaterial();
        device = null;
      }
    }
    if (!device) {
      if (!(await ensurePqDeviceEnrollment(chatKey))) {
        throw new Error("PQ device enrollment failed.");
      }
      device = restorePqDeviceState();
    }
    if (!device) {
      throw new Error("PQ device state is unavailable.");
    }
    return device;
  }

  async function openPqDeliveryState(device) {
    const storageKey = await window.HushLinePqBrowserState.importStorageKey(
      base64UrlToBytes(device.storageKey),
    );
    return window.HushLinePqBrowserState.create({
      accountId: device.accountId,
      deviceId: device.deviceId,
      sessionBinding: chatKeySessionId(),
      storageKey,
    });
  }

  function uuidBytes(value) {
    const hex = value.replaceAll("-", "");
    if (!/^[0-9a-f]{32}$/u.test(hex)) {
      throw new Error("Invalid message identifier.");
    }
    return Uint8Array.from(
      hex.match(/../gu).map((byte) => Number.parseInt(byte, 16)),
    );
  }

  function bytesUuid(bytes) {
    const hex = Array.from(bytes, (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  async function prekeyClaimId(messageId, deviceId) {
    const digest = new Uint8Array(
      await window.crypto.subtle.digest(
        "SHA-1",
        joinBytes(uuidBytes(messageId), textEncoder.encode(deviceId)),
      ),
    );
    const value = digest.slice(0, 16);
    value[6] = (value[6] & 0x0f) | 0x50;
    value[8] = (value[8] & 0x3f) | 0x80;
    return bytesUuid(value);
  }

  function pqCopyContext({
    account,
    conversationId,
    deviceId,
    keyVersion,
    messageId,
    purpose,
    senderDevice,
  }) {
    return {
      account_recipient_id: account.account_id,
      archive_epoch: purpose === "archive" ? account.archive.epoch : 0,
      capability_offer: ["HL-PQCHAT-1"],
      capability_selection: "HL-PQCHAT-1",
      conversation_id: conversationId,
      device_recipient_id:
        purpose === "archive"
          ? "00000000-0000-0000-0000-000000000000"
          : deviceId,
      key_version: keyVersion,
      message_id: messageId,
      protocol: "HL-PQCHAT-1",
      purpose,
      recipient_membership_sequence: account.membership_sequence,
      sender_account_id: senderDevice.membership.account_id,
      sender_device_id: senderDevice.membership.device_id,
      sender_membership_sequence:
        senderDevice.membership.membership_sequence,
      suite:
        purpose === "archive"
          ? "MLKEM768-X25519-HKDF-SHA256-AES256GCM"
          : "SIGNAL-PQXDH3-KYBER1024-SPQR1",
    };
  }

  function pqCopyOrder(left, right) {
    return [
      left.context.purpose,
      left.context.account_recipient_id,
      left.context.device_recipient_id,
    ]
      .join(":")
      .localeCompare(
        [
          right.context.purpose,
          right.context.account_recipient_id,
          right.context.device_recipient_id,
        ].join(":"),
      );
  }

  async function pqManifestCopy(copy) {
    const ciphertextBytes = base64UrlToBytes(copy.ciphertext);
    return {
      account_recipient_id: copy.context.account_recipient_id,
      archive_epoch: copy.context.archive_epoch,
      ciphertext_length: ciphertextBytes.length,
      ciphertext_sha256: await sha256Hex(ciphertextBytes),
      context_sha256: await sha256Hex(
        textEncoder.encode(canonicalStringify(copy.context)),
      ),
      device_recipient_id: copy.context.device_recipient_id,
      key_version: copy.context.key_version,
      purpose: copy.context.purpose,
    };
  }

  async function transmitPqOutbox(
    adapter,
    lease,
    sessionId,
    logicalMessageId,
    endpoint,
    extraHeaders,
  ) {
    return adapter.deliverOutbox({
      lease,
      sessionId,
      logicalMessageId,
      transmit: async (exactRequestBytes) => {
        const response = await fetch(endpoint, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": csrfTokenFromDocument(),
            ...(extraHeaders || {}),
          },
          body: exactRequestBytes,
        });
        lockIfAuthenticationEnded(response);
        const result = await response.json();
        if (!response.ok) {
          const sendError = new Error(result?.error || "PQ delivery failed.");
          sendError.code = result?.error || "INTERNAL_ERROR";
          throw sendError;
        }
        return result;
      },
    });
  }

  async function sendPqMessage({
    accountIds,
    conversationId,
    endpoint,
    extraHeaders = {},
    plaintext,
  }) {
    if (
      !Array.isArray(accountIds) ||
      ![1, 2].includes(accountIds.length) ||
      typeof plaintext !== "string" ||
      !plaintext
    ) {
      throw new Error("PQ delivery input is incomplete.");
    }
    const device = await ensurePqDeliveryDevice();
    accountIds = [...new Set([device.accountId, ...accountIds])];
    if (accountIds.length !== 2) {
      throw new Error("PQ delivery requires two distinct participant accounts.");
    }
    const adapter = await openPqDeliveryState(device);
    const lease = await adapter.acquireLease(tabId);
    const client = window.HushLinePqProtocol.createWorkerClient();
    const sessionId = `conversation:${conversationId}`;
    let staleMembership = false;
    try {
      const pending = (await adapter.listOutbox()).find(
        (item) => item.sessionId === sessionId,
      );
      if (pending) {
        const response = await transmitPqOutbox(
          adapter,
          lease,
          sessionId,
          pending.logicalMessageId,
          endpoint,
          extraHeaders,
        );
        return { ...response, retried: true };
      }

      const accounts = await Promise.all(
        [...new Set(accountIds)].sort().map((accountId) =>
          pqJson(`/api/pq/accounts/${encodeURIComponent(accountId)}/devices`, {
            deviceId: device.deviceId,
          }),
        ),
      );
      if (
        accounts.length !== 2 ||
        !(await Promise.all(accounts.map((account) => verifyPqArchive(account)))).every(
          Boolean,
        )
      ) {
        throw new Error("PQ participant membership could not be verified.");
      }
      const senderAccount = accounts.find(
        (account) => account.account_id === device.accountId,
      );
      const senderDevice = senderAccount?.devices.find(
        (candidate) =>
          candidate.membership.device_id === device.deviceId,
      );
      if (!senderAccount || !senderDevice) {
        throw new Error("PQ sender membership is unavailable.");
      }

      let current;
      try {
        current = await adapter.loadSession(sessionId);
      } catch (error) {
        if (error?.code !== "STATE_MISSING") throw error;
        const initialState = { sessions: {}, v: 1 };
        await adapter.initializeSession({
          lease,
          sessionId,
          state: initialState,
          stateDigest: await sha256Hex(
            textEncoder.encode(canonicalStringify(initialState)),
          ),
        });
        current = await adapter.loadSession(sessionId);
      }
      const deviceSeed = await adapter.loadSession(`device:${device.deviceId}`);
      const nextState = structuredClone(current.state);
      const messageId = window.crypto.randomUUID();
      const createdAt = pqTimestamp(new Date());
      const copies = [];

      for (const account of accounts) {
        const archiveContext = pqCopyContext({
          account,
          conversationId,
          deviceId: null,
          keyVersion: account.archive.epoch,
          messageId,
          purpose: "archive",
          senderDevice,
        });
        copies.push({
          context: archiveContext,
          ciphertext: await client.archiveSeal({
            context: archiveContext,
            plaintext,
            publicKey: account.archive.public_key,
          }),
        });

        for (const recipientDevice of account.devices) {
          const recipientDeviceId = recipientDevice.membership.device_id;
          if (recipientDeviceId === device.deviceId) continue;
          let ratchetState = nextState.sessions[recipientDeviceId];
          if (!ratchetState) {
            const claimId = await prekeyClaimId(messageId, recipientDeviceId);
            const claim = await pqJson(
              `/api/pq/accounts/${encodeURIComponent(account.account_id)}/devices/${encodeURIComponent(recipientDeviceId)}/prekeys/claim`,
              {
                body: { claim_id: claimId },
                deviceId: device.deviceId,
                method: "POST",
              },
            );
            if (
              claim?.device?.membership?.device_id !== recipientDeviceId ||
              claim.device.membership_sha256 !==
                recipientDevice.membership_sha256
            ) {
              throw new Error("PQ prekey claim changed recipient membership.");
            }
            const established =
              await window.HushLinePqProtocol.beginVerifiedSession({
                client,
                expectedAccountId: account.account_id,
                expectedIdentityPublicKey: account.identity_public_key,
                localState: deviceSeed.state,
                minimumMembershipSequence:
                  recipientDevice.membership.membership_sequence,
                prekeyClaim: claim,
            });
            ratchetState = established.state;
          }
          const transportContext = pqCopyContext({
            account,
            conversationId,
            deviceId: recipientDeviceId,
            keyVersion: recipientDevice.membership.signed_prekey_id,
            messageId,
            purpose: "transport",
            senderDevice,
          });
          const encrypted = await client.ratchetEncrypt({
            context: transportContext,
            plaintext,
            state: ratchetState,
          });
          nextState.sessions[recipientDeviceId] = encrypted.state;
          copies.push({
            context: transportContext,
            ciphertext: encrypted.ciphertext,
          });
        }
      }
      copies.sort(pqCopyOrder);
      const manifest = {
        capability_offer: ["HL-PQCHAT-1"],
        capability_selection: "HL-PQCHAT-1",
        conversation_id: conversationId,
        copies: await Promise.all(copies.map(pqManifestCopy)),
        created_at: createdAt,
        message_id: messageId,
        protocol: "HL-PQCHAT-1",
        sender_account_id: device.accountId,
        sender_device_id: device.deviceId,
        sender_membership_sha256: senderDevice.membership_sha256,
      };
      const signingKey = await importEd25519PrivateKey(
        device.deviceSigningPrivateJwk,
      );
      const signature = await signEd25519Json(
        signingKey,
        "HushLine/HL-PQCHAT-1/manifest-signature/v1",
        manifest,
      );
      const request = { copies, manifest, signature };
      const exactRequestBytes = textEncoder.encode(canonicalStringify(request));
      const idempotencyKey = await sha256Hex(
        joinBytes(
          textEncoder.encode(canonicalStringify(manifest)),
          base64UrlToBytes(signature),
        ),
      );
      await adapter.commitSend({
        afterStateDigest: await sha256Hex(
          textEncoder.encode(canonicalStringify(nextState)),
        ),
        beforeStateDigest: current.stateDigest,
        exactRequestBytes,
        expectedRevision: current.revision,
        idempotencyKey,
        lease,
        logicalMessageId: messageId,
        nextState,
        sessionId,
      });
      const response = await transmitPqOutbox(
        adapter,
        lease,
        sessionId,
        messageId,
        endpoint,
        extraHeaders,
      );
      return response;
    } catch (error) {
      if (error?.code !== "STALE_MEMBERSHIP") {
        throw error;
      }
      staleMembership = true;
    } finally {
      client.close();
      await adapter.releaseLease(lease);
      adapter.lock();
    }
    if (staleMembership) {
      await clearPqDeviceMaterial();
      const recoveryChatKey = await fetchChatKey(chatKeyUrlFromCurrentOrigin());
      if (
        !recoveryChatKey ||
        !(await restoreUnlockedChatKey(recoveryChatKey)) ||
        !(await ensurePqDeviceEnrollment(recoveryChatKey))
      ) {
        throw new Error("PQ device re-establishment failed.");
      }
      return sendPqMessage({
        accountIds,
        conversationId,
        endpoint,
        extraHeaders,
        plaintext,
      });
    }
    throw new Error("PQ delivery did not complete.");
  }

  async function clearPqDeviceMaterial() {
    let clearing;
    try {
      clearing = window.HushLinePqBrowserState?.clearAll?.();
    } catch (error) {
      // Continue locking even when browser storage cannot be opened.
    }
    try {
      window.sessionStorage.removeItem(pqDeviceSessionStorageKey);
    } catch (error) {
      // Storage denial cannot prevent in-memory key cleanup.
    }
    announcePqDeviceState("unavailable");
    try {
      await clearing;
    } catch (error) {
      // Removing the wrapped session key still locks inaccessible stored state.
    }
  }

  function clearChatKeyMaterial({ broadcast = true } = {}) {
    if (broadcast) {
      postChatKeyBroadcast({ type: "lock-chat-key" });
    }
    void clearPqDeviceMaterial();
    const hadUnlockedKey = Boolean(
      unlockedChatPrivateKey ||
        unlockedChatSigningPrivateKey ||
        unlockedPqAccountRoot ||
        unlockedPqAccountIdentityPrivateKey ||
        unlockedPqAccountIdentityPublicKey ||
        state.status === "unlocked",
    );
    forgetUnlockedPrivateJwk();
    unlockedChatPrivateKey = null;
    unlockedChatSigningPrivateKey = null;
    unlockedPqAccountRoot = null;
    unlockedPqAccountIdentityPrivateKey = null;
    unlockedPqAccountIdentityPublicKey = null;
    state.status = "empty";
    state.keyVersion = null;
    state.lastError = null;
    if (hadUnlockedKey) {
      updateConversationLockedAfterKeyClear();
    }
  }

  function lockIfAuthenticationEnded(response) {
    if (!response?.redirected) {
      return false;
    }
    const path = new URL(response.url, window.location.origin).pathname;
    if (path !== "/login" && path !== "/verify-2fa-login") {
      return false;
    }
    clearChatKeyMaterial();
    const error = new Error("Authenticated session ended.");
    error.code = "AUTHENTICATION_FAILED";
    throw error;
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

  function jsonFromScript(id, fallback, sourceDocument = document) {
    const script = sourceDocument.getElementById(id);
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

  async function pqConversationDecryptionContext() {
    const root = document.getElementById("conversation-chat");
    const device = await ensurePqDeliveryDevice({ verifyCurrent: true });
    const participantAccounts = jsonFromScript(
      "conversationParticipantPqAccounts",
      [],
    );
    const ownParticipantAccount = participantAccounts.find(
      (account) => account.account_id === device.accountId,
    );
    if (!root?.dataset.conversationPublicId || !ownParticipantAccount) {
      throw new Error("Protected conversation metadata is unavailable.");
    }
    const [ownAccountState, ownAccount] = await Promise.all([
      pqJson(
        `/api/pq/accounts/${encodeURIComponent(ownParticipantAccount.account_id)}/devices`,
        { deviceId: device.deviceId },
      ),
      pqJson("/api/pq/account", { body: {}, method: "POST" }),
    ]);
    return {
      accountStates: [ownAccountState],
      conversationId: root.dataset.conversationPublicId,
      device,
      ownAccount,
    };
  }

  async function decryptPqConversationMessage(messagePublicId, context) {
    const { accountStates, conversationId, device, ownAccount } = context;
    const delivery = await pqJson(
      `/conversation/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messagePublicId)}`,
      { deviceId: device.deviceId },
    );
    const senderAccount = accountStates.find(
      (account) => account.account_id === delivery.manifest?.sender_account_id,
    );
    const activeSenderDevice = senderAccount?.devices.find(
      (candidate) =>
        candidate.membership.device_id ===
        delivery.manifest?.sender_device_id,
    );
    const senderDevice = activeSenderDevice || delivery.sender?.device;
    const senderIdentityPublicKey = activeSenderDevice
      ? senderAccount?.identity_public_key
      : delivery.sender?.account_identity_public_key;
    if (
      !senderDevice ||
      !(await verifyPqMembership(
        senderIdentityPublicKey,
        senderDevice,
        0,
        delivery.manifest.sender_account_id,
        true,
      )) ||
      senderDevice.membership_sha256 !==
        delivery.manifest.sender_membership_sha256 ||
      !(await verifyEd25519Json(
        senderDevice.membership.device_signing_public_key,
        delivery.signature,
        "HushLine/HL-PQCHAT-1/manifest-signature/v1",
        delivery.manifest,
      ))
    ) {
      throw new Error("Protected message signature is invalid.");
    }
    const archiveCopy = delivery.copies.find(
      (candidate) =>
        candidate.context?.purpose === "archive" &&
        candidate.context.account_recipient_id === device.accountId,
    );
    const manifestCopy = delivery.manifest.copies.find(
      (candidate) =>
        candidate.purpose === "archive" &&
        candidate.account_recipient_id === device.accountId,
    );
    if (
      !archiveCopy ||
      !manifestCopy ||
      manifestCopy.context_sha256 !==
        (await sha256Hex(
          textEncoder.encode(canonicalStringify(archiveCopy.context)),
        )) ||
      manifestCopy.ciphertext_sha256 !==
        (await sha256Hex(base64UrlToBytes(archiveCopy.ciphertext)))
    ) {
      throw new Error("Protected archive copy is invalid.");
    }
    const archiveEpoch = ownAccount.archive_epochs.find(
      (epoch) => epoch.epoch === archiveCopy.context.archive_epoch,
    );
    if (!archiveEpoch) {
      throw new Error("Protected archive key is unavailable.");
    }
    return openPqArchive({
      accountId: device.accountId,
      ciphertext: archiveCopy.ciphertext,
      context: archiveCopy.context,
      encryptedPrivateKey: archiveEpoch.encrypted_private_key,
      epoch: archiveEpoch.epoch,
      publicKey: archiveEpoch.public_key,
    });
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

    const response = await fetch(window.location.href, {
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        Accept: "text/html",
        "X-Hushline-Conversation-Refresh": "true",
      },
    });
    lockIfAuthenticationEnded(response);
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

    await decryptConversationMessages(nextDocument);
    const shouldScroll = scroll || conversationThreadIsNearBottom();
    const previousScrollTop = thread.scrollTop;
    currentCopies.textContent = nextCopies.textContent;
    thread.replaceChildren(
      ...Array.from(nextThread.children).map((child) => {
        return document.importNode(child, true);
      }),
    );
    thread.scrollTop = shouldScroll ? thread.scrollHeight : previousScrollTop;
    return true;
  }

  async function decryptConversationMessages(sourceDocument = document) {
    const copies = jsonFromScript(
      "conversationMessageCopies",
      [],
      sourceDocument,
    );
    const pqContext = copies.some((copy) => copy.pq_message_id)
      ? pqConversationDecryptionContext()
      : null;
    for (const copy of copies) {
      if (!copy.encrypted_payload && !copy.pq_message_id) {
        continue;
      }

      const messageElement = sourceDocument.querySelector(
        `[data-conversation-message-id="${copy.message_id}"] .conversation-message-body`,
      );
      const messageContainer = sourceDocument.querySelector(
        `[data-conversation-message-id="${copy.message_id}"]`,
      );
      const messageTimeElement = messageContainer?.querySelector(
        "[data-conversation-message-time]",
      );
      if (!messageElement) {
        continue;
      }

      try {
        if (copy.pq_message_id) {
          const plaintext = await decryptPqConversationMessage(
            copy.pq_message_id,
            await pqContext,
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
          continue;
        }
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
    if (conversationSubmitInFlight) {
      return;
    }

    conversationSubmitInFlight = true;
    setConversationComposeEnabled(false);
    setConversationStatus("Encrypting reply...");
    try {
      if (root.dataset.protocolVersion === "1") {
        const participantAccounts = jsonFromScript(
          "conversationParticipantPqAccounts",
          [],
        );
        if (participantAccounts.length !== 2) {
          throw new Error("Protected participant state is unavailable.");
        }
        const timestamp = new Date().toISOString();
        await sendPqMessage({
          accountIds: participantAccounts.map((account) => account.account_id),
          conversationId: root.dataset.conversationPublicId || "",
          endpoint: root.dataset.messageUrl,
          plaintext: JSON.stringify({
            content: plaintext,
            created_at: timestamp,
          }),
        });
        body.value = "";
        resizeConversationComposer();
        await refreshConversationMessages({ force: true, scroll: true });
        setConversationStatus("Reply sent.");
        return;
      }
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
      lockIfAuthenticationEnded(response);
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
    } finally {
      conversationSubmitInFlight = false;
      setConversationComposeEnabled(root.dataset.canCompose === "true");
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
      const response = await fetch(root.dataset.presenceUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRFToken": conversationCsrfToken() || "",
        },
      });
      lockIfAuthenticationEnded(response);
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

  function bindPqDeviceRevocation() {
    document
      .querySelectorAll("[data-pq-revoke-device-id]")
      .forEach((button) => {
        if (button.dataset.bound === "true") {
          return;
        }
        button.dataset.bound = "true";
        button.addEventListener("click", async () => {
          if (
            !window.confirm(
              "Revoke this browser and rotate protection for future messages? Previously copied messages and keys cannot be retracted.",
            )
          ) {
            return;
          }
          const status = document.getElementById("pq-device-revocation-status");
          const buttons = Array.from(
            document.querySelectorAll("[data-pq-revoke-device-id]"),
          );
          buttons.forEach((candidate) => {
            candidate.disabled = true;
          });
          if (status) {
            status.textContent = "Revoking browser and rotating future keys...";
          }
          try {
            await revokePqDevice(button.dataset.pqRevokeDeviceId);
            if (status) {
              status.textContent =
                "Browser revoked and future keys rotated. Account sessions were signed out; log in again to re-establish protected chat.";
            }
          } catch (error) {
            if (status) {
              status.textContent =
                "The browser could not be revoked. Refresh the page before trying again.";
            }
          } finally {
            buttons.forEach((candidate) => {
              candidate.disabled = false;
            });
          }
        });
      });
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

  function scheduleAuthenticatedSessionLock() {
    if (sessionLockTimer !== null) {
      window.clearTimeout(sessionLockTimer);
      sessionLockTimer = null;
    }
    const maxAgeMs = Number.parseInt(
      document.body?.dataset.authSessionMaxAgeMs || "",
      10,
    );
    if (
      document.body?.dataset.authenticated !== "true" ||
      !Number.isFinite(maxAgeMs) ||
      maxAgeMs <= 0
    ) {
      return;
    }
    sessionLockTimer = window.setTimeout(clearChatKeyMaterial, maxAgeMs);
  }

  function bindPage() {
    scheduleAuthenticatedSessionLock();
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
    bindPqDeviceRevocation();
    document
      .querySelector("form[action*='password-reset']")
      ?.addEventListener("submit", clearChatKeyMaterial);
    bindChatKeyCleanupTriggers();
    bindConversation();
  }

  window.HushLineChatKeys = {
    clear: clearChatKeyMaterial,
    createPqArchiveEpoch,
    fetchChatKey,
    get state() {
      return { ...state };
    },
    get pqDeviceState() {
      return { ...pqDeviceState };
    },
    decryptChatCiphertext,
    encryptForPublicKey,
    enrollPqDevice,
    ensureChatKeyUnlockedAfterAuth,
    ensurePqDeviceEnrollment,
    openPqArchive,
    provisionChatKey,
    revokePqDevice,
    rewrapForPasswordChange,
    sendPqMessage,
    signingPrivateKeyForChatKey,
    unlockFromPassword,
    verifyPqMembership,
    verifyPqArchive,
    verifyPqPrekeyClaim,
  };

  document.addEventListener("DOMContentLoaded", function () {
    bindPage();
  });
})();

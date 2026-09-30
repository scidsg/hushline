(function () {
  "use strict";

  const DATABASE_NAME = "hushline-pq-browser-state-v1";
  const DATABASE_VERSION = 1;
  const RECORDS_STORE = "encrypted-records";
  const LEASES_STORE = "leases";
  const CHANNEL_NAME = "hushline:pq-browser-state";
  const ENVELOPE_VERSION = 1;
  const DEFAULT_LEASE_DURATION_MS = 15000;
  const MAX_REQUEST_BYTES = 55000000;
  const MAX_OUTBOX_RECORDS = 32;
  const MAX_SENT_RECORDS = 100000;
  const MAX_RECEIPTS_PER_DEVICE = 100000;
  const MAX_SKIPPED_KEYS = 2000;
  const MAX_PENDING_TRANSITIONS = 32;
  const SHA256_HEX = /^[0-9a-f]{64}$/;
  const browserGlobal = globalThis;
  const textEncoder = new TextEncoder();
  const textDecoder = new TextDecoder();
  const activeAdapters = new Set();

  class PqBrowserStateError extends Error {
    constructor(code, message) {
      super(message);
      this.name = "PqBrowserStateError";
      this.code = code;
    }
  }

  function fail(code, message) {
    throw new PqBrowserStateError(code, message);
  }

  function requireText(value, label) {
    if (typeof value !== "string" || !value) {
      fail("INVALID_INPUT", `${label} is required.`);
    }
    return value;
  }

  function requireDigest(value, label) {
    if (typeof value !== "string" || !SHA256_HEX.test(value)) {
      fail("INVALID_INPUT", `${label} must be a SHA-256 digest.`);
    }
    return value;
  }

  function requireRevision(value) {
    if (!Number.isSafeInteger(value) || value < 0) {
      fail("INVALID_INPUT", "State revision must be a non-negative integer.");
    }
    return value;
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

  function bytesToBase64Url(bytes) {
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return browserGlobal
      .btoa(binary)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/u, "");
  }

  function base64UrlToBytes(value) {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    const binary = browserGlobal.atob(
      base64.padEnd(Math.ceil(base64.length / 4) * 4, "="),
    );
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  }

  function encodePrivateValue(value) {
    return textEncoder.encode(
      JSON.stringify(value, (_key, item) => {
        if (item instanceof Uint8Array) {
          return { $hushlineBytes: bytesToBase64Url(item) };
        }
        if (item instanceof ArrayBuffer) {
          return { $hushlineBytes: bytesToBase64Url(new Uint8Array(item)) };
        }
        return item;
      }),
    );
  }

  function decodePrivateValue(bytes) {
    return JSON.parse(textDecoder.decode(bytes), (_key, item) => {
      if (
        item &&
        typeof item === "object" &&
        Object.keys(item).length === 1 &&
        typeof item.$hushlineBytes === "string"
      ) {
        return base64UrlToBytes(item.$hushlineBytes);
      }
      return item;
    });
  }

  async function sha256Hex(value) {
    const bytes =
      typeof value === "string" ? textEncoder.encode(value) : value;
    const digest = new Uint8Array(
      await browserGlobal.crypto.subtle.digest("SHA-256", bytes),
    );
    return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join(
      "",
    );
  }

  function requestResult(request) {
    return new Promise((resolve, reject) => {
      request.addEventListener("success", () => resolve(request.result), {
        once: true,
      });
      request.addEventListener("error", () => reject(request.error), {
        once: true,
      });
    });
  }

  function transactionResult(transaction) {
    return new Promise((resolve, reject) => {
      transaction.addEventListener("complete", resolve, { once: true });
      transaction.addEventListener(
        "abort",
        () => reject(transaction.error || new Error("Transaction aborted.")),
        { once: true },
      );
      transaction.addEventListener(
        "error",
        () => reject(transaction.error || new Error("Transaction failed.")),
        { once: true },
      );
    });
  }

  async function runTransaction(database, storeNames, mode, operation) {
    const transaction = database.transaction(storeNames, mode);
    const completion = transactionResult(transaction);
    try {
      const stores = Object.fromEntries(
        storeNames.map((storeName) => [
          storeName,
          transaction.objectStore(storeName),
        ]),
      );
      const result = await operation(stores);
      await completion;
      return result;
    } catch (error) {
      try {
        transaction.abort();
      } catch (abortError) {
        // The transaction may have completed between the failure and abort.
      }
      try {
        await completion;
      } catch (transactionError) {
        // Preserve the stable application error raised by the operation.
      }
      throw error;
    }
  }

  function openDatabase(indexedDb) {
    return new Promise((resolve, reject) => {
      let request;
      try {
        request = indexedDb.open(DATABASE_NAME, DATABASE_VERSION);
      } catch (error) {
        reject(error);
        return;
      }
      request.addEventListener(
        "upgradeneeded",
        () => {
          const database = request.result;
          if (!database.objectStoreNames.contains(RECORDS_STORE)) {
            const records = database.createObjectStore(RECORDS_STORE, {
              keyPath: "id",
            });
            records.createIndex("partition", "partition", { unique: false });
            records.createIndex("partitionType", ["partition", "type"], {
              unique: false,
            });
          }
          if (!database.objectStoreNames.contains(LEASES_STORE)) {
            database.createObjectStore(LEASES_STORE, { keyPath: "id" });
          }
        },
        { once: true },
      );
      request.addEventListener("success", () => resolve(request.result), {
        once: true,
      });
      request.addEventListener("error", () => reject(request.error), {
        once: true,
      });
      request.addEventListener(
        "blocked",
        () => reject(new Error("IndexedDB upgrade was blocked.")),
        { once: true },
      );
    });
  }

  function storageError(error) {
    if (error instanceof PqBrowserStateError) {
      return error;
    }
    return new PqBrowserStateError(
      "STORAGE_UNAVAILABLE",
      "Encrypted browser state is unavailable.",
    );
  }

  function assertStorageKey(storageKey) {
    if (
      !storageKey ||
      storageKey.type !== "secret" ||
      storageKey.extractable !== false ||
      storageKey.algorithm?.name !== "AES-GCM" ||
      !storageKey.usages?.includes("encrypt") ||
      !storageKey.usages?.includes("decrypt")
    ) {
      fail(
        "INVALID_INPUT",
        "A non-exported AES-GCM device-storage key is required.",
      );
    }
  }

  function assertLease(record, lease, currentTime) {
    if (
      !record ||
      record.ownerId !== lease?.ownerId ||
      record.fencingToken !== lease?.fencingToken ||
      record.expiresAt <= currentTime
    ) {
      fail("LEASE_LOST", "The browser-state lease is no longer valid.");
    }
  }

  function assertBounds(skippedKeys, pendingTransitions) {
    if (
      !Array.isArray(skippedKeys) ||
      skippedKeys.length > MAX_SKIPPED_KEYS ||
      !Array.isArray(pendingTransitions) ||
      pendingTransitions.length > MAX_PENDING_TRANSITIONS
    ) {
      fail("STATE_LIMIT", "Protocol state exceeds its persisted bounds.");
    }
  }

  async function create(options) {
    const accountId = requireText(options?.accountId, "Account ID");
    const deviceId = requireText(options?.deviceId, "Device ID");
    const sessionBinding = requireText(
      options?.sessionBinding,
      "Authenticated session binding",
    );
    const sessionBindingDigest = await sha256Hex(
      `HushLine/HL-PQCHAT-1/authenticated-session/v1\u0000${sessionBinding}`,
    );
    let storageKey = options?.storageKey;
    assertStorageKey(storageKey);
    const indexedDb = options?.indexedDB || browserGlobal.indexedDB;
    if (!indexedDb) {
      fail("STORAGE_UNAVAILABLE", "IndexedDB is unavailable.");
    }
    const now = options?.now || (() => Date.now());
    const faultInjector = options?.faultInjector || (() => undefined);
    const leaseDurationMs =
      options?.leaseDurationMs || DEFAULT_LEASE_DURATION_MS;
    if (!Number.isSafeInteger(leaseDurationMs) || leaseDurationMs < 1000) {
      fail("INVALID_INPUT", "Lease duration must be at least one second.");
    }
    const partition = `${accountId}:${deviceId}`;
    const leaseId = `lease:${partition}`;
    let database;
    let channel = null;
    let adapterApi = null;
    const outboxListeners = new Set();
    try {
      database = await openDatabase(indexedDb);
      database.addEventListener("versionchange", () => {
        storageKey = null;
        outboxListeners.clear();
        channel?.close();
        database.close();
        activeAdapters.delete(adapterApi);
      });
      if (browserGlobal.BroadcastChannel) {
        channel = new browserGlobal.BroadcastChannel(CHANNEL_NAME);
      }
    } catch (error) {
      throw storageError(error);
    }

    function requireUnlocked() {
      if (!storageKey) {
        fail("SESSION_LOCKED", "Browser state is locked for this session.");
      }
    }

    function recordMetadata(record) {
      const {
        ciphertext,
        iv,
        ...metadata
      } = record;
      return metadata;
    }

    async function seal(metadata, privateValue) {
      requireUnlocked();
      const iv = browserGlobal.crypto.getRandomValues(new Uint8Array(12));
      const ciphertext = await browserGlobal.crypto.subtle.encrypt(
        {
          name: "AES-GCM",
          iv,
          additionalData: textEncoder.encode(canonicalStringify(metadata)),
        },
        storageKey,
        encodePrivateValue(privateValue),
      );
      return { ...metadata, iv, ciphertext };
    }

    async function unseal(record) {
      requireUnlocked();
      if (!record || record.envelopeVersion !== ENVELOPE_VERSION) {
        fail("STATE_CORRUPT", "Encrypted browser state has an unknown format.");
      }
      try {
        const plaintext = await browserGlobal.crypto.subtle.decrypt(
          {
            name: "AES-GCM",
            iv: record.iv,
            additionalData: textEncoder.encode(
              canonicalStringify(recordMetadata(record)),
            ),
          },
          storageKey,
          record.ciphertext,
        );
        return decodePrivateValue(new Uint8Array(plaintext));
      } catch (error) {
        fail("STATE_CORRUPT", "Encrypted browser state failed authentication.");
      }
    }

    async function sessionKey(sessionId) {
      requireUnlocked();
      requireText(sessionId, "Protocol session ID");
      return sha256Hex(`HushLine/HL-PQCHAT-1/session/v1\u0000${sessionId}`);
    }

    async function logicalKey(logicalMessageId) {
      requireText(logicalMessageId, "Logical message ID");
      return sha256Hex(
        `HushLine/HL-PQCHAT-1/logical-message/v1\u0000${logicalMessageId}`,
      );
    }

    function recordId(type, hashedSession, suffix = "") {
      return `${partition}:${type}:${hashedSession}${suffix ? `:${suffix}` : ""}`;
    }

    async function getRecord(id) {
      try {
        return await runTransaction(
          database,
          [RECORDS_STORE],
          "readonly",
          ({ [RECORDS_STORE]: records }) => requestResult(records.get(id)),
        );
      } catch (error) {
        throw storageError(error);
      }
    }

    function metadata(type, id, revision, extra = {}) {
      return {
        id,
        partition,
        type,
        revision,
        envelopeVersion: ENVELOPE_VERSION,
        recordTag: browserGlobal.crypto.randomUUID(),
        sessionBindingDigest,
        ...extra,
      };
    }

    async function acquireLease(ownerId = browserGlobal.crypto.randomUUID()) {
      requireText(ownerId, "Lease owner ID");
      const currentTime = now();
      try {
        return await runTransaction(
          database,
          [LEASES_STORE],
          "readwrite",
          async ({ [LEASES_STORE]: leases }) => {
            const current = await requestResult(leases.get(leaseId));
            if (
              current?.ownerId &&
              current.ownerId !== ownerId &&
              current.expiresAt > currentTime
            ) {
              fail("LEASE_BUSY", "Another browser context owns this device.");
            }
            const lease = {
              id: leaseId,
              ownerId,
              fencingToken: (current?.fencingToken || 0) + 1,
              expiresAt: currentTime + leaseDurationMs,
            };
            leases.put(lease);
            return {
              ownerId: lease.ownerId,
              fencingToken: lease.fencingToken,
              expiresAt: lease.expiresAt,
            };
          },
        );
      } catch (error) {
        throw storageError(error);
      }
    }

    async function renewLease(lease) {
      const currentTime = now();
      try {
        return await runTransaction(
          database,
          [LEASES_STORE],
          "readwrite",
          async ({ [LEASES_STORE]: leases }) => {
            const current = await requestResult(leases.get(leaseId));
            assertLease(current, lease, currentTime);
            current.expiresAt = currentTime + leaseDurationMs;
            leases.put(current);
            return {
              ownerId: current.ownerId,
              fencingToken: current.fencingToken,
              expiresAt: current.expiresAt,
            };
          },
        );
      } catch (error) {
        throw storageError(error);
      }
    }

    async function releaseLease(lease) {
      try {
        await runTransaction(
          database,
          [LEASES_STORE],
          "readwrite",
          async ({ [LEASES_STORE]: leases }) => {
            const current = await requestResult(leases.get(leaseId));
            if (
              current?.ownerId === lease?.ownerId &&
              current.fencingToken === lease?.fencingToken
            ) {
              leases.put({
                ...current,
                ownerId: null,
                expiresAt: 0,
              });
            }
          },
        );
      } catch (error) {
        throw storageError(error);
      }
    }

    async function initializeSession({
      lease,
      sessionId,
      state,
      stateDigest,
      skippedKeys = [],
      pendingTransitions = [],
    }) {
      requireDigest(stateDigest, "State digest");
      assertBounds(skippedKeys, pendingTransitions);
      const hashedSession = await sessionKey(sessionId);
      const id = recordId("state", hashedSession);
      const encrypted = await seal(metadata("state", id, 0), {
        sessionId,
        state,
        stateDigest,
        skippedKeys,
        pendingTransitions,
        lastAcknowledgedLogicalDigest: null,
        lastReceivedMessageDigest: null,
      });
      faultInjector("before-initialize-transaction");
      try {
        await runTransaction(
          database,
          [LEASES_STORE, RECORDS_STORE],
          "readwrite",
          async (stores) => {
            const currentLease = await requestResult(
              stores[LEASES_STORE].get(leaseId),
            );
            assertLease(currentLease, lease, now());
            const existing = await requestResult(
              stores[RECORDS_STORE].get(id),
            );
            if (existing) {
              fail("STATE_CONFLICT", "Protocol session already exists.");
            }
            stores[RECORDS_STORE].put(encrypted);
          },
        );
      } catch (error) {
        throw storageError(error);
      }
      faultInjector("after-initialize-transaction");
      return { revision: 0 };
    }

    async function loadSession(sessionId, { minimumRevision = 0 } = {}) {
      requireRevision(minimumRevision);
      const hashedSession = await sessionKey(sessionId);
      const record = await getRecord(recordId("state", hashedSession));
      if (!record) {
        fail("STATE_MISSING", "Protocol session state is unavailable.");
      }
      if (record.revision < minimumRevision) {
        fail("STALE_STATE", "Known-stale protocol state was rejected.");
      }
      const value = await unseal(record);
      if (value.sessionId !== sessionId) {
        fail("STATE_CORRUPT", "Protocol session binding does not match.");
      }
      return { ...value, revision: record.revision };
    }

    async function commitSend({
      lease,
      sessionId,
      expectedRevision,
      beforeStateDigest,
      nextState,
      afterStateDigest,
      logicalMessageId,
      idempotencyKey,
      exactRequestBytes,
      skippedKeys = [],
      pendingTransitions = [],
    }) {
      requireRevision(expectedRevision);
      requireDigest(beforeStateDigest, "Before-state digest");
      requireDigest(afterStateDigest, "After-state digest");
      requireDigest(idempotencyKey, "Idempotency key");
      assertBounds(skippedKeys, pendingTransitions);
      if (!(exactRequestBytes instanceof Uint8Array) || !exactRequestBytes.length) {
        fail("INVALID_INPUT", "Exact request bytes are required.");
      }
      if (exactRequestBytes.length > MAX_REQUEST_BYTES) {
        fail("STATE_LIMIT", "Exact request bytes exceed the protocol limit.");
      }
      const hashedSession = await sessionKey(sessionId);
      const hashedLogical = await logicalKey(logicalMessageId);
      const stateId = recordId("state", hashedSession);
      const pendingId = recordId("pending", hashedSession);
      const outboxId = recordId("outbox", hashedSession, hashedLogical);
      const sentId = recordId("sent", hashedSession, hashedLogical);
      const sentIdempotencyId = recordId(
        "sent-idempotency",
        hashedSession,
        idempotencyKey,
      );
      const requestDigest = await sha256Hex(exactRequestBytes);
      const [sentRecord, sentIdempotencyRecord] = await Promise.all([
        getRecord(sentId),
        getRecord(sentIdempotencyId),
      ]);
      if (sentRecord || sentIdempotencyRecord) {
        if (!sentRecord || !sentIdempotencyRecord) {
          fail("STATE_CONFLICT", "Outgoing message identity was already used.");
        }
        const [sentValue, sentIdempotencyValue] = await Promise.all([
          unseal(sentRecord),
          unseal(sentIdempotencyRecord),
        ]);
        if (
          sentValue.logicalMessageId === logicalMessageId &&
          sentValue.idempotencyKey === idempotencyKey &&
          sentValue.requestDigest === requestDigest &&
          sentIdempotencyValue.logicalMessageId === logicalMessageId &&
          sentIdempotencyValue.idempotencyKey === idempotencyKey &&
          sentIdempotencyValue.requestDigest === requestDigest
        ) {
          return {
            alreadyAcknowledged: true,
            alreadyCommitted: true,
            requestDigest,
          };
        }
        fail("STATE_CONFLICT", "Outgoing message identity was already used.");
      }
      const currentRecord = await getRecord(stateId);
      if (!currentRecord || currentRecord.revision !== expectedRevision) {
        fail("STATE_CONFLICT", "Send state was advanced by another context.");
      }
      const currentValue = await unseal(currentRecord);
      if (
        currentValue.sessionId !== sessionId ||
        currentValue.stateDigest !== beforeStateDigest
      ) {
        fail("STATE_CONFLICT", "Send state digest does not match.");
      }
      const pendingRecord = await seal(
        metadata("pending", pendingId, expectedRevision + 1, {
          baseRevision: expectedRevision,
          logicalDigest: hashedLogical,
        }),
        {
          sessionId,
          state: nextState,
          stateDigest: afterStateDigest,
          skippedKeys,
          pendingTransitions,
          logicalMessageId,
          idempotencyKey,
        },
      );
      const outboxRecord = await seal(
        metadata("outbox", outboxId, expectedRevision + 1, {
          requestDigest,
          logicalDigest: hashedLogical,
          idempotencyKey,
          createdAt: now(),
        }),
        {
          sessionId,
          logicalMessageId,
          idempotencyKey,
          exactRequestBytes,
        },
      );
      faultInjector("before-send-transaction");
      try {
        const result = await runTransaction(
          database,
          [LEASES_STORE, RECORDS_STORE],
          "readwrite",
          async (stores) => {
            const currentLease = await requestResult(
              stores[LEASES_STORE].get(leaseId),
            );
            assertLease(currentLease, lease, now());
            const records = stores[RECORDS_STORE];
            const storedState = await requestResult(records.get(stateId));
            if (
              !storedState ||
              storedState.recordTag !== currentRecord.recordTag ||
              storedState.revision !== expectedRevision
            ) {
              fail("STATE_CONFLICT", "Send state was advanced concurrently.");
            }
            const existingPending = await requestResult(records.get(pendingId));
            const existingOutbox = await requestResult(records.get(outboxId));
            const existingSent = await requestResult(records.get(sentId));
            const existingIdempotency = await requestResult(
              records.get(sentIdempotencyId),
            );
            if (existingSent || existingIdempotency) {
              fail("STATE_CONFLICT", "Outgoing message identity was already used.");
            }
            if (existingPending || existingOutbox) {
              if (
                existingPending?.logicalDigest === hashedLogical &&
                existingOutbox?.requestDigest === requestDigest &&
                existingOutbox.idempotencyKey === idempotencyKey
              ) {
                return { alreadyCommitted: true, requestDigest };
              }
              fail("STATE_CONFLICT", "A different send is already pending.");
            }
            const outboxCount = await requestResult(
              records.index("partitionType").count(
                browserGlobal.IDBKeyRange.only([partition, "outbox"]),
              ),
            );
            if (outboxCount >= MAX_OUTBOX_RECORDS) {
              fail("STATE_LIMIT", "The durable outbox is full.");
            }
            const sentCount = await requestResult(
              records.index("partitionType").count(
                browserGlobal.IDBKeyRange.only([partition, "sent"]),
              ),
            );
            if (sentCount + outboxCount >= MAX_SENT_RECORDS) {
              fail("STATE_LIMIT", "Outgoing deduplication state is full.");
            }
            records.put(pendingRecord);
            records.put(outboxRecord);
            return { alreadyCommitted: false, requestDigest };
          },
        );
        channel?.postMessage({ type: "outbox-ready", partition });
        faultInjector("after-send-transaction");
        return result;
      } catch (error) {
        throw storageError(error);
      }
    }

    async function loadOutbox(sessionId, logicalMessageId) {
      const hashedSession = await sessionKey(sessionId);
      const hashedLogical = await logicalKey(logicalMessageId);
      const record = await getRecord(
        recordId("outbox", hashedSession, hashedLogical),
      );
      if (!record) {
        return null;
      }
      const value = await unseal(record);
      if (
        value.sessionId !== sessionId ||
        value.logicalMessageId !== logicalMessageId ||
        (await sha256Hex(value.exactRequestBytes)) !== record.requestDigest
      ) {
        fail("STATE_CORRUPT", "Durable outbox bytes failed authentication.");
      }
      return { ...value, requestDigest: record.requestDigest };
    }

    async function listOutbox() {
      requireUnlocked();
      let records;
      try {
        records = await runTransaction(
          database,
          [RECORDS_STORE],
          "readonly",
          ({ [RECORDS_STORE]: recordStore }) =>
            requestResult(
              recordStore
                .index("partitionType")
                .getAll(
                  browserGlobal.IDBKeyRange.only([partition, "outbox"]),
                ),
            ),
        );
      } catch (error) {
        throw storageError(error);
      }
      const outbox = await Promise.all(
        records.map(async (record) => {
          const value = await unseal(record);
          if (
            (await sha256Hex(value.exactRequestBytes)) !== record.requestDigest
          ) {
            fail("STATE_CORRUPT", "Durable outbox bytes failed authentication.");
          }
          return {
            ...value,
            createdAt: record.createdAt,
            requestDigest: record.requestDigest,
          };
        }),
      );
      return outbox.sort(
        (left, right) =>
          left.createdAt - right.createdAt ||
          left.logicalMessageId.localeCompare(right.logicalMessageId),
      );
    }

    async function acknowledgeSend({
      lease,
      sessionId,
      logicalMessageId,
      idempotencyKey,
    }) {
      requireDigest(idempotencyKey, "Idempotency key");
      const hashedSession = await sessionKey(sessionId);
      const hashedLogical = await logicalKey(logicalMessageId);
      const stateId = recordId("state", hashedSession);
      const pendingId = recordId("pending", hashedSession);
      const outboxId = recordId("outbox", hashedSession, hashedLogical);
      const sentId = recordId("sent", hashedSession, hashedLogical);
      const sentIdempotencyId = recordId(
        "sent-idempotency",
        hashedSession,
        idempotencyKey,
      );
      const [
        currentRecord,
        pendingRecord,
        outboxRecord,
        sentRecord,
        sentIdempotencyRecord,
      ] = await Promise.all([
        getRecord(stateId),
        getRecord(pendingId),
        getRecord(outboxId),
        getRecord(sentId),
        getRecord(sentIdempotencyId),
      ]);
      if (!currentRecord) {
        fail("STATE_MISSING", "Protocol session state is unavailable.");
      }
      if (!pendingRecord || !outboxRecord) {
        if (sentRecord && sentIdempotencyRecord) {
          const [sentValue, sentIdempotencyValue] = await Promise.all([
            unseal(sentRecord),
            unseal(sentIdempotencyRecord),
          ]);
          if (
            sentValue.logicalMessageId === logicalMessageId &&
            sentValue.idempotencyKey === idempotencyKey &&
            sentIdempotencyValue.logicalMessageId === logicalMessageId &&
            sentIdempotencyValue.idempotencyKey === idempotencyKey
          ) {
            return {
              alreadyAcknowledged: true,
              revision: currentRecord.revision,
            };
          }
        }
        const currentValue = await unseal(currentRecord);
        if (currentValue.lastAcknowledgedLogicalDigest === hashedLogical) {
          return { alreadyAcknowledged: true, revision: currentRecord.revision };
        }
        fail("STATE_CONFLICT", "The acknowledged send is not pending.");
      }
      const [pendingValue, outboxValue] = await Promise.all([
        unseal(pendingRecord),
        unseal(outboxRecord),
      ]);
      if (
        pendingValue.logicalMessageId !== logicalMessageId ||
        pendingValue.idempotencyKey !== idempotencyKey ||
        outboxValue.logicalMessageId !== logicalMessageId ||
        outboxValue.idempotencyKey !== idempotencyKey
      ) {
        fail("STATE_CONFLICT", "Acknowledgement does not match the outbox.");
      }
      const promotedRecord = await seal(
        metadata("state", stateId, pendingRecord.revision, {
          lastLogicalDigest: hashedLogical,
        }),
        {
          sessionId,
          state: pendingValue.state,
          stateDigest: pendingValue.stateDigest,
          skippedKeys: pendingValue.skippedKeys,
          pendingTransitions: pendingValue.pendingTransitions,
          lastAcknowledgedLogicalDigest: hashedLogical,
          lastReceivedMessageDigest: null,
        },
      );
      const sentValue = {
        sessionId,
        logicalMessageId,
        idempotencyKey,
        requestDigest: outboxRecord.requestDigest,
      };
      const nextSentRecord = await seal(
        metadata("sent", sentId, pendingRecord.revision, {
          logicalDigest: hashedLogical,
          idempotencyKey,
          requestDigest: outboxRecord.requestDigest,
        }),
        sentValue,
      );
      const nextSentIdempotencyRecord = await seal(
        metadata(
          "sent-idempotency",
          sentIdempotencyId,
          pendingRecord.revision,
          {
            logicalDigest: hashedLogical,
            idempotencyKey,
            requestDigest: outboxRecord.requestDigest,
          },
        ),
        sentValue,
      );
      faultInjector("before-acknowledgement-transaction");
      try {
        await runTransaction(
          database,
          [LEASES_STORE, RECORDS_STORE],
          "readwrite",
          async (stores) => {
            const currentLease = await requestResult(
              stores[LEASES_STORE].get(leaseId),
            );
            assertLease(currentLease, lease, now());
            const records = stores[RECORDS_STORE];
            const [
              storedState,
              storedPending,
              storedOutbox,
              storedSent,
              storedIdempotency,
            ] = await Promise.all([
              requestResult(records.get(stateId)),
              requestResult(records.get(pendingId)),
              requestResult(records.get(outboxId)),
              requestResult(records.get(sentId)),
              requestResult(records.get(sentIdempotencyId)),
            ]);
            if (
              storedState?.recordTag !== currentRecord.recordTag ||
              storedPending?.recordTag !== pendingRecord.recordTag ||
              storedOutbox?.recordTag !== outboxRecord.recordTag
            ) {
              fail("STATE_CONFLICT", "Acknowledgement state changed concurrently.");
            }
            if (storedSent || storedIdempotency) {
              fail("STATE_CONFLICT", "Outgoing message identity was already used.");
            }
            records.put(promotedRecord);
            records.put(nextSentRecord);
            records.put(nextSentIdempotencyRecord);
            records.delete(pendingId);
            records.delete(outboxId);
          },
        );
      } catch (error) {
        throw storageError(error);
      }
      faultInjector("after-acknowledgement-transaction");
      return { alreadyAcknowledged: false, revision: pendingRecord.revision };
    }

    async function deliverOutbox({
      lease,
      sessionId,
      logicalMessageId,
      transmit,
    }) {
      if (typeof transmit !== "function") {
        fail("INVALID_INPUT", "An authenticated transmit callback is required.");
      }
      const item = await loadOutbox(sessionId, logicalMessageId);
      if (!item) {
        fail("STATE_MISSING", "The durable outbox item is unavailable.");
      }
      faultInjector("before-network-request");
      const response = await transmit(item.exactRequestBytes, {
        idempotencyKey: item.idempotencyKey,
        logicalMessageId: item.logicalMessageId,
      });
      if (
        response?.message_id !== item.logicalMessageId ||
        !Number.isSafeInteger(response.conversation_version) ||
        response.conversation_version < 1 ||
        typeof response.idempotent !== "boolean"
      ) {
        fail(
          "AUTHENTICATION_FAILED",
          "The server acknowledgement does not match the durable outbox.",
        );
      }
      faultInjector("after-network-response-before-acknowledgement");
      await acknowledgeSend({
        lease,
        sessionId,
        logicalMessageId,
        idempotencyKey: item.idempotencyKey,
      });
      faultInjector("after-local-acknowledgement");
      return response;
    }

    async function loadReceipt(sessionId, messageId) {
      const hashedSession = await sessionKey(sessionId);
      const hashedMessage = await logicalKey(messageId);
      const receiptId = recordId("receipt", hashedSession, hashedMessage);
      const record = await getRecord(receiptId);
      if (!record) {
        return null;
      }
      const value = await unseal(record);
      if (value.sessionId !== sessionId || value.messageId !== messageId) {
        fail("STATE_CORRUPT", "Receive deduplication state does not match.");
      }
      return value;
    }

    async function commitReceive({
      lease,
      sessionId,
      messageId,
      expectedRevision,
      beforeStateDigest,
      nextState,
      afterStateDigest,
      receipt,
      archiveResult,
      skippedKeys = [],
      pendingTransitions = [],
    }) {
      requireRevision(expectedRevision);
      requireText(messageId, "Message ID");
      requireDigest(beforeStateDigest, "Before-state digest");
      requireDigest(afterStateDigest, "After-state digest");
      if (archiveResult === undefined || archiveResult === null) {
        fail("INVALID_INPUT", "The required archive result is missing.");
      }
      assertBounds(skippedKeys, pendingTransitions);
      const existingReceipt = await loadReceipt(sessionId, messageId);
      if (existingReceipt) {
        return { duplicate: true, receipt: existingReceipt.receipt };
      }
      const hashedSession = await sessionKey(sessionId);
      const hashedMessage = await logicalKey(messageId);
      const stateId = recordId("state", hashedSession);
      const receiptId = recordId("receipt", hashedSession, hashedMessage);
      const currentRecord = await getRecord(stateId);
      if (!currentRecord || currentRecord.revision !== expectedRevision) {
        fail("STATE_CONFLICT", "Receive state was advanced by another context.");
      }
      const currentValue = await unseal(currentRecord);
      if (
        currentValue.sessionId !== sessionId ||
        currentValue.stateDigest !== beforeStateDigest
      ) {
        fail("STATE_CONFLICT", "Receive state digest does not match.");
      }
      const nextRecord = await seal(
        metadata("state", stateId, expectedRevision + 1, {
          lastMessageDigest: hashedMessage,
        }),
        {
          sessionId,
          state: nextState,
          stateDigest: afterStateDigest,
          skippedKeys,
          pendingTransitions,
          lastAcknowledgedLogicalDigest:
            currentValue.lastAcknowledgedLogicalDigest || null,
          lastReceivedMessageDigest: hashedMessage,
        },
      );
      const receiptRecord = await seal(
        metadata("receipt", receiptId, expectedRevision + 1, {
          messageDigest: hashedMessage,
          createdAt: now(),
        }),
        { sessionId, messageId, receipt, archiveResult },
      );
      faultInjector("before-receive-transaction");
      let duplicate = false;
      try {
        await runTransaction(
          database,
          [LEASES_STORE, RECORDS_STORE],
          "readwrite",
          async (stores) => {
            const currentLease = await requestResult(
              stores[LEASES_STORE].get(leaseId),
            );
            assertLease(currentLease, lease, now());
            const records = stores[RECORDS_STORE];
            const [storedState, storedReceipt, storedPending] = await Promise.all([
              requestResult(records.get(stateId)),
              requestResult(records.get(receiptId)),
              requestResult(records.get(recordId("pending", hashedSession))),
            ]);
            if (storedReceipt) {
              duplicate = true;
              return;
            }
            if (
              storedState?.recordTag !== currentRecord.recordTag ||
              storedState.revision !== expectedRevision
            ) {
              fail("STATE_CONFLICT", "Receive state changed concurrently.");
            }
            if (storedPending) {
              fail("STATE_CONFLICT", "A send transition is still pending.");
            }
            const receiptCount = await requestResult(
              records.index("partitionType").count(
                browserGlobal.IDBKeyRange.only([partition, "receipt"]),
              ),
            );
            if (receiptCount >= MAX_RECEIPTS_PER_DEVICE) {
              fail("STATE_LIMIT", "Receive deduplication state is full.");
            }
            records.put(nextRecord);
            records.put(receiptRecord);
          },
        );
      } catch (error) {
        throw storageError(error);
      }
      if (duplicate) {
        const storedReceipt = await loadReceipt(sessionId, messageId);
        return { duplicate: true, receipt: storedReceipt?.receipt };
      }
      faultInjector("after-receive-transaction");
      return { duplicate: false, receipt, revision: expectedRevision + 1 };
    }

    async function clearDeviceInternal(announce) {
      if (announce) {
        faultInjector("before-logout-transaction");
      }
      try {
        await runTransaction(
          database,
          [LEASES_STORE, RECORDS_STORE],
          "readwrite",
          async (stores) => {
            const records = stores[RECORDS_STORE];
            const keys = await requestResult(
              records
                .index("partition")
                .getAllKeys(browserGlobal.IDBKeyRange.only(partition)),
            );
            keys.forEach((key) => records.delete(key));
            const currentLease = await requestResult(
              stores[LEASES_STORE].get(leaseId),
            );
            stores[LEASES_STORE].put({
              id: leaseId,
              ownerId: null,
              fencingToken: (currentLease?.fencingToken || 0) + 1,
              expiresAt: 0,
            });
          },
        );
      } catch (error) {
        throw storageError(error);
      } finally {
        if (announce) {
          channel?.postMessage({ type: "clear-device", partition });
        }
        storageKey = null;
        outboxListeners.clear();
        channel?.close();
        database.close();
        activeAdapters.delete(adapterApi);
      }
      if (announce) {
        faultInjector("after-logout-transaction");
      }
    }

    async function clearDevice() {
      await clearDeviceInternal(true);
    }

    function lock() {
      storageKey = null;
      outboxListeners.clear();
      channel?.close();
      database.close();
      activeAdapters.delete(adapterApi);
    }

    function onOutboxReady(listener) {
      if (typeof listener !== "function") {
        fail("INVALID_INPUT", "An outbox listener is required.");
      }
      outboxListeners.add(listener);
      return () => outboxListeners.delete(listener);
    }

    adapterApi = Object.freeze({
      acquireLease,
      renewLease,
      releaseLease,
      initializeSession,
      loadSession,
      commitSend,
      loadOutbox,
      listOutbox,
      acknowledgeSend,
      deliverOutbox,
      loadReceipt,
      commitReceive,
      onOutboxReady,
      clearDevice,
      lock,
    });
    activeAdapters.add(adapterApi);
    channel?.addEventListener("message", (event) => {
      if (
        event.data?.type === "outbox-ready" &&
        event.data.partition === partition
      ) {
        outboxListeners.forEach((listener) => {
          try {
            listener();
          } catch (error) {
            // A wakeup callback cannot change durable state.
          }
        });
      }
      if (
        event.data?.type === "clear-device" &&
        event.data.partition === partition
      ) {
        void clearDeviceInternal(false).catch(() => lock());
      }
    });
    return adapterApi;
  }

  async function importStorageKey(rawKeyBytes) {
    if (!(rawKeyBytes instanceof Uint8Array) || rawKeyBytes.length !== 32) {
      fail("INVALID_INPUT", "Device-storage key must contain 32 bytes.");
    }
    try {
      return await browserGlobal.crypto.subtle.importKey(
        "raw",
        rawKeyBytes,
        { name: "AES-GCM", length: 256 },
        false,
        ["encrypt", "decrypt"],
      );
    } finally {
      rawKeyBytes.fill(0);
    }
  }

  async function clearAll() {
    await Promise.allSettled(
      Array.from(activeAdapters, (adapter) => adapter.clearDevice()),
    );
  }

  browserGlobal.HushLinePqBrowserState = Object.freeze({
    clearAll,
    create,
    importStorageKey,
    Error: PqBrowserStateError,
    limits: Object.freeze({
      maxOutboxRecords: MAX_OUTBOX_RECORDS,
      maxRequestBytes: MAX_REQUEST_BYTES,
      maxSentRecords: MAX_SENT_RECORDS,
      maxReceiptsPerDevice: MAX_RECEIPTS_PER_DEVICE,
      maxSkippedKeys: MAX_SKIPPED_KEYS,
      maxPendingTransitions: MAX_PENDING_TRANSITIONS,
    }),
  });
})();

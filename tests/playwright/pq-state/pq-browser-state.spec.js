const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { readFileSync } = require("node:fs");
const { expect, test } = require("@playwright/test");

const scriptPath = path.resolve("assets/js/pq-browser-state.js");
const adapterSource = readFileSync(scriptPath, "utf8");
const digest = (character) => character.repeat(64);

async function prepareOrigin(context) {
  await context.route("https://pq-state.test/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<!doctype html><meta charset=utf-8><title>PQ state test</title>",
    }),
  );
}

async function loadAdapter(
  page,
  {
    accountId,
    deviceId,
    sessionBinding = "authenticated-session-1",
    currentTime = 1000,
  },
) {
  await page.goto("https://pq-state.test/");
  await page.addScriptTag({ path: scriptPath });
  await page.evaluate(
    async ({
      requestedAccountId,
      requestedDeviceId,
      requestedSession,
      now,
    }) => {
      window.testClock = now;
      window.testFault = null;
      const rawKey = new Uint8Array(32).fill(23);
      const storageKey =
        await window.HushLinePqBrowserState.importStorageKey(rawKey);
      rawKey.fill(0);
      window.stateAdapter = await window.HushLinePqBrowserState.create({
        accountId: requestedAccountId,
        deviceId: requestedDeviceId,
        sessionBinding: requestedSession,
        storageKey,
        leaseDurationMs: 1000,
        now: () => window.testClock,
        faultInjector: (point) => {
          if (window.testFault === point) {
            throw new Error(`synthetic crash at ${point}`);
          }
        },
      });
    },
    {
      requestedAccountId: accountId,
      requestedDeviceId: deviceId,
      requestedSession: sessionBinding,
      now: currentTime,
    },
  );
}

async function initialize(page, sessionId = "ratchet-session-1") {
  await page.evaluate(
    async ({ requestedSessionId, stateDigest }) => {
      window.stateLease = await window.stateAdapter.acquireLease("tab-a");
      await window.stateAdapter.initializeSession({
        lease: window.stateLease,
        sessionId: requestedSessionId,
        state: { chainKey: "PRIVATE-RATCHET-SECRET", counter: 0 },
        stateDigest,
      });
    },
    { requestedSessionId: sessionId, stateDigest: digest("a") },
  );
}

test.beforeEach(async ({ context }, testInfo) => {
  await prepareOrigin(context);
  testInfo.annotations.push({
    type: "security",
    description: "Synthetic data only; no production disclosures or keys.",
  });
});

test("send commit survives termination and retries byte-identical ciphertext", async ({
  page,
}) => {
  const identity = {
    accountId: randomUUID(),
    deviceId: randomUUID(),
  };
  await loadAdapter(page, identity);
  await initialize(page);

  const committed = await page.evaluate(
    async ({ beforeDigest, afterDigest, idempotencyKey }) => {
      const exactRequestBytes = new TextEncoder().encode(
        '{"copies":["synthetic-ciphertext"],"manifest":"fixed"}',
      );
      window.testFault = "after-send-transaction";
      let crashObserved = false;
      try {
        await window.stateAdapter.commitSend({
          lease: window.stateLease,
          sessionId: "ratchet-session-1",
          expectedRevision: 0,
          beforeStateDigest: beforeDigest,
          nextState: { chainKey: "PRIVATE-NEXT-SECRET", counter: 1 },
          afterStateDigest: afterDigest,
          logicalMessageId: "logical-message-1",
          idempotencyKey,
          exactRequestBytes,
        });
      } catch (error) {
        crashObserved = true;
      }
      window.testFault = null;
      const outbox = await window.stateAdapter.loadOutbox(
        "ratchet-session-1",
        "logical-message-1",
      );
      const database = await new Promise((resolve, reject) => {
        const request = indexedDB.open("hushline-pq-browser-state-v1", 1);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const records = await new Promise((resolve, reject) => {
        const request = database
          .transaction("encrypted-records", "readonly")
          .objectStore("encrypted-records")
          .getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      database.close();
      return {
        crashObserved,
        bytes: Array.from(outbox.exactRequestBytes),
        rawStorage: JSON.stringify(records),
      };
    },
    {
      beforeDigest: digest("a"),
      afterDigest: digest("b"),
      idempotencyKey: digest("c"),
    },
  );
  expect(committed.crashObserved).toBe(true);
  expect(new TextDecoder().decode(Uint8Array.from(committed.bytes))).toBe(
    '{"copies":["synthetic-ciphertext"],"manifest":"fixed"}',
  );
  expect(committed.rawStorage).not.toContain("PRIVATE-RATCHET-SECRET");
  expect(committed.rawStorage).not.toContain("PRIVATE-NEXT-SECRET");

  await page.evaluate(() => window.stateAdapter.lock());
  await loadAdapter(page, {
    ...identity,
    sessionBinding: "authenticated-session-2",
    currentTime: 3000,
  });
  const retried = await page.evaluate(async () => {
    window.stateLease =
      await window.stateAdapter.acquireLease("tab-after-crash");
    const discoveredOutbox = await window.stateAdapter.listOutbox();
    let transmitted;
    await window.stateAdapter.deliverOutbox({
      lease: window.stateLease,
      sessionId: "ratchet-session-1",
      logicalMessageId: "logical-message-1",
      transmit: async (bytes, identifiers) => {
        transmitted = {
          bytes: Array.from(bytes),
          idempotencyKey: identifiers.idempotencyKey,
        };
        return {
          message_id: identifiers.logicalMessageId,
          conversation_version: 1,
          idempotent: false,
        };
      },
    });
    const state = await window.stateAdapter.loadSession("ratchet-session-1");
    const outbox = await window.stateAdapter.loadOutbox(
      "ratchet-session-1",
      "logical-message-1",
    );
    return {
      transmitted,
      discoveredLogicalMessageId: discoveredOutbox[0].logicalMessageId,
      discoveredBytes: Array.from(discoveredOutbox[0].exactRequestBytes),
      state,
      outbox,
    };
  });
  expect(retried.transmitted.bytes).toEqual(committed.bytes);
  expect(retried.discoveredLogicalMessageId).toBe("logical-message-1");
  expect(retried.discoveredBytes).toEqual(committed.bytes);
  expect(retried.transmitted.idempotencyKey).toBe(digest("c"));
  expect(retried.state.revision).toBe(1);
  expect(retried.state.state.counter).toBe(1);
  expect(retried.outbox).toBeNull();
});

test("fencing rejects an expired tab and receive deduplication is atomic", async ({
  context,
  page,
}) => {
  const identity = {
    accountId: randomUUID(),
    deviceId: randomUUID(),
  };
  await loadAdapter(page, identity);
  await initialize(page, "shared-session");

  const secondPage = await context.newPage();
  await loadAdapter(secondPage, { ...identity, currentTime: 3000 });
  await secondPage.evaluate(async () => {
    window.stateLease = await window.stateAdapter.acquireLease("tab-b");
  });

  const staleWriterCode = await page.evaluate(
    async ({ beforeDigest, afterDigest, idempotencyKey }) => {
      try {
        await window.stateAdapter.commitSend({
          lease: window.stateLease,
          sessionId: "shared-session",
          expectedRevision: 0,
          beforeStateDigest: beforeDigest,
          nextState: { counter: 1 },
          afterStateDigest: afterDigest,
          logicalMessageId: "stale-send",
          idempotencyKey,
          exactRequestBytes: new Uint8Array([1, 2, 3]),
        });
      } catch (error) {
        return error.code;
      }
      return null;
    },
    {
      beforeDigest: digest("a"),
      afterDigest: digest("b"),
      idempotencyKey: digest("d"),
    },
  );
  expect(staleWriterCode).toBe("LEASE_LOST");

  const receiveResults = await secondPage.evaluate(
    async ({ beforeDigest, afterDigest }) => {
      const input = {
        lease: window.stateLease,
        sessionId: "shared-session",
        messageId: "incoming-message-1",
        expectedRevision: 0,
        beforeStateDigest: beforeDigest,
        nextState: { counter: 1, receiveChain: "PRIVATE-RECEIVE-STATE" },
        afterStateDigest: afterDigest,
        receipt: { status: "stored" },
        archiveResult: { archiveEpoch: 7, opened: true },
      };
      const first = await window.stateAdapter.commitReceive(input);
      const second = await window.stateAdapter.commitReceive(input);
      const state = await window.stateAdapter.loadSession("shared-session");
      return { first, second, revision: state.revision };
    },
    { beforeDigest: digest("a"), afterDigest: digest("e") },
  );
  expect(receiveResults.first.duplicate).toBe(false);
  expect(receiveResults.second).toEqual({
    duplicate: true,
    receipt: { status: "stored" },
  });
  expect(receiveResults.revision).toBe(1);

  const workerTakeover = await secondPage.evaluate(
    async ({ source, accountId, deviceId }) => {
      const workerSource = `${source}\nself.onmessage = async (event) => {
        const key = await self.HushLinePqBrowserState.importStorageKey(
          new Uint8Array(32).fill(23),
        );
        const adapter = await self.HushLinePqBrowserState.create({
          accountId: event.data.accountId,
          deviceId: event.data.deviceId,
          sessionBinding: "worker-session",
          storageKey: key,
          leaseDurationMs: 1000,
          now: () => 5000,
        });
        const lease = await adapter.acquireLease("dedicated-worker");
        self.postMessage({ fencingToken: lease.fencingToken });
      };`;
      const workerUrl = URL.createObjectURL(
        new Blob([workerSource], { type: "application/javascript" }),
      );
      const worker = new Worker(workerUrl);
      const workerResult = await new Promise((resolve, reject) => {
        worker.onmessage = (event) => resolve(event.data);
        worker.onerror = (event) => reject(new Error(event.message));
        worker.postMessage({ accountId, deviceId });
      });
      worker.terminate();
      URL.revokeObjectURL(workerUrl);
      let staleCode = null;
      try {
        await window.stateAdapter.renewLease(window.stateLease);
      } catch (error) {
        staleCode = error.code;
      }
      return { ...workerResult, staleCode };
    },
    { source: adapterSource, ...identity },
  );
  expect(workerTakeover.fencingToken).toBeGreaterThan(2);
  expect(workerTakeover.staleCode).toBe("LEASE_LOST");
  await secondPage.evaluate(() => window.stateAdapter.clearDevice());
  await expect
    .poll(() =>
      page.evaluate(async () => {
        try {
          await window.stateAdapter.loadSession("shared-session");
        } catch (error) {
          return error.code;
        }
        return null;
      }),
    )
    .toBe("SESSION_LOCKED");
});

test("network ambiguity retains the exact outbox and acknowledgement is idempotent", async ({
  page,
}) => {
  const identity = {
    accountId: randomUUID(),
    deviceId: randomUUID(),
  };
  await loadAdapter(page, identity);
  await initialize(page);
  const result = await page.evaluate(
    async ({ beforeDigest, afterDigest, idempotencyKey }) => {
      const exactRequestBytes = new Uint8Array([9, 8, 7, 6]);
      await window.stateAdapter.commitSend({
        lease: window.stateLease,
        sessionId: "ratchet-session-1",
        expectedRevision: 0,
        beforeStateDigest: beforeDigest,
        nextState: { counter: 1 },
        afterStateDigest: afterDigest,
        logicalMessageId: "logical-message-ambiguous",
        idempotencyKey,
        exactRequestBytes,
      });
      let sends = 0;
      let invalidAcknowledgementCode = null;
      try {
        await window.stateAdapter.deliverOutbox({
          lease: window.stateLease,
          sessionId: "ratchet-session-1",
          logicalMessageId: "logical-message-ambiguous",
          transmit: async () => {
            sends += 1;
            return {
              message_id: "wrong-logical-message",
              conversation_version: 1,
              idempotent: false,
            };
          },
        });
      } catch (error) {
        invalidAcknowledgementCode = error.code;
      }
      window.testFault = "after-network-response-before-acknowledgement";
      try {
        await window.stateAdapter.deliverOutbox({
          lease: window.stateLease,
          sessionId: "ratchet-session-1",
          logicalMessageId: "logical-message-ambiguous",
          transmit: async (_bytes, identifiers) => {
            sends += 1;
            return {
              message_id: identifiers.logicalMessageId,
              conversation_version: 1,
              idempotent: false,
            };
          },
        });
      } catch (error) {
        // The simulated response was lost before local acknowledgement.
      }
      window.testFault = null;
      const retained = await window.stateAdapter.loadOutbox(
        "ratchet-session-1",
        "logical-message-ambiguous",
      );
      window.testFault = "after-local-acknowledgement";
      let localAcknowledgementFault = false;
      try {
        await window.stateAdapter.deliverOutbox({
          lease: window.stateLease,
          sessionId: "ratchet-session-1",
          logicalMessageId: "logical-message-ambiguous",
          transmit: async (_bytes, identifiers) => {
            sends += 1;
            return {
              message_id: identifiers.logicalMessageId,
              conversation_version: 1,
              idempotent: true,
            };
          },
        });
      } catch (error) {
        localAcknowledgementFault = true;
      }
      window.testFault = null;
      const repeatedAck = await window.stateAdapter.acknowledgeSend({
        lease: window.stateLease,
        sessionId: "ratchet-session-1",
        logicalMessageId: "logical-message-ambiguous",
        idempotencyKey,
      });
      const acknowledgedRetry = await window.stateAdapter.commitSend({
        lease: window.stateLease,
        sessionId: "ratchet-session-1",
        expectedRevision: 0,
        beforeStateDigest: beforeDigest,
        nextState: { counter: 1 },
        afterStateDigest: afterDigest,
        logicalMessageId: "logical-message-ambiguous",
        idempotencyKey,
        exactRequestBytes,
      });
      let collisionCode = null;
      try {
        await window.stateAdapter.commitSend({
          lease: window.stateLease,
          sessionId: "ratchet-session-1",
          expectedRevision: 1,
          beforeStateDigest: afterDigest,
          nextState: { counter: 2 },
          afterStateDigest: "0".repeat(64),
          logicalMessageId: "different-logical-message",
          idempotencyKey,
          exactRequestBytes,
        });
      } catch (error) {
        collisionCode = error.code;
      }
      return {
        sends,
        retained: Array.from(retained.exactRequestBytes),
        repeatedAck,
        acknowledgedRetry,
        collisionCode,
        invalidAcknowledgementCode,
        localAcknowledgementFault,
      };
    },
    {
      beforeDigest: digest("a"),
      afterDigest: digest("b"),
      idempotencyKey: digest("f"),
    },
  );
  expect(result.sends).toBe(3);
  expect(result.retained).toEqual([9, 8, 7, 6]);
  expect(result.repeatedAck.alreadyAcknowledged).toBe(true);
  expect(result.acknowledgedRetry.alreadyAcknowledged).toBe(true);
  expect(result.collisionCode).toBe("STATE_CONFLICT");
  expect(result.invalidAcknowledgementCode).toBe("AUTHENTICATION_FAILED");
  expect(result.localAcknowledgementFault).toBe(true);
});

test("fault injection preserves each storage and network boundary", async ({
  page,
}) => {
  const identity = {
    accountId: randomUUID(),
    deviceId: randomUUID(),
  };
  await loadAdapter(page, identity);
  const observations = await page.evaluate(
    async ({ zeroDigest, oneDigest, twoDigest, idempotencyKey }) => {
      const observed = {};
      window.stateLease = await window.stateAdapter.acquireLease("fault-tab");
      const initializeInput = {
        lease: window.stateLease,
        sessionId: "fault-send-session",
        state: { counter: 0 },
        stateDigest: zeroDigest,
      };

      window.testFault = "before-initialize-transaction";
      try {
        await window.stateAdapter.initializeSession(initializeInput);
      } catch (error) {
        observed.beforeInitialize = true;
      }
      window.testFault = null;
      try {
        await window.stateAdapter.loadSession("fault-send-session");
      } catch (error) {
        observed.beforeInitializeMissing = error.code;
      }

      window.testFault = "after-initialize-transaction";
      try {
        await window.stateAdapter.initializeSession(initializeInput);
      } catch (error) {
        observed.afterInitialize = true;
      }
      window.testFault = null;
      observed.afterInitializeRevision = (
        await window.stateAdapter.loadSession("fault-send-session")
      ).revision;

      const sendInput = {
        lease: window.stateLease,
        sessionId: "fault-send-session",
        expectedRevision: 0,
        beforeStateDigest: zeroDigest,
        nextState: { counter: 1 },
        afterStateDigest: oneDigest,
        logicalMessageId: "fault-logical-message",
        idempotencyKey,
        exactRequestBytes: new Uint8Array([4, 5, 6]),
      };
      window.testFault = "before-send-transaction";
      try {
        await window.stateAdapter.commitSend(sendInput);
      } catch (error) {
        observed.beforeSend = true;
      }
      window.testFault = null;
      observed.beforeSendOutbox = await window.stateAdapter.loadOutbox(
        "fault-send-session",
        "fault-logical-message",
      );
      await window.stateAdapter.commitSend(sendInput);

      let transmissions = 0;
      window.testFault = "before-network-request";
      try {
        await window.stateAdapter.deliverOutbox({
          lease: window.stateLease,
          sessionId: "fault-send-session",
          logicalMessageId: "fault-logical-message",
          transmit: async () => {
            transmissions += 1;
          },
        });
      } catch (error) {
        observed.beforeNetwork = true;
      }
      window.testFault = null;
      observed.beforeNetworkTransmissions = transmissions;

      window.testFault = "before-acknowledgement-transaction";
      try {
        await window.stateAdapter.acknowledgeSend({
          lease: window.stateLease,
          sessionId: "fault-send-session",
          logicalMessageId: "fault-logical-message",
          idempotencyKey,
        });
      } catch (error) {
        observed.beforeAcknowledgement = true;
      }
      window.testFault = null;
      observed.beforeAcknowledgementRevision = (
        await window.stateAdapter.loadSession("fault-send-session")
      ).revision;

      window.testFault = "after-acknowledgement-transaction";
      try {
        await window.stateAdapter.acknowledgeSend({
          lease: window.stateLease,
          sessionId: "fault-send-session",
          logicalMessageId: "fault-logical-message",
          idempotencyKey,
        });
      } catch (error) {
        observed.afterAcknowledgement = true;
      }
      window.testFault = null;
      observed.afterAcknowledgementRevision = (
        await window.stateAdapter.loadSession("fault-send-session")
      ).revision;

      await window.stateAdapter.initializeSession({
        lease: window.stateLease,
        sessionId: "fault-receive-session",
        state: { counter: 0 },
        stateDigest: zeroDigest,
      });
      const receiveInput = {
        lease: window.stateLease,
        sessionId: "fault-receive-session",
        messageId: "fault-incoming-message",
        expectedRevision: 0,
        beforeStateDigest: zeroDigest,
        nextState: { counter: 1 },
        afterStateDigest: twoDigest,
        receipt: { status: "stored" },
        archiveResult: { opened: true },
      };
      window.testFault = "before-receive-transaction";
      try {
        await window.stateAdapter.commitReceive(receiveInput);
      } catch (error) {
        observed.beforeReceive = true;
      }
      window.testFault = null;
      observed.beforeReceiveReceipt = await window.stateAdapter.loadReceipt(
        "fault-receive-session",
        "fault-incoming-message",
      );

      window.testFault = "after-receive-transaction";
      try {
        await window.stateAdapter.commitReceive(receiveInput);
      } catch (error) {
        observed.afterReceive = true;
      }
      window.testFault = null;
      observed.afterReceiveRevision = (
        await window.stateAdapter.loadSession("fault-receive-session")
      ).revision;

      window.testFault = "before-logout-transaction";
      try {
        await window.stateAdapter.clearDevice();
      } catch (error) {
        observed.beforeLogout = true;
      }
      window.testFault = null;
      observed.beforeLogoutState = (
        await window.stateAdapter.loadSession("fault-receive-session")
      ).revision;
      await window.stateAdapter.clearDevice();
      return observed;
    },
    {
      zeroDigest: digest("0"),
      oneDigest: digest("1"),
      twoDigest: digest("2"),
      idempotencyKey: digest("3"),
    },
  );

  expect(observations).toEqual({
    beforeInitialize: true,
    beforeInitializeMissing: "STATE_MISSING",
    afterInitialize: true,
    afterInitializeRevision: 0,
    beforeSend: true,
    beforeSendOutbox: null,
    beforeNetwork: true,
    beforeNetworkTransmissions: 0,
    beforeAcknowledgement: true,
    beforeAcknowledgementRevision: 0,
    afterAcknowledgement: true,
    afterAcknowledgementRevision: 1,
    beforeReceive: true,
    beforeReceiveReceipt: null,
    afterReceive: true,
    afterReceiveRevision: 1,
    beforeLogout: true,
    beforeLogoutState: 1,
  });
});

test("storage denial, stale snapshots, bounds, and logout fail closed", async ({
  page,
}) => {
  const identity = {
    accountId: randomUUID(),
    deviceId: randomUUID(),
  };
  await loadAdapter(page, identity);
  await initialize(page);
  const freshDeviceId = randomUUID();
  await page.evaluate(
    ({ accountId, freshId }) => {
      window.testAccountId = accountId;
      window.testFreshDeviceId = freshId;
    },
    { accountId: identity.accountId, freshId: freshDeviceId },
  );
  const results = await page.evaluate(async () => {
    const values = {};
    const accountId = window.testAccountId;
    const freshDeviceId = window.testFreshDeviceId;
    try {
      await window.stateAdapter.loadSession("ratchet-session-1", {
        minimumRevision: 1,
      });
    } catch (error) {
      values.stale = error.code;
    }
    try {
      await window.stateAdapter.commitReceive({
        lease: window.stateLease,
        sessionId: "ratchet-session-1",
        messageId: "oversized-state",
        expectedRevision: 0,
        beforeStateDigest: "a".repeat(64),
        nextState: {},
        afterStateDigest: "b".repeat(64),
        receipt: {},
        archiveResult: {},
        skippedKeys: Array(2001).fill("synthetic"),
      });
    } catch (error) {
      values.bound = error.code;
    }
    const database = await new Promise((resolve, reject) => {
      const request = indexedDB.open("hushline-pq-browser-state-v1", 1);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(
        "encrypted-records",
        "readwrite",
      );
      const records = transaction.objectStore("encrypted-records");
      const request = records.getAll();
      request.onsuccess = () => {
        const stateRecord = request.result.find(
          (record) => record.type === "state",
        );
        const ciphertext = new Uint8Array(stateRecord.ciphertext);
        ciphertext[0] ^= 1;
        records.put({ ...stateRecord, ciphertext: ciphertext.buffer });
      };
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    database.close();
    try {
      await window.stateAdapter.loadSession("ratchet-session-1");
    } catch (error) {
      values.corrupt = error.code;
    }
    window.testFault = "after-logout-transaction";
    try {
      await window.stateAdapter.clearDevice();
    } catch (error) {
      values.afterLogout = true;
    }
    window.testFault = null;
    try {
      await window.stateAdapter.loadSession("ratchet-session-1");
    } catch (error) {
      values.logout = error.code;
    }
    const freshRawKey = new Uint8Array(32).fill(23);
    const freshKey =
      await window.HushLinePqBrowserState.importStorageKey(freshRawKey);
    freshRawKey.fill(0);
    const freshAdapter = await window.HushLinePqBrowserState.create({
      accountId,
      deviceId: freshDeviceId,
      sessionBinding: "fresh-browser-session",
      storageKey: freshKey,
      leaseDurationMs: 1000,
      now: () => 3000,
    });
    const freshLease = await freshAdapter.acquireLease("fresh-browser");
    try {
      await freshAdapter.loadSession("ratchet-session-1");
    } catch (error) {
      values.freshBrowserOldState = error.code;
    }
    await freshAdapter.initializeSession({
      lease: freshLease,
      sessionId: "fresh-ratchet-session",
      state: { counter: 0 },
      stateDigest: "4".repeat(64),
    });
    values.freshBrowserRevision = (
      await freshAdapter.loadSession("fresh-ratchet-session")
    ).revision;
    await freshAdapter.clearDevice();
    const rawKey = new Uint8Array(32).fill(44);
    const key = await window.HushLinePqBrowserState.importStorageKey(rawKey);
    rawKey.fill(0);
    try {
      await window.HushLinePqBrowserState.create({
        accountId: "storage-denied",
        deviceId: "storage-denied",
        sessionBinding: "storage-denied",
        storageKey: key,
        indexedDB: {
          open() {
            throw new DOMException("denied", "QuotaExceededError");
          },
        },
      });
    } catch (error) {
      values.denied = error.code;
    }
    return values;
  });
  expect(results).toEqual({
    stale: "STALE_STATE",
    bound: "STATE_LIMIT",
    corrupt: "STATE_CORRUPT",
    afterLogout: true,
    logout: "SESSION_LOCKED",
    freshBrowserOldState: "STATE_MISSING",
    freshBrowserRevision: 0,
    denied: "STORAGE_UNAVAILABLE",
  });
});

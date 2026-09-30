(function () {
  "use strict";

  const PROTOCOL = "HL-PQCHAT-1";
  const SUITE = "SIGNAL-PQXDH3-KYBER1024-SPQR1";
  const REQUEST_TIMEOUT_MS = 30000;
  const workerUrl = document.currentScript?.dataset.workerUrl;
  const encoder = new TextEncoder();

  class PqProtocolError extends Error {
    constructor(code) {
      super(code);
      this.name = "PqProtocolError";
      this.code = code;
    }
  }

  function fail(code) {
    throw new PqProtocolError(code);
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

  async function sha256Hex(value) {
    const bytes = typeof value === "string" ? encoder.encode(value) : value;
    const digest = new Uint8Array(
      await window.crypto.subtle.digest("SHA-256", bytes),
    );
    return Array.from(digest, (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
  }

  function createWorkerClient(options = {}) {
    const WorkerConstructor = options.Worker || window.Worker;
    const resolvedWorkerUrl = options.workerUrl || workerUrl;
    if (!WorkerConstructor || !resolvedWorkerUrl) {
      fail("CAPABILITY_UNAVAILABLE");
    }
    const worker = new WorkerConstructor(resolvedWorkerUrl);
    const pending = new Map();
    let nextId = 1;
    let closed = false;

    function rejectAll(code) {
      for (const request of pending.values()) {
        window.clearTimeout(request.timeout);
        request.reject(new PqProtocolError(code));
      }
      pending.clear();
    }

    worker.addEventListener("message", (event) => {
      const request = pending.get(event.data?.id);
      if (!request) return;
      pending.delete(event.data.id);
      window.clearTimeout(request.timeout);
      if (event.data.ok) {
        request.resolve(event.data.result);
      } else {
        request.reject(
          new PqProtocolError(event.data.error || "INTERNAL_ERROR"),
        );
      }
    });
    worker.addEventListener("error", () => {
      closed = true;
      rejectAll("CAPABILITY_UNAVAILABLE");
      worker.terminate();
    });

    function call(operation, args) {
      if (closed) return Promise.reject(new PqProtocolError("STATE_CONFLICT"));
      const id = nextId++;
      return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          pending.delete(id);
          closed = true;
          worker.terminate();
          reject(new PqProtocolError("INTERNAL_ERROR"));
          rejectAll("INTERNAL_ERROR");
        }, options.timeoutMs || REQUEST_TIMEOUT_MS);
        pending.set(id, { reject, resolve, timeout });
        worker.postMessage({ id, operation, args });
      });
    }

    return Object.freeze({
      archiveOpen: (args) => call("archiveOpen", args),
      archiveSeal: (args) => call("archiveSeal", args),
      beginSession: (args) => call("beginSession", args),
      close() {
        if (closed) return;
        closed = true;
        rejectAll("STATE_CONFLICT");
        worker.terminate();
      },
      createArchiveEpoch: (args) => call("createArchiveEpoch", args),
      createDevice: (args) => call("createDevice", args),
      ratchetDecrypt: (args) => call("ratchetDecrypt", args),
      ratchetEncrypt: (args) => call("ratchetEncrypt", args),
    });
  }

  async function beginVerifiedSession({
    client,
    expectedAccountId,
    expectedIdentityPublicKey,
    localState,
    minimumMembershipSequence = 0,
    prekeyClaim,
    replaceExisting = false,
  }) {
    const verifier = window.HushLineChatKeys?.verifyPqPrekeyClaim;
    if (
      typeof verifier !== "function" ||
      !(await verifier(
        prekeyClaim,
        minimumMembershipSequence,
        expectedAccountId,
        expectedIdentityPublicKey,
      ))
    ) {
      fail("AUTHENTICATION_FAILED");
    }
    const membership = prekeyClaim.device.membership;
    return client.beginSession({
      remoteBundle: {
        address: {
          name: `${membership.account_id}.${membership.device_id}`,
          deviceId: 1,
        },
        identityKey: membership.protocol_identity_public_key,
        kyberPrekey: {
          id: prekeyClaim.one_time_prekey.key_id,
          publicKey: prekeyClaim.one_time_prekey.pq_public_key,
          signature: prekeyClaim.one_time_prekey.pq_signature,
        },
        membershipSequence: membership.membership_sequence,
        prekey: {
          id: prekeyClaim.one_time_prekey.key_id,
          publicKey: prekeyClaim.one_time_prekey.classical_public_key,
        },
        protocol: PROTOCOL,
        registrationId: membership.protocol_registration_id,
        signedPrekey: {
          id: prekeyClaim.signed_prekey.key_id,
          publicKey: prekeyClaim.signed_prekey.classical_public_key,
          signature: prekeyClaim.signed_prekey.classical_signature,
        },
        suite: SUITE,
      },
      replaceExisting,
      state: localState,
    });
  }

  async function createPersistedSession(options) {
    const browserState = options?.browserState || window.HushLinePqBrowserState;
    if (!browserState?.create || !options?.initialState) {
      fail("CAPABILITY_UNAVAILABLE");
    }
    const client = options.client || createWorkerClient(options);
    const state = await browserState.create({
      accountId: options.accountId,
      deviceId: options.deviceId,
      indexedDB: options.indexedDB,
      sessionBinding: options.sessionBinding,
      storageKey: options.storageKey,
    });
    const lease = await state.acquireLease(options.leaseOwnerId);
    const initialDigest = await sha256Hex(
      canonicalStringify(options.initialState),
    );
    try {
      await state.initializeSession({
        lease,
        sessionId: options.sessionId,
        state: options.initialState,
        stateDigest: initialDigest,
      });
    } catch (error) {
      if (error?.code !== "STATE_CONFLICT") throw error;
    }

    async function encrypt({
      buildRequest,
      context,
      idempotencyKey,
      logicalMessageId,
      plaintext,
    }) {
      if (typeof buildRequest !== "function") fail("MALFORMED_WIRE");
      const current = await state.loadSession(options.sessionId);
      const encrypted = await client.ratchetEncrypt({
        context,
        plaintext,
        state: current.state,
      });
      const nextDigest = await sha256Hex(canonicalStringify(encrypted.state));
      const exactRequestBytes = encoder.encode(
        canonicalStringify(
          await buildRequest({
            ciphertext: encrypted.ciphertext,
            observation: encrypted.observation,
            status: encrypted.status,
          }),
        ),
      );
      await state.commitSend({
        afterStateDigest: nextDigest,
        beforeStateDigest: current.stateDigest,
        exactRequestBytes,
        expectedRevision: current.revision,
        idempotencyKey,
        lease,
        logicalMessageId,
        nextState: encrypted.state,
        sessionId: options.sessionId,
      });
      return {
        exactRequestBytes,
        observation: encrypted.observation,
        status: encrypted.status,
      };
    }

    async function decrypt({
      archiveResult,
      ciphertext,
      context,
      messageId,
      receipt,
      senderAddress,
    }) {
      const prior = await state.loadReceipt(options.sessionId, messageId);
      if (prior) return { duplicate: true, receipt: prior.receipt };
      const current = await state.loadSession(options.sessionId);
      const decrypted = await client.ratchetDecrypt({
        ciphertext,
        context,
        senderAddress,
        state: current.state,
      });
      const nextDigest = await sha256Hex(canonicalStringify(decrypted.state));
      const committed = await state.commitReceive({
        afterStateDigest: nextDigest,
        archiveResult,
        beforeStateDigest: current.stateDigest,
        expectedRevision: current.revision,
        lease,
        messageId,
        nextState: decrypted.state,
        receipt,
        sessionId: options.sessionId,
      });
      return {
        ...committed,
        plaintext: committed.duplicate ? null : decrypted.plaintext,
        status: decrypted.status,
      };
    }

    return Object.freeze({
      acknowledgeSend: (logicalMessageId, idempotencyKey) =>
        state.acknowledgeSend({
          idempotencyKey,
          lease,
          logicalMessageId,
          sessionId: options.sessionId,
        }),
      async close() {
        try {
          await state.releaseLease(lease);
        } finally {
          client.close();
          state.lock();
        }
      },
      decrypt,
      deliverOutbox: (logicalMessageId, transmit) =>
        state.deliverOutbox({
          lease,
          logicalMessageId,
          sessionId: options.sessionId,
          transmit,
        }),
      encrypt,
      listOutbox: state.listOutbox,
      renewLease: () => state.renewLease(lease),
    });
  }

  window.HushLinePqProtocol = Object.freeze({
    Error: PqProtocolError,
    beginVerifiedSession,
    createPersistedSession,
    createWorkerClient,
    implementation: Object.freeze({
      candidate: "@getmaapp/signal-wasm",
      candidateVersion: "0.6.6",
      kem: "round-3 Kyber1024",
      kemIsFips203MlKem: false,
      protocol: PROTOCOL,
      suite: SUITE,
      upstreamRevision: "b056faa6dd02961cff24064c54c089c52e1a0753",
      upstreamVersion: "0.101.0",
      wrapperSourceRevision: "0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd",
    }),
  });
})();

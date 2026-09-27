import init, {
  IdentityKeyPair,
  InMemIdentityKeyStore,
  InMemKyberPreKeyStore,
  InMemPreKeyStore,
  InMemSessionStore,
  InMemSignedPreKeyStore,
  PrivateKey,
  ProtocolAddress,
  decryptMessage,
  encryptMessage,
  generateKyberPreKey,
  generatePreKeys,
  generateRegistrationId,
  generateSignedPreKey,
  message_type_pre_key,
  message_type_signal,
  processPreKeyBundle,
} from "/vendor/signal_wasm.js";

const encoder = new TextEncoder();
const SYNTHETIC_MESSAGE = encoder.encode(
  "fictional Hush Line PQ prototype message",
);
const SNAPSHOT_KEY = "hushline-pq-prototype-synthetic-state-v1";

function invariant(value, message) {
  if (!value) throw new Error(message);
}

function equalBytes(left, right) {
  return (
    left.length === right.length &&
    left.every((byte, index) => byte === right[index])
  );
}

function readVarint(bytes, start) {
  let value = 0;
  let shift = 0;
  let offset = start;
  while (offset < bytes.length && shift <= 63) {
    const byte = bytes[offset++];
    value += (byte & 0x7f) * 2 ** shift;
    if ((byte & 0x80) === 0) return { value, offset };
    shift += 7;
  }
  throw new Error("invalid varint");
}

function protobufBytesField(bytes, wantedField) {
  let offset = 0;
  while (offset < bytes.length) {
    const tag = readVarint(bytes, offset);
    offset = tag.offset;
    const field = Math.floor(tag.value / 8);
    const wire = tag.value & 7;
    if (wire === 0) {
      offset = readVarint(bytes, offset).offset;
    } else if (wire === 1) {
      offset += 8;
    } else if (wire === 2) {
      const length = readVarint(bytes, offset);
      offset = length.offset;
      const end = offset + length.value;
      invariant(end <= bytes.length, "truncated protobuf field");
      if (field === wantedField) return bytes.slice(offset, end);
      offset = end;
    } else if (wire === 5) {
      offset += 4;
    } else {
      throw new Error("unsupported protobuf wire type");
    }
  }
  return null;
}

function observeSpqr(ciphertext) {
  if (ciphertext.message_type !== message_type_signal()) return null;
  const body = ciphertext.body;
  invariant(body.length > 9, "signal message too short");
  const pq = protobufBytesField(body.slice(1, -8), 5);
  if (!pq || pq.length < 4) return null;
  const epoch = readVarint(pq, 1);
  const messageIndex = readVarint(pq, epoch.offset);
  const messageType = pq[messageIndex.offset];
  invariant(pq[0] === 1, "unexpected SPQR wire version");
  invariant(epoch.value > 0, "SPQR epoch must be positive");
  invariant(messageType <= 6, "unexpected SPQR message type");
  return {
    epoch: epoch.value,
    message_index: messageIndex.value,
    message_type: messageType,
    wire_version: pq[0],
  };
}

async function sha256(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

async function createParticipant(name, keyBase) {
  const privateKey = PrivateKey.generate();
  const publicKey = privateKey.getPublicKey();
  const identityKeyPair = new IdentityKeyPair(publicKey, privateKey);
  const registrationId = generateRegistrationId();
  const identityStore = new InMemIdentityKeyStore(
    identityKeyPair,
    registrationId,
  );
  const sessionStore = new InMemSessionStore();
  const prekeyStore = new InMemPreKeyStore();
  const signedPrekeyStore = new InMemSignedPreKeyStore();
  const kyberPrekeyStore = new InMemKyberPreKeyStore();
  const prekeys = await generatePreKeys(keyBase, 2, prekeyStore);
  const signedPrekey = await generateSignedPreKey(
    keyBase + 100,
    identityKeyPair,
    signedPrekeyStore,
  );
  const kyberPrekey = await generateKyberPreKey(
    keyBase + 200,
    identityKeyPair,
    kyberPrekeyStore,
  );
  return {
    address: new ProtocolAddress(name, 1),
    identityKeyPair,
    identityStore,
    kyberPrekey,
    kyberPrekeyStore,
    prekeys,
    prekeyStore,
    publicKey,
    registrationId,
    sessionStore,
    signedPrekey,
    signedPrekeyStore,
  };
}

async function establish(alice, bob) {
  await processPreKeyBundle(
    bob.address,
    alice.address,
    bob.registrationId,
    bob.publicKey,
    bob.signedPrekey.id,
    bob.signedPrekey.public_key,
    bob.signedPrekey.signature,
    bob.prekeys[0].id,
    bob.prekeys[0].public_key,
    bob.kyberPrekey.id,
    bob.kyberPrekey.public_key,
    bob.kyberPrekey.signature,
    alice.sessionStore,
    alice.identityStore,
  );
}

async function encrypt(sender, recipient) {
  return encryptMessage(
    SYNTHETIC_MESSAGE,
    recipient.address,
    sender.address,
    sender.sessionStore,
    sender.identityStore,
  );
}

async function decrypt(recipient, sender, ciphertext) {
  const result = await decryptMessage(
    ciphertext.body,
    ciphertext.message_type,
    sender.address,
    recipient.address,
    recipient.sessionStore,
    recipient.identityStore,
    recipient.prekeyStore,
    recipient.signedPrekeyStore,
    recipient.kyberPrekeyStore,
  );
  invariant(
    equalBytes(result.plaintext, SYNTHETIC_MESSAGE),
    "plaintext mismatch",
  );
  return result;
}

function encodeBytes(bytes) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.slice(offset, offset + 0x8000));
  }
  return btoa(binary);
}

function decodeBytes(value) {
  return Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
}

async function snapshot(participant, peerAddress) {
  const prekeys = [];
  for (const key of participant.prekeys) {
    const record = await participant.prekeyStore.export_pre_key(key.id);
    if (record) prekeys.push({ id: key.id, record: encodeBytes(record) });
  }
  const signedPrekey =
    await participant.signedPrekeyStore.export_signed_pre_key(
      participant.signedPrekey.id,
    );
  const kyberPrekey = await participant.kyberPrekeyStore.export_kyber_pre_key(
    participant.kyberPrekey.id,
  );
  const session = await participant.sessionStore.export_session(peerAddress);
  invariant(signedPrekey, "signed prekey missing from saved state");
  invariant(kyberPrekey, "Kyber prekey missing from saved state");
  invariant(session, "session missing from saved state");
  return {
    identity: encodeBytes(participant.identityKeyPair.serialize()),
    registration_id: participant.registrationId,
    session: encodeBytes(session),
    prekeys,
    signed_prekey: {
      id: participant.signedPrekey.id,
      record: encodeBytes(signedPrekey),
    },
    kyber_prekey: {
      id: participant.kyberPrekey.id,
      record: encodeBytes(kyberPrekey),
    },
    kyber_usage: encodeBytes(
      await participant.kyberPrekeyStore.export_kyber_usage(),
    ),
  };
}

async function restoreParticipant(name, saved, peerAddress) {
  const identityKeyPair = IdentityKeyPair.deserialize(
    decodeBytes(saved.identity),
  );
  const participant = {
    address: new ProtocolAddress(name, 1),
    identityKeyPair,
    identityStore: new InMemIdentityKeyStore(
      identityKeyPair,
      saved.registration_id,
    ),
    kyberPrekeyStore: new InMemKyberPreKeyStore(),
    prekeyStore: new InMemPreKeyStore(),
    registrationId: saved.registration_id,
    sessionStore: new InMemSessionStore(),
    signedPrekeyStore: new InMemSignedPreKeyStore(),
  };
  for (const key of saved.prekeys) {
    await participant.prekeyStore.import_pre_key(
      key.id,
      decodeBytes(key.record),
    );
  }
  await participant.signedPrekeyStore.import_signed_pre_key(
    saved.signed_prekey.id,
    decodeBytes(saved.signed_prekey.record),
  );
  await participant.kyberPrekeyStore.import_kyber_pre_key(
    saved.kyber_prekey.id,
    decodeBytes(saved.kyber_prekey.record),
  );
  await participant.kyberPrekeyStore.import_kyber_usage(
    decodeBytes(saved.kyber_usage),
  );
  await participant.sessionStore.import_session(
    peerAddress,
    decodeBytes(saved.session),
  );
  return participant;
}

function percentile(values, fraction) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.ceil(sorted.length * fraction) - 1];
}

function memoryBytes() {
  return performance.memory?.usedJSHeapSize ?? null;
}

function bundleBytes() {
  return performance
    .getEntriesByType("resource")
    .filter((entry) => entry.name.includes("/vendor/"))
    .reduce(
      (total, entry) =>
        total + (entry.transferSize || entry.encodedBodySize || 0),
      0,
    );
}

async function exchange(sender, recipient, observations, durations, sizes) {
  const start = performance.now();
  const ciphertext = await encrypt(sender, recipient);
  const encryptedAt = performance.now();
  const observation = observeSpqr(ciphertext);
  await decrypt(recipient, sender, ciphertext);
  durations.push(performance.now() - start);
  sizes.push({
    ciphertext: ciphertext.body.length,
    plaintext: SYNTHETIC_MESSAGE.length,
  });
  if (observation) {
    observations.push({
      ...observation,
      ciphertext_sha256: await sha256(ciphertext.body),
      encrypt_ms: encryptedAt - start,
    });
  }
  return ciphertext;
}

function safeError(error) {
  return { code: error?.code || "unknown", name: error?.name || "Error" };
}

async function saveSnapshots(alice, bob) {
  const saved = {
    alice: await snapshot(alice, bob.address),
    bob: await snapshot(bob, alice.address),
  };
  const serialized = JSON.stringify(saved);
  sessionStorage.setItem(SNAPSHOT_KEY, serialized);
  return { saved, bytes: new Blob([serialized]).size };
}

async function restoreSnapshots(saved) {
  const aliceAddress = new ProtocolAddress("alice-synthetic", 1);
  const bobAddress = new ProtocolAddress("bob-synthetic", 1);
  const alice = await restoreParticipant(
    "alice-synthetic",
    saved.alice,
    bobAddress,
  );
  const bob = await restoreParticipant(
    "bob-synthetic",
    saved.bob,
    aliceAddress,
  );
  return { alice, bob };
}

export async function runPrototype({
  benchmarkRuns = 30,
  epochTarget = 2,
} = {}) {
  const longTasks = [];
  const observer =
    globalThis.PerformanceObserver?.supportedEntryTypes?.includes("longtask")
      ? new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) longTasks.push(entry.duration);
        })
      : null;
  observer?.observe({ entryTypes: ["longtask"] });
  const started = performance.now();
  const memoryBefore = memoryBytes();
  const memorySamples = memoryBefore === null ? [] : [memoryBefore];
  await init();
  let alice = await createParticipant("alice-synthetic", 1);
  let bob = await createParticipant("bob-synthetic", 1000);
  await establish(alice, bob);
  const handshake = await encrypt(alice, bob);
  invariant(
    handshake.message_type === message_type_pre_key(),
    "PQXDH prekey message missing",
  );
  const handshakeResult = await decrypt(bob, alice, handshake);
  invariant(
    handshakeResult.kyberPreKeyId !== undefined,
    "Kyber prekey was not consumed",
  );
  const coldLatency = performance.now() - started;

  const observations = [];
  const durations = [];
  const sizes = [
    { ciphertext: handshake.body.length, plaintext: SYNTHETIC_MESSAGE.length },
  ];
  const measuredExchange = async (sender, recipient) => {
    const ciphertext = await exchange(
      sender,
      recipient,
      observations,
      durations,
      sizes,
    );
    const memory = memoryBytes();
    if (memory !== null) memorySamples.push(memory);
    return ciphertext;
  };
  await measuredExchange(bob, alice);

  let attempts = 0;
  while (new Set(observations.map((entry) => entry.epoch)).size < epochTarget) {
    invariant(attempts++ < 2048, "two SPQR epochs were not observed");
    await measuredExchange(alice, bob);
    await measuredExchange(bob, alice);
  }

  const persisted = await saveSnapshots(alice, bob);
  ({ alice, bob } = await restoreSnapshots(persisted.saved));
  await measuredExchange(alice, bob);
  await measuredExchange(bob, alice);

  const dropped = await encrypt(alice, bob);
  sizes.push({
    ciphertext: dropped.body.length,
    plaintext: SYNTHETIC_MESSAGE.length,
  });
  await measuredExchange(alice, bob);

  const reorderedFirst = await encrypt(alice, bob);
  const reorderedSecond = await encrypt(alice, bob);
  await decrypt(bob, alice, reorderedSecond);
  await decrypt(bob, alice, reorderedFirst);
  sizes.push(
    {
      ciphertext: reorderedFirst.body.length,
      plaintext: SYNTHETIC_MESSAGE.length,
    },
    {
      ciphertext: reorderedSecond.body.length,
      plaintext: SYNTHETIC_MESSAGE.length,
    },
  );
  let replay;
  try {
    await decrypt(bob, alice, reorderedFirst);
    replay = { rejected: false };
  } catch (error) {
    replay = { rejected: true, ...safeError(error) };
  }
  invariant(replay.rejected, "replay was accepted");

  while (durations.length < benchmarkRuns) {
    await measuredExchange(alice, bob);
    await measuredExchange(bob, alice);
  }
  await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  observer?.disconnect();
  const memoryAfter = memoryBytes();
  if (memoryAfter !== null) memorySamples.push(memoryAfter);
  const epochs = [...new Set(observations.map((entry) => entry.epoch))].sort(
    (left, right) => left - right,
  );
  const ciphertextBytes = sizes.reduce((sum, item) => sum + item.ciphertext, 0);
  const plaintextBytes = sizes.reduce((sum, item) => sum + item.plaintext, 0);
  return {
    schema_version: 1,
    synthetic_only: true,
    algorithm: "round-3 Kyber1024 PQXDH plus SPQR v1",
    fips_203_ml_kem: false,
    browser: navigator.userAgent,
    secure_context: isSecureContext,
    cross_origin_isolated: globalThis.crossOriginIsolated === true,
    pqxdh: {
      kyber_prekey_consumed: true,
      message_type: handshake.message_type,
    },
    bidirectional: true,
    state_reload: {
      session_continuation_passed: true,
      identity_trust_persistence: "unsupported-by-wrapper",
      acceptance_passed: false,
      session_storage_bytes: persisted.bytes,
    },
    faults: {
      dropped_message_recovered: true,
      reordered_messages_recovered: true,
      replay,
    },
    spqr: {
      wire_version: 1,
      observed_epochs: epochs,
      observations: observations.filter(
        (entry, index, all) =>
          all.findIndex((candidate) => candidate.epoch === entry.epoch) ===
          index,
      ),
    },
    benchmarks: {
      timing_runs: durations.length,
      cold_latency_ms: coldLatency,
      warm_latency_p50_ms: percentile(durations, 0.5),
      warm_latency_p95_ms: percentile(durations, 0.95),
      bundle_transfer_bytes: bundleBytes(),
      js_heap_delta_bytes:
        memoryBefore === null || memoryAfter === null
          ? null
          : memoryAfter - memoryBefore,
      peak_memory_bytes: memorySamples.length
        ? Math.max(...memorySamples)
        : null,
      peak_memory_note: memorySamples.length
        ? "sampled usedJSHeapSize; confirm with browser tooling"
        : "requires browser-specific external measurement",
      longest_main_thread_task_ms: longTasks.length
        ? Math.max(...longTasks)
        : null,
      ciphertext_amplification: ciphertextBytes / plaintextBytes,
    },
    csp: document.location.search.includes("csp=conversation")
      ? "conversation"
      : "isolated-wasm-evaluation",
    reference_peer: { status: "not_run" },
  };
}

export async function resumePersistedPrototype() {
  await init();
  const serialized = sessionStorage.getItem(SNAPSHOT_KEY);
  if (!serialized) return { resumed: false, reason: "state-unavailable" };
  const { alice, bob } = await restoreSnapshots(JSON.parse(serialized));
  const ciphertext = await encrypt(alice, bob);
  await decrypt(bob, alice, ciphertext);
  return { resumed: true, ciphertext_sha256: await sha256(ciphertext.body) };
}

export function probeStorage() {
  try {
    sessionStorage.setItem(
      "hushline-pq-prototype-storage-probe",
      "x".repeat(4096),
    );
    sessionStorage.removeItem("hushline-pq-prototype-storage-probe");
    return { available: true };
  } catch (error) {
    return { available: false, fail_closed: true, ...safeError(error) };
  }
}

window.pqPrototype = { probeStorage, resumePersistedPrototype, runPrototype };

document.querySelector("#run")?.addEventListener("click", async () => {
  const status = document.querySelector("#status");
  const result = document.querySelector("#result");
  status.textContent = "Running…";
  try {
    const report = await runPrototype();
    result.textContent = JSON.stringify(report, null, 2);
    status.textContent = "Synthetic scenario complete.";
  } catch (error) {
    result.textContent = JSON.stringify(safeError(error), null, 2);
    status.textContent = "Synthetic scenario failed.";
  }
});

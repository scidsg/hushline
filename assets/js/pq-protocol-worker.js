import init, {
  IdentityKeyPair,
  InMemIdentityKeyStore,
  InMemKyberPreKeyStore,
  InMemPreKeyStore,
  InMemSessionStore,
  InMemSignedPreKeyStore,
  PrivateKey,
  ProtocolAddress,
  PublicKey,
  decryptMessage,
  encryptMessage,
  generateKyberPreKey,
  generatePreKeys,
  generateRegistrationId,
  generateSignedPreKey,
  message_type_signal,
  processPreKeyBundle,
} from "@getmaapp/signal-wasm";

const PROTOCOL = "HL-PQCHAT-1";
const SUITE = "SIGNAL-PQXDH3-KYBER1024-SPQR1";
const STATE_VERSION = 1;
const TRANSPORT_FRAME_VERSION = 1;
const MAX_CIPHERTEXT_BYTES = 200000;
const MAX_KEY_ID = 0xffffffff;
const MAX_PLAINTEXT_BYTES = 50000;
const MAX_PREKEYS = 100;
const MAX_OBSERVED_EPOCHS = 2;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const CONTEXT_FIELDS = [
  "account_recipient_id",
  "archive_epoch",
  "capability_offer",
  "capability_selection",
  "conversation_id",
  "device_recipient_id",
  "key_version",
  "message_id",
  "protocol",
  "purpose",
  "recipient_membership_sequence",
  "sender_account_id",
  "sender_device_id",
  "sender_membership_sequence",
  "suite",
];
const encoder = new TextEncoder();
const decoder = new TextDecoder();
let initialized;

class ProtocolError extends Error {
  constructor(code) {
    super(code);
    this.name = "ProtocolError";
    this.code = code;
  }
}

function fail(code) {
  throw new ProtocolError(code);
}

function canonicalStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalStringify(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function bytesToBase64Url(bytes) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/u, "");
}

function base64UrlToBytes(value) {
  if (typeof value !== "string" || !value || value.includes("=")) {
    fail("MALFORMED_WIRE");
  }
  try {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
    const bytes = Uint8Array.from(binary, (character) =>
      character.charCodeAt(0),
    );
    if (bytesToBase64Url(bytes) !== value) {
      fail("MALFORMED_WIRE");
    }
    return bytes;
  } catch (error) {
    if (error instanceof ProtocolError) throw error;
    fail("MALFORMED_WIRE");
  }
}

async function sha256Hex(bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

function requireInteger(value, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail("MALFORMED_WIRE");
  }
  return value;
}

function requireText(value) {
  if (typeof value !== "string" || !value) fail("MALFORMED_WIRE");
  return value;
}

function hasExactFields(value, fields) {
  return (
    value &&
    typeof value === "object" &&
    JSON.stringify(Object.keys(value).sort()) ===
      JSON.stringify([...fields].sort())
  );
}

function assertContext(context) {
  if (
    !context ||
    typeof context !== "object" ||
    JSON.stringify(Object.keys(context).sort()) !==
      JSON.stringify([...CONTEXT_FIELDS].sort())
  ) {
    fail("MALFORMED_WIRE");
  }
  if (
    context.protocol !== PROTOCOL ||
    context.suite !== SUITE ||
    context.purpose !== "transport" ||
    context.archive_epoch !== 0 ||
    context.capability_selection !== PROTOCOL ||
    JSON.stringify(context.capability_offer) !== JSON.stringify([PROTOCOL])
  ) {
    fail("SUITE_MISMATCH");
  }
  for (const field of [
    "account_recipient_id",
    "conversation_id",
    "device_recipient_id",
    "message_id",
    "sender_account_id",
    "sender_device_id",
  ]) {
    requireText(context[field]);
    if (!UUID.test(context[field])) fail("MALFORMED_WIRE");
  }
  for (const field of [
    "key_version",
    "recipient_membership_sequence",
    "sender_membership_sequence",
  ]) {
    requireInteger(context[field], 1);
  }
  return canonicalStringify(context);
}

function assertContextAddresses(context, localAddress, remoteAddress, sending) {
  const senderName = `${context.sender_account_id}.${context.sender_device_id}`;
  const recipientName = `${context.account_recipient_id}.${context.device_recipient_id}`;
  const expectedLocal = sending ? senderName : recipientName;
  const expectedRemote = sending ? recipientName : senderName;
  if (
    localAddress?.name !== expectedLocal ||
    remoteAddress?.name !== expectedRemote
  ) {
    fail("AUTHENTICATION_FAILED");
  }
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
  fail("MALFORMED_WIRE");
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
      if (end > bytes.length) fail("MALFORMED_WIRE");
      if (field === wantedField) return bytes.slice(offset, end);
      offset = end;
    } else if (wire === 5) {
      offset += 4;
    } else {
      fail("MALFORMED_WIRE");
    }
    if (offset > bytes.length) fail("MALFORMED_WIRE");
  }
  return null;
}

function observeSpqr(messageType, body) {
  if (messageType !== message_type_signal()) return null;
  if (!(body instanceof Uint8Array) || body.length <= 9) {
    fail("MALFORMED_WIRE");
  }
  const payload = protobufBytesField(body.slice(1, -8), 5);
  if (!payload) return null;
  if (payload.length < 4 || payload[0] !== 1) fail("SUITE_MISMATCH");
  const epoch = readVarint(payload, 1);
  const messageIndex = readVarint(payload, epoch.offset);
  const messageTypeValue = payload[messageIndex.offset];
  if (epoch.value < 1 || messageTypeValue > 6) fail("MALFORMED_WIRE");
  return {
    epoch: epoch.value,
    messageIndex: messageIndex.value,
    messageType: messageTypeValue,
    wireVersion: 1,
  };
}

function encodeTransportCiphertext(messageType, body) {
  requireInteger(messageType, 0, 255);
  if (!(body instanceof Uint8Array) || body.length + 2 > MAX_CIPHERTEXT_BYTES) {
    fail("MALFORMED_WIRE");
  }
  const framed = new Uint8Array(body.length + 2);
  framed[0] = TRANSPORT_FRAME_VERSION;
  framed[1] = messageType;
  framed.set(body, 2);
  return bytesToBase64Url(framed);
}

function decodeTransportCiphertext(value) {
  if (
    typeof value !== "string" ||
    value.length > Math.ceil((MAX_CIPHERTEXT_BYTES * 4) / 3)
  ) {
    fail("MALFORMED_WIRE");
  }
  const framed = base64UrlToBytes(value);
  if (
    framed.length < 3 ||
    framed.length > MAX_CIPHERTEXT_BYTES ||
    framed[0] !== TRANSPORT_FRAME_VERSION
  ) {
    fail("MALFORMED_WIRE");
  }
  return { body: framed.slice(2), messageType: framed[1] };
}

function address(value) {
  if (!hasExactFields(value, ["deviceId", "name"])) {
    fail("MALFORMED_WIRE");
  }
  return new ProtocolAddress(
    requireText(value?.name),
    requireInteger(value?.deviceId, 1, 127),
  );
}

async function ensureInitialized() {
  initialized ||= init();
  await initialized;
}

async function createDevice(args) {
  const prekeyCount = requireInteger(args?.prekeyCount, 1, MAX_PREKEYS);
  const prekeyStart = requireInteger(
    args?.prekeyStart,
    1,
    MAX_KEY_ID - prekeyCount + 1,
  );
  const signedPrekeyId = requireInteger(args?.signedPrekeyId, 1, MAX_KEY_ID);
  const localAddress = {
    name: requireText(args?.address?.name),
    deviceId: requireInteger(args?.address?.deviceId, 1, 127),
  };
  const privateKey = PrivateKey.generate();
  const identityKeyPair = new IdentityKeyPair(
    privateKey.getPublicKey(),
    privateKey,
  );
  const registrationId = generateRegistrationId();
  const identityStore = new InMemIdentityKeyStore(
    identityKeyPair,
    registrationId,
  );
  const prekeyStore = new InMemPreKeyStore();
  const signedPrekeyStore = new InMemSignedPreKeyStore();
  const kyberPrekeyStore = new InMemKyberPreKeyStore();
  const prekeys = await generatePreKeys(prekeyStart, prekeyCount, prekeyStore);
  const signedPrekey = await generateSignedPreKey(
    signedPrekeyId,
    identityKeyPair,
    signedPrekeyStore,
  );
  const kyberPrekeys = [];
  for (const prekey of prekeys) {
    kyberPrekeys.push(
      await generateKyberPreKey(prekey.id, identityKeyPair, kyberPrekeyStore),
    );
  }
  const participant = {
    identityKeyPair,
    identityStore,
    kyberPrekeys,
    kyberPrekeyStore,
    localAddress,
    observedEpochs: [],
    peer: null,
    peerIdentityKey: null,
    peerMembershipSequence: null,
    peerSignedPrekeyId: null,
    prekeys,
    prekeyStore,
    registrationId,
    sessionStore: new InMemSessionStore(),
    signedPrekey,
    signedPrekeyStore,
    handshakeComplete: false,
  };
  return {
    publicBundle: {
      address: localAddress,
      identityKey: bytesToBase64Url(privateKey.getPublicKey().serialize()),
      prekeys: prekeys.map((prekey, index) => ({
        id: prekey.id,
        kyberPrekey: {
          id: kyberPrekeys[index].id,
          publicKey: bytesToBase64Url(
            kyberPrekeys[index].public_key.serialize(),
          ),
          signature: bytesToBase64Url(kyberPrekeys[index].signature),
        },
        publicKey: bytesToBase64Url(prekey.public_key.serialize()),
      })),
      protocol: PROTOCOL,
      registrationId,
      signedPrekey: {
        id: signedPrekey.id,
        publicKey: bytesToBase64Url(signedPrekey.public_key.serialize()),
        signature: bytesToBase64Url(signedPrekey.signature),
      },
      suite: SUITE,
    },
    state: await snapshot(participant),
  };
}

async function restore(state, requestedPeer = null) {
  if (
    !state ||
    state.version !== STATE_VERSION ||
    state.protocol !== PROTOCOL ||
    state.suite !== SUITE ||
    !Array.isArray(state.prekeys) ||
    state.prekeys.length > MAX_PREKEYS ||
    !Array.isArray(state.kyberPrekeys) ||
    state.kyberPrekeys.length > MAX_PREKEYS
  ) {
    fail("STATE_CONFLICT");
  }
  const identityKeyPair = IdentityKeyPair.deserialize(
    base64UrlToBytes(state.identity),
  );
  const participant = {
    identityKeyPair,
    identityStore: new InMemIdentityKeyStore(
      identityKeyPair,
      requireInteger(state.registrationId, 1, 16380),
    ),
    kyberPrekeys: state.kyberPrekeys.map((prekey) => ({
      id: requireInteger(prekey.id, 1, MAX_KEY_ID),
    })),
    kyberPrekeyStore: new InMemKyberPreKeyStore(),
    localAddress: state.localAddress,
    observedEpochs: Array.isArray(state.observedEpochs)
      ? state.observedEpochs.map((epoch) => requireInteger(epoch, 1))
      : [],
    peer: state.peer,
    peerIdentityKey: state.peerIdentityKey,
    peerMembershipSequence: state.peerMembershipSequence,
    peerSignedPrekeyId: state.peerSignedPrekeyId,
    prekeys: state.prekeys.map((prekey) => ({
      id: requireInteger(prekey.id, 1, MAX_KEY_ID),
    })),
    prekeyStore: new InMemPreKeyStore(),
    registrationId: requireInteger(state.registrationId, 1, 16380),
    sessionStore: new InMemSessionStore(),
    signedPrekey: {
      id: requireInteger(state.signedPrekey?.id, 1, MAX_KEY_ID),
    },
    signedPrekeyStore: new InMemSignedPreKeyStore(),
    handshakeComplete: state.handshakeComplete === true,
  };
  if (
    participant.prekeys.length !== participant.kyberPrekeys.length ||
    participant.prekeys.some(
      (prekey, index) => prekey.id !== participant.kyberPrekeys[index].id,
    )
  ) {
    fail("STATE_CONFLICT");
  }
  address(participant.localAddress);
  if (participant.observedEpochs.length > MAX_OBSERVED_EPOCHS) {
    fail("STATE_CONFLICT");
  }
  if (
    participant.peer &&
    ((participant.peerIdentityKey !== null &&
      typeof participant.peerIdentityKey !== "string") ||
      (participant.peerMembershipSequence !== null &&
        (!Number.isSafeInteger(participant.peerMembershipSequence) ||
          participant.peerMembershipSequence < 1)) ||
      (participant.peerSignedPrekeyId !== null &&
        (!Number.isSafeInteger(participant.peerSignedPrekeyId) ||
          participant.peerSignedPrekeyId < 1 ||
          participant.peerSignedPrekeyId > MAX_KEY_ID)))
  ) {
    fail("STATE_CONFLICT");
  }
  if (
    requestedPeer &&
    participant.peer &&
    canonicalStringify(requestedPeer) !== canonicalStringify(participant.peer)
  ) {
    fail("STATE_CONFLICT");
  }
  participant.peer ||= requestedPeer;
  for (const prekey of state.prekeys) {
    await participant.prekeyStore.import_pre_key(
      prekey.id,
      base64UrlToBytes(prekey.record),
    );
  }
  await participant.signedPrekeyStore.import_signed_pre_key(
    state.signedPrekey.id,
    base64UrlToBytes(state.signedPrekey.record),
  );
  for (const prekey of state.kyberPrekeys) {
    await participant.kyberPrekeyStore.import_kyber_pre_key(
      prekey.id,
      base64UrlToBytes(prekey.record),
    );
  }
  await participant.kyberPrekeyStore.import_kyber_usage(
    base64UrlToBytes(state.kyberUsage),
  );
  if (state.session) {
    if (!participant.peer) fail("STATE_CONFLICT");
    await participant.sessionStore.import_session(
      address(participant.peer),
      base64UrlToBytes(state.session),
    );
  }
  return participant;
}

async function snapshot(participant) {
  const prekeys = [];
  for (const prekey of participant.prekeys) {
    const record = await participant.prekeyStore.export_pre_key(prekey.id);
    if (record) {
      prekeys.push({ id: prekey.id, record: bytesToBase64Url(record) });
    }
  }
  const signedPrekey =
    await participant.signedPrekeyStore.export_signed_pre_key(
      participant.signedPrekey.id,
    );
  const kyberPrekeys = [];
  for (const prekey of prekeys) {
    const record = await participant.kyberPrekeyStore.export_kyber_pre_key(
      prekey.id,
    );
    if (record) {
      kyberPrekeys.push({ id: prekey.id, record: bytesToBase64Url(record) });
    }
  }
  if (!signedPrekey || kyberPrekeys.length !== prekeys.length) {
    fail("STATE_CONFLICT");
  }
  let session = null;
  if (participant.peer) {
    const exported = await participant.sessionStore.export_session(
      address(participant.peer),
    );
    session = exported ? bytesToBase64Url(exported) : null;
  }
  return {
    handshakeComplete: participant.handshakeComplete,
    identity: bytesToBase64Url(participant.identityKeyPair.serialize()),
    kyberPrekeys,
    kyberUsage: bytesToBase64Url(
      await participant.kyberPrekeyStore.export_kyber_usage(),
    ),
    localAddress: participant.localAddress,
    observedEpochs: [...new Set(participant.observedEpochs)].sort(
      (left, right) => left - right,
    ),
    peer: participant.peer,
    peerIdentityKey: participant.peerIdentityKey,
    peerMembershipSequence: participant.peerMembershipSequence,
    peerSignedPrekeyId: participant.peerSignedPrekeyId,
    prekeys,
    protocol: PROTOCOL,
    registrationId: participant.registrationId,
    session,
    signedPrekey: {
      id: participant.signedPrekey.id,
      record: bytesToBase64Url(signedPrekey),
    },
    suite: SUITE,
    version: STATE_VERSION,
  };
}

function publicKey(value) {
  return PublicKey.deserialize(base64UrlToBytes(value));
}

async function beginSession(args) {
  const remote = args?.remoteBundle;
  if (
    !hasExactFields(remote, [
      "address",
      "identityKey",
      "kyberPrekey",
      "membershipSequence",
      "prekey",
      "protocol",
      "registrationId",
      "signedPrekey",
      "suite",
    ]) ||
    !hasExactFields(remote?.prekey, ["id", "publicKey"]) ||
    !hasExactFields(remote?.signedPrekey, ["id", "publicKey", "signature"]) ||
    !hasExactFields(remote?.kyberPrekey, ["id", "publicKey", "signature"])
  ) {
    fail("MALFORMED_WIRE");
  }
  if (
    remote?.protocol !== PROTOCOL ||
    remote?.suite !== SUITE ||
    !remote.prekey ||
    !remote.signedPrekey ||
    !remote.kyberPrekey
  ) {
    fail("SUITE_MISMATCH");
  }
  const identityKey = requireText(remote.identityKey);
  const membershipSequence = requireInteger(remote.membershipSequence, 1);
  const signedPrekeyId = requireInteger(remote.signedPrekey.id, 1, MAX_KEY_ID);
  const prekeyId = requireInteger(remote.prekey.id, 1, MAX_KEY_ID);
  const kyberPrekeyId = requireInteger(remote.kyberPrekey.id, 1, MAX_KEY_ID);
  if (prekeyId !== kyberPrekeyId) fail("MALFORMED_WIRE");
  const participant = await restore(args.state, remote.address);
  if (args.state.session) {
    if (args.replaceExisting !== true) fail("STATE_CONFLICT");
    if (
      participant.peerIdentityKey !== null &&
      identityKey !== participant.peerIdentityKey
    ) {
      fail("AUTHENTICATION_FAILED");
    }
    if (
      participant.peerMembershipSequence !== null &&
      membershipSequence <= participant.peerMembershipSequence
    ) {
      fail("STALE_MEMBERSHIP");
    }
    participant.sessionStore = new InMemSessionStore();
    participant.handshakeComplete = false;
    participant.observedEpochs = [];
  }
  await processPreKeyBundle(
    address(remote.address),
    address(participant.localAddress),
    requireInteger(remote.registrationId, 1, 16380),
    publicKey(identityKey),
    signedPrekeyId,
    publicKey(remote.signedPrekey.publicKey),
    base64UrlToBytes(remote.signedPrekey.signature),
    prekeyId,
    publicKey(remote.prekey.publicKey),
    kyberPrekeyId,
    publicKey(remote.kyberPrekey.publicKey),
    base64UrlToBytes(remote.kyberPrekey.signature),
    participant.sessionStore,
    participant.identityStore,
  );
  participant.peer = remote.address;
  participant.peerIdentityKey = identityKey;
  participant.peerMembershipSequence = membershipSequence;
  participant.peerSignedPrekeyId = signedPrekeyId;
  return {
    state: await snapshot(participant),
    status: protocolStatus(participant),
  };
}

function addObservation(participant, observation) {
  if (observation && !participant.observedEpochs.includes(observation.epoch)) {
    participant.observedEpochs.push(observation.epoch);
    participant.observedEpochs =
      participant.observedEpochs.slice(-MAX_OBSERVED_EPOCHS);
  }
}

function protocolStatus(participant) {
  const observedEpochs = [...new Set(participant.observedEpochs)].sort(
    (left, right) => left - right,
  );
  return {
    continuousPq: participant.handshakeComplete && observedEpochs.length >= 2,
    handshakeComplete: participant.handshakeComplete,
    observedEpochCount: observedEpochs.length,
    observedEpochs,
    protocol: PROTOCOL,
    suite: SUITE,
  };
}

async function ratchetEncrypt(args) {
  const participant = await restore(args.state);
  if (!participant.peer) fail("STATE_CONFLICT");
  const context = assertContext(args.context);
  assertContextAddresses(
    args.context,
    participant.localAddress,
    participant.peer,
    true,
  );
  if (
    args.context.recipient_membership_sequence !==
      participant.peerMembershipSequence ||
    args.context.key_version !== participant.peerSignedPrekeyId
  ) {
    fail("STALE_MEMBERSHIP");
  }
  const plaintext = requireText(args.plaintext);
  const plaintextBytes = encoder.encode(plaintext);
  if (plaintextBytes.length > MAX_PLAINTEXT_BYTES) fail("MALFORMED_WIRE");
  const payload = encoder.encode(
    canonicalStringify({
      context_sha256: await sha256Hex(encoder.encode(context)),
      plaintext: bytesToBase64Url(plaintextBytes),
      protocol: PROTOCOL,
      suite: SUITE,
      v: 1,
    }),
  );
  const encrypted = await encryptMessage(
    payload,
    address(participant.peer),
    address(participant.localAddress),
    participant.sessionStore,
    participant.identityStore,
  );
  const observation = observeSpqr(encrypted.message_type, encrypted.body);
  addObservation(participant, observation);
  return {
    ciphertext: encodeTransportCiphertext(
      encrypted.message_type,
      encrypted.body,
    ),
    messageType: encrypted.message_type,
    observation,
    state: await snapshot(participant),
    status: protocolStatus(participant),
  };
}

async function ratchetDecrypt(args) {
  const participant = await restore(args.state, args.senderAddress);
  const context = assertContext(args.context);
  assertContextAddresses(
    args.context,
    participant.localAddress,
    args.senderAddress,
    false,
  );
  if (args.context.key_version !== participant.signedPrekey.id) {
    fail("STALE_MEMBERSHIP");
  }
  if (participant.peerMembershipSequence === null) {
    participant.peerMembershipSequence =
      args.context.sender_membership_sequence;
  } else {
    if (
      args.context.sender_membership_sequence !==
      participant.peerMembershipSequence
    ) {
      fail("STALE_MEMBERSHIP");
    }
  }
  const { body, messageType } = decodeTransportCiphertext(args.ciphertext);
  const observation = observeSpqr(messageType, body);
  const result = await decryptMessage(
    body,
    messageType,
    address(args.senderAddress),
    address(participant.localAddress),
    participant.sessionStore,
    participant.identityStore,
    participant.prekeyStore,
    participant.signedPrekeyStore,
    participant.kyberPrekeyStore,
  );
  let envelope;
  try {
    envelope = JSON.parse(decoder.decode(result.plaintext));
  } catch (error) {
    fail("AUTHENTICATION_FAILED");
  }
  if (
    envelope?.v !== 1 ||
    envelope.protocol !== PROTOCOL ||
    envelope.suite !== SUITE ||
    envelope.context_sha256 !== (await sha256Hex(encoder.encode(context)))
  ) {
    fail("AUTHENTICATION_FAILED");
  }
  participant.peer = args.senderAddress;
  participant.handshakeComplete ||=
    result.kyberPreKeyId !== undefined || messageType === message_type_signal();
  addObservation(participant, observation);
  return {
    plaintext: decoder.decode(base64UrlToBytes(envelope.plaintext)),
    observation,
    state: await snapshot(participant),
    status: protocolStatus(participant),
  };
}

async function dispatch(operation, args) {
  await ensureInitialized();
  if (operation === "createDevice") return createDevice(args);
  if (operation === "beginSession") return beginSession(args);
  if (operation === "ratchetEncrypt") return ratchetEncrypt(args);
  if (operation === "ratchetDecrypt") return ratchetDecrypt(args);
  fail("MALFORMED_WIRE");
}

function safeCode(error) {
  if (error instanceof ProtocolError) return error.code;
  const message = String(error?.message || "").toLowerCase();
  if (message.includes("duplicate") || message.includes("already")) {
    return "PREKEY_REPLAY";
  }
  if (
    message.includes("ciphertext") ||
    message.includes("decrypt") ||
    message.includes("invalid") ||
    message.includes("signature")
  ) {
    return "AUTHENTICATION_FAILED";
  }
  return "INTERNAL_ERROR";
}

self.addEventListener("message", async (event) => {
  const id = event.data?.id;
  if (!Number.isSafeInteger(id)) return;
  try {
    const result = await dispatch(event.data.operation, event.data.args);
    self.postMessage({ id, ok: true, result });
  } catch (error) {
    self.postMessage({ id, ok: false, error: safeCode(error) });
  }
});

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
import nacl from "../../node_modules/openpgp/dist/lightweight/nacl-fast.mjs";
import { ml_kem768 } from "../../node_modules/openpgp/dist/lightweight/noble_post_quantum.mjs";
import {
  q as sha3_256,
  w as shake256,
} from "../../node_modules/openpgp/dist/lightweight/sha512.mjs";

const PROTOCOL = "HL-PQCHAT-1";
const SUITE = "SIGNAL-PQXDH3-KYBER1024-SPQR1";
const ARCHIVE_SUITE = "MLKEM768-X25519-HKDF-SHA256-AES256GCM";
const STATE_VERSION = 1;
const TRANSPORT_FRAME_VERSION = 1;
const MAX_CIPHERTEXT_BYTES = 200000;
const MAX_KEY_ID = 0xffffffff;
const MAX_PLAINTEXT_BYTES = 50000;
const MAX_PREKEYS = 100;
const MAX_OBSERVED_EPOCHS = 2;
const ARCHIVE_PUBLIC_BYTES = 1216;
const ARCHIVE_PRIVATE_BYTES = 32;
const ARCHIVE_ENCAPSULATION_BYTES = 1120;
const MLKEM_PUBLIC_BYTES = 1184;
const MLKEM_CIPHERTEXT_BYTES = 1088;
const ARCHIVE_TAG_BYTES = 16;
const MAX_ARCHIVE_CIPHERTEXT_BYTES =
  ARCHIVE_ENCAPSULATION_BYTES + ARCHIVE_TAG_BYTES + MAX_PLAINTEXT_BYTES;
const ARCHIVE_WRAP_LABEL = "HushLine/HL-PQCHAT-1/archive-private-key-wrap/v1";
const ARCHIVE_SEAL_LABEL = "HushLine/HL-PQCHAT-1/archive-seal/v1";
const XWING_LABEL = new Uint8Array([0x5c, 0x2e, 0x2f, 0x2f, 0x5e, 0x5c]);
const HPKE_SUITE_ID = new Uint8Array([
  0x48, 0x50, 0x4b, 0x45, 0x64, 0x7a, 0x00, 0x01, 0x00, 0x02,
]);
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

function concatBytes(...values) {
  const length = values.reduce((total, value) => total + value.length, 0);
  const result = new Uint8Array(length);
  let offset = 0;
  for (const value of values) {
    result.set(value, offset);
    offset += value.length;
  }
  return result;
}

function integerBytes(value, length) {
  requireInteger(value, 0, 2 ** (8 * length) - 1);
  const bytes = new Uint8Array(length);
  for (let offset = length - 1; offset >= 0; offset -= 1) {
    bytes[offset] = value & 0xff;
    value = Math.floor(value / 256);
  }
  return bytes;
}

function randomBytes(length) {
  return crypto.getRandomValues(new Uint8Array(length));
}

function requireBytes(value, length) {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/u.test(value)) {
    fail("MALFORMED_WIRE");
  }
  const bytes = base64UrlToBytes(value);
  if (bytes.length !== length || bytesToBase64Url(bytes) !== value) {
    fail("MALFORMED_WIRE");
  }
  return bytes;
}

async function sha256Bytes(value) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", value));
}

async function hmacSha256(key, value) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key,
    { hash: "SHA-256", name: "HMAC" },
    false,
    ["sign"],
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, value));
}

async function hkdfExtract(salt, inputKeyMaterial) {
  return hmacSha256(salt.length ? salt : new Uint8Array(32), inputKeyMaterial);
}

async function hkdfExpand(pseudorandomKey, info, length) {
  if (length > 255 * 32) fail("MALFORMED_WIRE");
  const output = new Uint8Array(length);
  let previous = new Uint8Array();
  let offset = 0;
  for (let counter = 1; offset < length; counter += 1) {
    previous = await hmacSha256(
      pseudorandomKey,
      concatBytes(previous, info, new Uint8Array([counter])),
    );
    const available = Math.min(previous.length, length - offset);
    output.set(previous.subarray(0, available), offset);
    offset += available;
  }
  previous.fill(0);
  return output;
}

async function labeledExtract(salt, label, inputKeyMaterial) {
  return hkdfExtract(
    salt,
    concatBytes(
      encoder.encode("HPKE-v1"),
      HPKE_SUITE_ID,
      encoder.encode(label),
      inputKeyMaterial,
    ),
  );
}

async function labeledExpand(pseudorandomKey, label, info, length) {
  return hkdfExpand(
    pseudorandomKey,
    concatBytes(
      integerBytes(length, 2),
      encoder.encode("HPKE-v1"),
      HPKE_SUITE_ID,
      encoder.encode(label),
      info,
    ),
    length,
  );
}

async function hpkeKeySchedule(sharedSecret, info) {
  const empty = new Uint8Array();
  const pskIdHash = await labeledExtract(empty, "psk_id_hash", empty);
  const infoHash = await labeledExtract(empty, "info_hash", info);
  const context = concatBytes(new Uint8Array([0]), pskIdHash, infoHash);
  const secret = await labeledExtract(sharedSecret, "secret", empty);
  let key;
  try {
    key = await labeledExpand(secret, "key", context, 32);
    return {
      key,
      nonce: await labeledExpand(secret, "base_nonce", context, 12),
    };
  } catch (error) {
    key?.fill(0);
    throw error;
  } finally {
    secret.fill(0);
  }
}

function assertArchiveContext(context) {
  if (
    !context ||
    typeof context !== "object" ||
    JSON.stringify(Object.keys(context).sort()) !==
      JSON.stringify([...CONTEXT_FIELDS].sort())
  ) {
    fail("MALFORMED_WIRE");
  }
  if (context.protocol !== PROTOCOL || context.suite !== ARCHIVE_SUITE) {
    fail("SUITE_MISMATCH");
  }
  if (
    context.purpose !== "archive" ||
    context.capability_selection !== PROTOCOL ||
    JSON.stringify(context.capability_offer) !== JSON.stringify([PROTOCOL]) ||
    context.device_recipient_id !== "00000000-0000-0000-0000-000000000000"
  ) {
    fail("AUTHENTICATION_FAILED");
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
    "archive_epoch",
    "key_version",
    "recipient_membership_sequence",
    "sender_membership_sequence",
  ]) {
    requireInteger(context[field], 1);
  }
  if (context.key_version !== context.archive_epoch) {
    fail("STALE_MEMBERSHIP");
  }
  return canonicalStringify(context);
}

function archiveContext(value) {
  return encoder.encode(assertArchiveContext(value));
}

function expandArchivePrivateKey(seed) {
  if (!(seed instanceof Uint8Array) || seed.length !== ARCHIVE_PRIVATE_BYTES) {
    fail("MALFORMED_WIRE");
  }
  const expanded = shake256(seed, { dkLen: 96 });
  const pq = ml_kem768.keygen(expanded.subarray(0, 64));
  return {
    expanded,
    pq,
    traditionalPrivateKey: expanded.subarray(64, 96),
  };
}

function deriveArchivePublicKey(seed) {
  const privateKey = expandArchivePrivateKey(seed);
  try {
    return concatBytes(
      privateKey.pq.publicKey,
      nacl.scalarMult.base(privateKey.traditionalPrivateKey),
    );
  } finally {
    privateKey.expanded.fill(0);
    privateKey.pq.secretKey.fill(0);
  }
}

function assertNonzeroSharedSecret(value) {
  if (value.every((byte) => byte === 0)) fail("AUTHENTICATION_FAILED");
}

function archiveEncapsulate(publicKey) {
  if (publicKey.length !== ARCHIVE_PUBLIC_BYTES) fail("MALFORMED_WIRE");
  const pqPublicKey = publicKey.subarray(0, MLKEM_PUBLIC_BYTES);
  const traditionalPublicKey = publicKey.subarray(MLKEM_PUBLIC_BYTES);
  const ephemeralPrivateKey = randomBytes(32);
  let pq;
  let traditionalSharedSecret;
  try {
    pq = ml_kem768.encapsulate(pqPublicKey);
    const traditionalCiphertext = nacl.scalarMult.base(ephemeralPrivateKey);
    traditionalSharedSecret = nacl.scalarMult(
      ephemeralPrivateKey,
      traditionalPublicKey,
    );
    assertNonzeroSharedSecret(traditionalSharedSecret);
    return {
      encapsulation: concatBytes(pq.cipherText, traditionalCiphertext),
      sharedSecret: sha3_256(
        concatBytes(
          pq.sharedSecret,
          traditionalSharedSecret,
          traditionalCiphertext,
          traditionalPublicKey,
          XWING_LABEL,
        ),
      ),
    };
  } finally {
    ephemeralPrivateKey.fill(0);
    pq?.sharedSecret.fill(0);
    traditionalSharedSecret?.fill(0);
  }
}

function archiveDecapsulate(seed, encapsulation) {
  if (encapsulation.length !== ARCHIVE_ENCAPSULATION_BYTES) {
    fail("MALFORMED_WIRE");
  }
  const privateKey = expandArchivePrivateKey(seed);
  let pqSharedSecret;
  let traditionalSharedSecret;
  try {
    const traditionalPublicKey = nacl.scalarMult.base(
      privateKey.traditionalPrivateKey,
    );
    const traditionalCiphertext = encapsulation.subarray(
      MLKEM_CIPHERTEXT_BYTES,
    );
    pqSharedSecret = ml_kem768.decapsulate(
      encapsulation.subarray(0, MLKEM_CIPHERTEXT_BYTES),
      privateKey.pq.secretKey,
    );
    traditionalSharedSecret = nacl.scalarMult(
      privateKey.traditionalPrivateKey,
      traditionalCiphertext,
    );
    assertNonzeroSharedSecret(traditionalSharedSecret);
    return sha3_256(
      concatBytes(
        pqSharedSecret,
        traditionalSharedSecret,
        traditionalCiphertext,
        traditionalPublicKey,
        XWING_LABEL,
      ),
    );
  } finally {
    privateKey.expanded.fill(0);
    privateKey.pq.secretKey.fill(0);
    pqSharedSecret?.fill(0);
    traditionalSharedSecret?.fill(0);
  }
}

async function archiveWrapKey(accountRoot, accountId) {
  const salt = await sha256Bytes(encoder.encode(accountId));
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    accountRoot,
    "HKDF",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt,
      info: encoder.encode(ARCHIVE_WRAP_LABEL),
    },
    keyMaterial,
    { length: 256, name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
}

function archiveWrapContext(accountId, epoch, publicKeySha256) {
  return {
    account_id: accountId,
    archive_epoch: epoch,
    protocol: PROTOCOL,
    public_key_sha256: publicKeySha256,
    purpose: "archive-private-key",
    suite: ARCHIVE_SUITE,
    v: 1,
  };
}

async function wrapArchivePrivateKey({ accountId, accountRoot, epoch, seed }) {
  const publicKey = deriveArchivePublicKey(seed);
  const context = archiveWrapContext(
    accountId,
    epoch,
    await sha256Hex(publicKey),
  );
  const nonce = randomBytes(12);
  const wrappingKey = await archiveWrapKey(accountRoot, accountId);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      {
        additionalData: encoder.encode(canonicalStringify(context)),
        iv: nonce,
        name: "AES-GCM",
      },
      wrappingKey,
      seed,
    ),
  );
  return {
    encryptedPrivateKey: bytesToBase64Url(
      encoder.encode(
        canonicalStringify({
          ciphertext: bytesToBase64Url(ciphertext),
          context,
          nonce: bytesToBase64Url(nonce),
          v: 1,
        }),
      ),
    ),
    publicKey,
  };
}

async function unwrapArchivePrivateKey({
  accountId,
  accountRoot,
  encryptedPrivateKey,
  epoch,
  publicKey,
}) {
  let envelope;
  try {
    envelope = JSON.parse(
      decoder.decode(base64UrlToBytes(encryptedPrivateKey)),
    );
  } catch (error) {
    fail("MALFORMED_WIRE");
  }
  const expectedContext = archiveWrapContext(
    accountId,
    epoch,
    await sha256Hex(publicKey),
  );
  if (
    !hasExactFields(envelope, ["ciphertext", "context", "nonce", "v"]) ||
    envelope.v !== 1 ||
    canonicalStringify(envelope.context) !== canonicalStringify(expectedContext)
  ) {
    fail("AUTHENTICATION_FAILED");
  }
  try {
    const wrappingKey = await archiveWrapKey(accountRoot, accountId);
    const seed = new Uint8Array(
      await crypto.subtle.decrypt(
        {
          additionalData: encoder.encode(canonicalStringify(expectedContext)),
          iv: requireBytes(envelope.nonce, 12),
          name: "AES-GCM",
        },
        wrappingKey,
        base64UrlToBytes(envelope.ciphertext),
      ),
    );
    if (
      seed.length !== ARCHIVE_PRIVATE_BYTES ||
      bytesToBase64Url(deriveArchivePublicKey(seed)) !==
        bytesToBase64Url(publicKey)
    ) {
      seed.fill(0);
      fail("AUTHENTICATION_FAILED");
    }
    return seed;
  } catch (error) {
    if (error instanceof ProtocolError) throw error;
    fail("AUTHENTICATION_FAILED");
  }
}

async function createArchiveEpoch(args) {
  const accountId = requireText(args?.accountId);
  if (!UUID.test(accountId)) fail("MALFORMED_WIRE");
  const epoch = requireInteger(args?.epoch, 1);
  const accountRoot = requireBytes(args?.accountRoot, 32);
  const seed = randomBytes(ARCHIVE_PRIVATE_BYTES);
  try {
    const wrapped = await wrapArchivePrivateKey({
      accountId,
      accountRoot,
      epoch,
      seed,
    });
    return {
      encryptedPrivateKey: wrapped.encryptedPrivateKey,
      epoch,
      publicKey: bytesToBase64Url(wrapped.publicKey),
      suite: ARCHIVE_SUITE,
    };
  } finally {
    accountRoot.fill(0);
    seed.fill(0);
  }
}

async function archiveSeal(args) {
  const context = archiveContext(args?.context);
  const plaintext = requireText(args?.plaintext);
  const plaintextBytes = encoder.encode(plaintext);
  if (plaintextBytes.length > MAX_PLAINTEXT_BYTES) fail("MALFORMED_WIRE");
  const publicKey = requireBytes(args?.publicKey, ARCHIVE_PUBLIC_BYTES);
  let kem;
  try {
    kem = archiveEncapsulate(publicKey);
  } catch (error) {
    if (error instanceof ProtocolError) throw error;
    fail("AUTHENTICATION_FAILED");
  }
  let schedule;
  try {
    const info = concatBytes(
      encoder.encode(ARCHIVE_SEAL_LABEL),
      new Uint8Array([0]),
      await sha256Bytes(context),
    );
    schedule = await hpkeKeySchedule(kem.sharedSecret, info);
    const key = await crypto.subtle.importKey(
      "raw",
      schedule.key,
      "AES-GCM",
      false,
      ["encrypt"],
    );
    const ciphertext = new Uint8Array(
      await crypto.subtle.encrypt(
        { additionalData: context, iv: schedule.nonce, name: "AES-GCM" },
        key,
        plaintextBytes,
      ),
    );
    return bytesToBase64Url(concatBytes(kem.encapsulation, ciphertext));
  } finally {
    kem.sharedSecret.fill(0);
    schedule?.key.fill(0);
    schedule?.nonce.fill(0);
  }
}

async function archiveOpen(args) {
  const context = archiveContext(args?.context);
  if (
    typeof args?.ciphertext !== "string" ||
    args.ciphertext.length >
      Math.ceil((MAX_ARCHIVE_CIPHERTEXT_BYTES * 4) / 3) ||
    !/^[A-Za-z0-9_-]+$/u.test(args.ciphertext)
  ) {
    fail("MALFORMED_WIRE");
  }
  const stored = base64UrlToBytes(args?.ciphertext);
  if (
    bytesToBase64Url(stored) !== args.ciphertext ||
    stored.length < ARCHIVE_ENCAPSULATION_BYTES + ARCHIVE_TAG_BYTES ||
    stored.length > MAX_ARCHIVE_CIPHERTEXT_BYTES
  ) {
    fail("MALFORMED_WIRE");
  }
  const accountId = requireText(args?.accountId);
  const epoch = requireInteger(args?.epoch, 1);
  if (
    !UUID.test(accountId) ||
    args.context.account_recipient_id !== accountId ||
    args.context.archive_epoch !== epoch
  ) {
    fail("AUTHENTICATION_FAILED");
  }
  const publicKey = requireBytes(args?.publicKey, ARCHIVE_PUBLIC_BYTES);
  const accountRoot = requireBytes(args?.accountRoot, 32);
  let seed;
  try {
    seed = await unwrapArchivePrivateKey({
      accountId,
      accountRoot,
      encryptedPrivateKey: args?.encryptedPrivateKey,
      epoch,
      publicKey,
    });
    const sharedSecret = archiveDecapsulate(
      seed,
      stored.subarray(0, ARCHIVE_ENCAPSULATION_BYTES),
    );
    let schedule;
    try {
      const info = concatBytes(
        encoder.encode(ARCHIVE_SEAL_LABEL),
        new Uint8Array([0]),
        await sha256Bytes(context),
      );
      schedule = await hpkeKeySchedule(sharedSecret, info);
      const key = await crypto.subtle.importKey(
        "raw",
        schedule.key,
        "AES-GCM",
        false,
        ["decrypt"],
      );
      const plaintext = await crypto.subtle.decrypt(
        { additionalData: context, iv: schedule.nonce, name: "AES-GCM" },
        key,
        stored.subarray(ARCHIVE_ENCAPSULATION_BYTES),
      );
      return decoder.decode(plaintext);
    } finally {
      sharedSecret.fill(0);
      schedule?.key.fill(0);
      schedule?.nonce.fill(0);
    }
  } catch (error) {
    if (error instanceof ProtocolError) throw error;
    fail("AUTHENTICATION_FAILED");
  } finally {
    accountRoot.fill(0);
    seed?.fill(0);
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
  if (operation === "createArchiveEpoch") return createArchiveEpoch(args);
  if (operation === "archiveSeal") return archiveSeal(args);
  if (operation === "archiveOpen") return archiveOpen(args);
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

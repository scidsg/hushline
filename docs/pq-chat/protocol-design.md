# Hush Line PQ Account-Chat Protocol Design

Status: **Proposed for independent cryptographic review**<br>
Protocol: `HL-PQCHAT-1`<br>
Specification version: 1<br>
Decision gate: G3 of `scidsg/hushline#2365`<br>
Issue: `scidsg/hushline#2398`

This document is the implementable integration contract for the two-party
account-chat design. It does not enable production traffic or record human
approval. Implementations must fail closed if a required algorithm, binding,
copy, key, or transaction guarantee is unavailable. There is no classical-only
writer for an `HL-PQCHAT-1` conversation.

## Normative suite and provenance

`HL-PQCHAT-1` fixes the following profile. Algorithm substitution requires a
new protocol version and new fixtures.

<!-- prettier-ignore -->
| Role | Fixed construction and revision |
| --- | --- |
| Online session | Signal PQXDH revision 3 and Triple Ratchet/SPQR v1 as implemented by `@getmaapp/signal-wasm` 0.6.6, source `0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd`, wrapping `signalapp/libsignal` 0.101.0 at `b056faa6dd02961cff24064c54c089c52e1a0753` |
| Online PQ KEM | Round-3 Kyber1024, libsignal key type `0x08`; it is deliberately not labelled FIPS 203 ML-KEM |
| Archive KEM | `MLKEM768-X25519` from `draft-irtf-cfrg-concrete-hybrid-kems-04` as profiled by `draft-ietf-hpke-pq-05`: ML-KEM-768 plus X25519, 1216-byte public key, 1120-byte encapsulation, 32-byte private key, and 32-byte shared secret |
| Archive sealing | HPKE base mode from `draft-ietf-hpke-hpke-03` and `draft-ietf-hpke-pq-05`, KEM ID `0x647a`, HKDF-SHA-256 (`0x0001`), and AES-256-GCM (`0x0002`). The wire suite name is `MLKEM768-X25519-HKDF-SHA256-AES256GCM`; the numeric identifiers are fixed inputs to HPKE's suite derivation and are not negotiated from message data. |
| Password root | Argon2id from RFC 9106's second recommended option, version 19, 64 MiB memory, 3 iterations, parallelism 4, 16-byte random salt, 32-byte output |
| Root and purpose derivation | HKDF-SHA-256 from RFC 5869 |
| Local/root wrapping | AES-256-GCM with a fresh 96-bit nonce and the canonical context as additional authenticated data |
| Hash | SHA-256 |
| Signatures | Ed25519 for account/device membership and message manifests; this is classical authentication and must not be described as PQ authentication |
| Canonical form | RFC 8785 JSON Canonicalization Scheme (JCS), UTF-8, with all identifiers represented as lowercase canonical UUID strings and binary values represented as unpadded base64url |

The concrete-hybrid-KEM draft supplies the analyzed classical/PQ KEM combiner,
and the PQ-HPKE draft defines its HPKE mapping and assigned code point. HPKE
supplies the KEM/KDF/AEAD composition. Hush Line does not concatenate
independent shared secrets, assign a private KEM identifier, or define a new
combiner. These are works in progress, so the exact pinned revisions and this
combined application profile require independent review before production use.

The archive public key is an `MLKEM768-X25519` public key for one account
archive epoch. An archive copy is an HPKE `SealBase` operation over the complete
message plaintext. `info` is the ASCII label
`HushLine/HL-PQCHAT-1/archive-seal/v1` followed by a zero byte and the 32-byte
SHA-256 digest of the copy context. The JCS copy-context bytes are HPKE
additional authenticated data. The stored value is the 1120-byte hybrid-KEM
encapsulation followed by the HPKE ciphertext, including its 16-byte GCM tag.
Parsing must use the fixed encapsulation length and reject stored values shorter
than 1136 bytes; it must not accept an algorithm or length supplied by the
record itself.

## Library boundary

Production code must expose these asynchronous operations through a dedicated
worker. Secret-returning operations return opaque handles where the caller does
not need raw key bytes.

```text
enrollDevice(accountRootHandle, deviceDescriptor) -> DevicePublicBundle
publishPrekeys(deviceHandle, count) -> SignedPrekeyBundle
beginSession(localDeviceHandle, verifiedRemoteBundle) -> PendingSession
ratchetEncrypt(pendingOrLiveSession, plaintext, contextBytes) -> PendingRatchetWrite
ratchetDecrypt(liveSession, ciphertext, contextBytes) -> PendingRatchetRead
archiveSeal(verifiedArchivePublicKey, plaintext, contextBytes) -> ArchiveCiphertext
archiveOpen(archivePrivateKeyHandle, ciphertext, contextBytes) -> plaintext
preparePasswordWrap(passwordBytes, kdfParameters, accountRootHandle) -> WrappedRoot
commitPendingState(transactionId) -> void
abortPendingState(transactionId) -> void
```

Each operation validates exact suite, key sizes, membership, key version,
expiry, and context before cryptographic use. Errors are stable categories:
`CAPABILITY_UNAVAILABLE`, `MALFORMED_WIRE`, `SUITE_MISMATCH`,
`STALE_MEMBERSHIP`, `PREKEY_DEPLETED`, `PREKEY_REPLAY`,
`AUTHENTICATION_FAILED`, `STATE_CONFLICT`, `STORAGE_UNAVAILABLE`, and
`INTERNAL_ERROR`. Error detail must contain no
plaintext, key bytes, or remote-controlled ciphertext.

## Identity, device membership, and freshness

Every account has a random account root and an Ed25519 account identity key.
The private identity key is wrapped under the account root. Its public key and
monotonic `identity_version` are stored by the server and pinned by clients.

Each browser enrollment generates a distinct device identity/signing key,
PQXDH/SPQR state, and prekeys. The account identity signs a JCS membership
record containing:

- account and device UUIDs;
- account `identity_version`, membership sequence, status, issue time, and
  expiry time;
- device signing and protocol identity public keys;
- supported protocol and archive suite names;
- signed-prekey and one-time-prekey ranges; and
- current account archive epoch and `MLKEM768-X25519` public key digest.

Membership sequence numbers increase for enrollment, renewal, revocation, and
archive-epoch changes. Membership expires after 30 days and is renewed during
normal authenticated use. A device signed prekey rotates every 7 days and the
previous key may decrypt already committed messages for at most 48 hours. Each
device maintains 100 one-time classical/PQ prekey pairs, replenishes below 20,
and cannot start a session when none are available.

Clients reject a membership below their account/conversation high-water mark,
an expired membership, a revoked device, a mismatched account identity, or a
prekey outside the signed range. The service enforces the same monotonic
version. A malicious service can still fork first-use views or isolate clients;
there is no key-transparency log in version 1. Classical signatures also do not
authenticate against a future active quantum forger. Product copy must state
both limitations.

## Password root and browser storage

Account creation generates a random 32-byte account root in the browser. The
password KDF output is expanded with
`HushLine/HL-PQCHAT-1/password-wrap-key/v1` and the account UUID to form a
32-byte wrapping key. AES-256-GCM wraps the account root with the KDF parameters,
account UUID, root version, and purpose in JCS additional authenticated data.
The server stores only the salt, KDF parameters, nonce, wrapped root, and tag.
Password input is the exact UTF-8 encoding submitted to the normal login flow,
with no Unicode normalization or truncation; clients reject invalid UTF-8 and
KDF parameters other than the fixed version-1 values.

The account root derives distinct wrapping keys with these exact HKDF `info`
labels and a salt equal to `SHA-256(account_uuid)`:

- `HushLine/HL-PQCHAT-1/account-identity-wrap/v1`;
- `HushLine/HL-PQCHAT-1/archive-private-key-wrap/v1`;
- `HushLine/HL-PQCHAT-1/device-storage-wrap/v1`; and
- `HushLine/HL-PQCHAT-1/session-export-wrap/v1`.

Keys derived under one label must never be used for another purpose. Archive
private keys are randomly generated, never derived from a password or account
root, and are stored server-side only as ciphertext wrapped under the account
root. This is what permits a fresh browser with the current password to recover
retained history.

Ratchet states and unused private prekeys are device-local. They are encrypted
in IndexedDB with a random device-storage key; the key is wrapped for the
current authenticated browser session and bound to the device UUID plus the
server chat-session identifier. They are never uploaded or included in account
backup/archive material. A fresh browser creates a new device and cannot
recover an old ratchet state.

An unlocked account root may be held in memory and `sessionStorage` only for
the authenticated session. Storage failure keeps the current document
in-memory or disables chat; it never selects a weaker path. Logout, session
identifier change, reset, revocation, and deletion perform best-effort removal,
without claiming guaranteed browser or operating-system erasure.

Password change with the old password unwraps and rewraps the same account root
before the credential transaction commits. Password reset without the old
password generates a new account root, identity version, device set, and
archive epoch. Old retained history stays locked and no server recovery copy is
created.

## Archive epochs and copy inventory

An account archive epoch is an `MLKEM768-X25519` keypair plus an unsigned 64-bit
monotonic epoch number. A new epoch is created every 90 days, on password reset,
on account-identity rotation, or when archive-key compromise is suspected. New
writes use only the highest active epoch. Old private keys remain wrapped only
while authorized retained copies in that epoch exist; deletion of the last copy
makes the wrapped private key eligible for deletion after the existing backup
retention window.

Rotation does not re-encrypt history by default and cannot repair a copied old
private key or plaintext. Revoking a device prevents new delivery to it, but
does not revoke archive access from an attacker who already obtained the
account root or an archive private key.

For the supported two-account conversation, one logical message has exactly:

1. one ratchet transport copy for every active device of both participant
   accounts except the originating sender device;
2. one independently sealed archive copy for the sender account's current
   archive epoch; and
3. one independently sealed archive copy for the recipient account's current
   archive epoch.

The active-device inventory is fixed by the same membership snapshot used for
encryption and validated by the server transaction. A device enrolled after
commit recovers history through its account archive; it does not create a late
ratchet copy. The sender and recipient archive ciphertexts must differ because
their hybrid archive keys and copy contexts differ. Offline queues and retries
retain the exact applicable device transport bytes; they do not create another
content encryption. Database replicas and backups retain exact already-hybrid
ciphertext bytes. Notifications contain only generic activity metadata.
Exports retain their existing scope and do not silently add plaintext chat.
There is no server escrow, classical-only history copy, plaintext retry buffer,
analytics copy, search index, preview, or ratchet-state backup.

## Authenticated context and wire package

All integers are JSON integers within the interoperable range, timestamps are
UTC RFC 3339 strings with whole seconds, and arrays that represent sets are
sorted lexicographically by their canonical identifier. Unknown fields are a
protocol error; extension data requires a new version.

The immutable copy context contains:

```json
{
  "account_recipient_id": "uuid",
  "archive_epoch": 7,
  "capability_offer": ["HL-PQCHAT-1"],
  "capability_selection": "HL-PQCHAT-1",
  "conversation_id": "uuid",
  "device_recipient_id": "uuid-or-zero-for-account-archive",
  "key_version": 4,
  "message_id": "uuid",
  "protocol": "HL-PQCHAT-1",
  "purpose": "transport|archive",
  "recipient_membership_sequence": 18,
  "sender_account_id": "uuid",
  "sender_device_id": "uuid",
  "sender_membership_sequence": 12,
  "suite": "SIGNAL-PQXDH3-KYBER1024-SPQR1|MLKEM768-X25519-HKDF-SHA256-AES256GCM"
}
```

Ratchet associated data and archive HPKE associated data are the exact JCS
bytes of the applicable context. This binds message, conversation, sender,
account/device recipient, purpose, version, membership freshness, negotiated
capability, archive epoch, and suite.

After encryption, the sender builds a manifest with the shared identifiers,
the selected capability, sender membership digest, and a sorted `copies` array.
Every copy entry contains its purpose, recipient account/device, key version,
archive epoch when applicable, exact byte length, SHA-256 of the complete
stored ciphertext bytes, and the SHA-256 of its context bytes. The device signs
`HushLine/HL-PQCHAT-1/manifest-signature/v1`, a zero byte, and the exact JCS
manifest bytes. The signature therefore authenticates transport bytes, archive
hashes, copy inventory, capability negotiation, and all context bindings
without a circular ciphertext dependency.

The request body is a JCS object with exactly three fields: `manifest` contains
the manifest object, `signature` contains its unpadded base64url signature, and
`copies` is sorted in manifest order. Each request copy has exactly `context`
(the copy-context object) and `ciphertext` (unpadded base64url stored bytes).
The server recanonicalizes each context and rejects a copy whose recomputed
digests, fields, length, or order differ from the manifest. The idempotency key
is lowercase hex `SHA-256(manifest_bytes || signature_bytes)`. The executable
[wire fixtures](g3-wire-fixtures.json) pin the canonical context/manifest bytes,
hash of the reconstructed request bytes, copy ordering, and mutation failures.
Their opaque ciphertext bytes are synthetic framing inputs, not cryptographic
known-answer vectors.

## Atomic state transitions

### Prekeys

<!-- prettier-ignore -->
| From | Event | To | Required atomic effect |
| --- | --- | --- | --- |
| absent | publish signed bundle | available | verify membership/signatures and uniqueness |
| available | reserve with message/idempotency ID | reserved | one reservation wins; 5-minute expiry |
| reserved | same ID retries | reserved | return identical bundle and reservation |
| reserved | message package commits | consumed | commit all copies and tombstone the one-time classical/PQ pair together |
| reserved | reservation expires before commit | available | release without advancing recipient state |
| consumed | any reuse | consumed | reject `PREKEY_REPLAY` |
| available/reserved | device revoked or key expires | invalid | reject new sessions; retain only what committed ciphertext needs |

Classical and PQ one-time prekeys form one logical pair. They cannot be
reserved, consumed, replenished, or deleted independently.

### Send

1. Read a consistent participant/membership/prekey/archive-key snapshot and
   reserve any initial-session prekey pair by message and idempotency ID.
2. Encrypt using cloned ratchet state and build every transport/archive copy.
3. Persist an encrypted local pending record containing exact request bytes and
   the before/after ratchet-state digests; do not publish the advanced state.
4. The server verifies authorization, membership/version freshness, signature,
   suite, exact participant/copy inventory, context and ciphertext hashes,
   sizes, uniqueness, and reservation ownership in one transaction.
5. The same transaction commits all metadata/copy references and consumes the
   prekey pair. Staged blobs become reachable only through that commit.
6. On the authenticated acknowledgement, atomically promote local ratchet
   state and delete the pending record. A retry sends byte-identical content.

Any different bytes under the same message or idempotency ID are
`STATE_CONFLICT`. Any required-copy, upload, validation, quota, or database
failure commits no message and consumes no prekey. Abandoned staged blobs are
unreachable and cleaned on a bounded schedule.

### Receive

1. Fetch the manifest and authorized participant copy without acknowledging.
2. Verify the device signature, membership high-water mark, conversation
   version, complete inventory, context digests, and exact ciphertext hash.
3. Decrypt against cloned ratchet/archive state and validate message identity.
4. In one IndexedDB transaction, store the promoted state, replay marker, and
   receipt. Render only after that transaction commits.
5. Replays return the prior receipt without advancing state. Authentication,
   storage, or state conflicts render no plaintext and send no success receipt.

Cross-tab access uses one lease per account/device with fencing tokens. A stale
lease holder cannot commit after a newer token. BroadcastChannel is only a
wakeup mechanism, never key transport.

### Browser transaction profile

The version-1 browser adapter is `assets/js/pq-browser-state.js`. Its IndexedDB
database contains only authenticated AES-256-GCM envelopes and non-secret
coordination metadata. Envelope additional data binds the database format,
account/device partition, record type, revision, random record tag, and the
authenticated-session binding under which the record was written. The random
device-storage key is supplied as a non-extractable `CryptoKey`; the adapter
does not persist that key or place key material in `localStorage`.

One account/device lease serializes state changes. Every acquisition increases
a durable fencing token, renewals retain that token, and release/logout retain
the counter so an expired owner can never become current again by token reuse.
Lease duration is 15 seconds by default. BroadcastChannel messages contain
only an outbox wakeup or cleanup signal and the public account/device
partition; they never contain keys or encrypted-record contents.

A send transaction leaves the current state unchanged and atomically stores an
encrypted pending next state plus the exact request bytes, stable logical
message ID, protocol idempotency key, and before/after state digests. Network
ambiguity leaves that record intact, and reload recovery enumerates encrypted
outbox records without a separate plaintext draft index. Only an authenticated
acknowledgement whose message identity and conversation version match the
durable operation atomically promotes the pending state and removes the outbox
record. A receive transaction atomically promotes state with its archive
result, receipt, and replay marker; a duplicate returns the stored receipt
without another state advance. A session with a pending send rejects receive
advancement rather than forking the ratchet.

Version 1 permits at most 32 durable outbox records per device, 2,000 skipped
keys and 32 pending transitions per ratchet state, 100,000 outgoing
deduplication markers, and 100,000 replay receipts per device. It does not
evict live send or replay markers: reaching a bound fails closed and requires
an authenticated session/device rotation. Logout notifies same-origin tabs and
workers, removes all encrypted records for the account/device partition, and
increments the fence before dropping the in-memory key. Storage denial,
corruption, missing state, known stale revisions, and quota exhaustion disable
the transition; they never select an in-memory send path or a classical
writer.

The adapter can reject a snapshot below a revision already known by the
caller, but browser storage can be rolled back together with its local
high-water mark without detection. JavaScript engines, browser processes,
swap, extensions, and crash capture can also retain copies after references
are cleared. Cleanup is therefore best effort and is not secure-erasure or
general rollback-detection evidence. A browser without the device partition
must enroll a fresh device/session; mutable ratchet state is never imported as
fresh-device recovery material.

## Capability, migration, and rollback

The server advertises authenticated membership capabilities, but the sender
selects a suite only after signature and freshness validation. A conversation
begins at legacy version 0. It may move monotonically to `HL-PQCHAT-1` only when
both accounts have current memberships, device/prekey supply, and archive keys
for this version. The first version-1 commit fixes the conversation writer
version; it can never write version 0 again.

Legacy ciphertext remains labelled and readable by the legacy reader. It is
not relabelled, rewrapped, or counted as PQ-protected. Automatic history
migration is forbidden. A later explicit migration must create a new
version-1 ciphertext from authenticated plaintext while an authorized client
is present and must define deletion and failure behavior in a new review.

A rollout kill switch stops new version-1 writes but preserves version-1
readers and existing encrypted state. Application rollback must deploy a build
that can parse, verify, and read the version-1 package or must leave chat
unavailable; it must not restore the legacy writer. Partial server/client
support, stale capabilities, unknown suite/version, or missing browser
capability fails closed with no extra everyday prompt.

## Failure matrix

<!-- prettier-ignore -->
| Failure | Required result |
| --- | --- |
| Missing/expired/revoked membership or identity mismatch | Reject before encryption/decryption; refresh authenticated public state |
| No complete classical/PQ prekey pair | Reject initial send as `PREKEY_DEPLETED`; no classical setup |
| Suite/version/capability mismatch | Reject the whole operation; do not negotiate downward |
| Missing, extra, duplicate, mixed-suite, or wrong-recipient copy | Reject the whole package and consume no prekey |
| Archive copy shorter than its 1120-byte encapsulation plus 16-byte tag | Reject as `MALFORMED_WIRE` before decapsulation |
| Context, ciphertext, transport-byte, archive-hash, or signature mismatch | Reject before plaintext release and retain no advanced state |
| Replay or reordered package | Use protocol skipped-key bounds for legitimate reordering; reject a consumed message/prekey without state advance |
| Local quota/storage failure before send | Publish nothing and retain old ratchet state |
| Network/acknowledgement loss after server commit | Retry byte-identical package; server returns the original result |
| Blob or database failure | Make no package reachable; consume no prekey; clean staged bytes |
| Password unwrap failure | Reveal no history and do not mutate root/key records |
| Password reset without old root | Start a new identity/archive epoch; old history remains locked |
| Archive open failure or wrong epoch | Render no plaintext; do not fall back to ratchet backup or server recovery |
| Revoked device sends with stale state | Reject by membership sequence/status even if its classical signature verifies |
| Browser loses in-memory keys | Disable read/write until normal login provisions or unlocks supported state |
| Emergency rollback | Stop writes; retain version-1 read support and ciphertext; never convert to legacy |

## Key and data flows

```text
password --Argon2id--> password wrap key --AES-GCM unwrap--> account root
                                                            |--wraps account identity
                                                            |--wraps archive epoch private keys
                                                            `--wraps local device-storage key

recipient signed membership --> verified PQXDH/SPQR + archive public keys
plaintext --> ratchet encrypt -----------------------------> transport copies
         `-> hybrid HPKE SealBase per participant epoch ---> archive copies
all exact ciphertext hashes + contexts --> signed manifest --> atomic commit
```

```text
server: signed public membership, prekey pairs, wrapped root/private keys,
        signed manifest, hybrid ciphertext copies, generic metadata
browser session: unwrapped account root, plaintext while in use, archive key
local encrypted storage: ratchet state, unused private prekeys, pending writes
never server-readable: plaintext, account root, archive private keys,
                       device-storage key, ratchet/message keys
```

## Security claim limits

- Confidentiality is hybrid PQ for new, complete version-1 copies. Identity,
  membership, manifests, TLS, and server authentication remain classical.
- The design does not provide active-quantum authentication, key transparency,
  metadata privacy, participant deniability against signed manifests, or
  protection from malicious served JavaScript/endpoints.
- Signal protocol claims apply only to exact tested ratchet behavior and
  best-effort key deletion. Archive copies intentionally remain decryptable and
  therefore do not inherit ratchet forward secrecy or post-compromise recovery.
- Account-root or archive-private-key compromise exposes its retained scope.
  Rotation and deletion do not repair already copied keys, plaintext, browser
  memory, backups, or ciphertext.
- Browser erasure is best effort. No UI, documentation, or review evidence may
  describe it as forensic deletion.

## Independent review disposition

The cryptographic engineer and independent design reviewer fields remain empty
in `g3-readiness.json`. Review must cover the combined ratchet, hybrid HPKE
profile, signed context, root hierarchy, transaction protocol, migrations, and
claim limits at one exact revision. Blocking findings must be resolved and the
fixtures regenerated before this specification can be marked accepted or used
by production-dependent cryptographic implementation.

## Primary references

- [`draft-ietf-hpke-pq-05`: Post-Quantum and Hybrid Algorithms for HPKE](https://datatracker.ietf.org/doc/html/draft-ietf-hpke-pq-05)
- [`draft-irtf-cfrg-concrete-hybrid-kems-04`: Concrete Hybrid PQ/T KEMs](https://datatracker.ietf.org/doc/html/draft-irtf-cfrg-concrete-hybrid-kems-04)
- [`draft-ietf-hpke-hpke-03`: Hybrid Public Key Encryption](https://datatracker.ietf.org/doc/html/draft-ietf-hpke-hpke-03)
- [RFC 9106: Argon2](https://www.rfc-editor.org/rfc/rfc9106.html)
- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [Signal PQXDH revision 3](https://signal.org/docs/specifications/pqxdh/)
- [Signal Double/Triple Ratchet](https://signal.org/docs/specifications/doubleratchet/)
- [`signalapp/libsignal` pinned revision](https://github.com/signalapp/libsignal/tree/b056faa6dd02961cff24064c54c089c52e1a0753)
- [`@getmaapp/signal-wasm` pinned source](https://github.com/getmaapp/signal-wasm/tree/0a5e3cb8bf282efb3521d7cdac5476caf3fb1acd)

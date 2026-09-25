# ADR-0007: Post-Quantum Chat Archive Readiness

Status: **Blocked before implementation**  
Date: 2026-09-25  
Decision gate: G8 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2373`

## Context

G8 must preserve retained sender and recipient history after the normal unlock,
including in a fresh browser and when an original target device never reopens.
It must use archive keys that are separate from live protocol secrets, wrap
approved archive epochs behind the account unlock root, create every required
authenticated hybrid-PQ archive copy at send time, and never archive a ratchet
snapshot. Authorization, retention, deletion placeholders, account deletion,
and export behavior must apply consistently to the complete copy inventory.

Those behaviors depend on G4's accepted storage/API implementation and G6's
accepted transactional browser-state implementation. The prerequisite
artifacts are available on this branch, but both record blocked decisions. The
archive construction itself was reserved for G3, whose artifact records that
no design was selected or reviewed. The machine-readable
[G8 readiness record](g8-readiness.json) pins those findings and inventories
the implementation and review evidence that cannot safely be produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G4 / `scidsg/hushline#2369` | Accepted versioned storage and APIs for authenticated account-archive copies, complete-copy transactions, authorization, retention, deletion, and migration | Commit `febe75caa6e7ad9ee1b1bedf786b0720f7767ad2`; [ADR-0003](adr-0003-server-storage-api-readiness.md) and [readiness record](g4-readiness.json) | **Unsatisfied:** G4 is blocked before implementation and records archive epochs/copies, authenticated envelopes, transaction boundaries, authorization, retention, and deletion as unspecified |
| G6 / `scidsg/hushline#2371` | Accepted encrypted browser state and atomic send/receive boundaries coupling protocol state, ciphertext, replay state, and the required archive result | Commit `fe312ab3bef6ded364c115ec29b8c2c8f2dce60f`; [ADR-0005](adr-0005-transactional-browser-state-readiness.md) and [readiness record](g6-readiness.json) | **Unsatisfied:** G6 is blocked before implementation and records wrapping, archive transitions, fresh-browser recovery, durable retries, and failure behavior as unspecified |
| G3 / `scidsg/hushline#2368` archive design | Accepted archive key hierarchy, hybrid construction, wrapping context, copy inventory, epoch lifecycle, recovery behavior, and compromise limits | Commit `9d7abd7a1ca83a64914cae6465e8ee4cf160132f`; [ADR-0002](adr-0002-complete-protocol-design-readiness.md) and [readiness record](g3-readiness.json) | **Unsatisfied:** G3 is blocked before design and explicitly produced no reviewed archive construction or complete-copy contract |

A merged readiness artifact, issue ordering, or existing classical history flow
is not proof that these gates passed. G8 cannot derive cryptographic algorithms,
key sizes, KDF inputs, canonical envelope bytes, epoch rules, or copy
cardinality from the outcome statement without deciding the design reserved
for G3 and its human reviewers.

## Decision

G8 is blocked before implementation. Do not add archive keys, wrapping code,
archive copies, schema, migrations, browser recovery logic, retention jobs, or
export behavior until G4 and G6 are accepted and G3 supplies the exact reviewed
archive contract. In particular, do not:

- reuse account, device, handshake, ratchet, chain, message, or transport keys
  as archive keys, or persist old ratchet snapshots as a history mechanism;
- invent a KDF, hybrid combiner, algorithm suite, envelope serialization,
  authenticated context, archive epoch, rotation rule, or retention period;
- create a classical-only sender, recipient, retry, compatibility, backup, or
  history copy, or commit only a subset of the required hybrid copies;
- make fresh-browser recovery depend on PGP import, an extra password, recovery
  phrase, paired device, or cloning mutable ratchet state;
- let an archive copy bypass participant authorization, survive a participant
  or account deletion contrary to the accepted retention contract, resurrect a
  deleted message, or silently expand the existing account-export surface; or
- claim that ratchet progress, archive-key rotation, or deletion retroactively
  revokes a stolen archive key or protects ciphertext already captured with it.

No production model, migration, route, browser asset, key lifecycle, export,
dependency, or security claim is changed by this decision. Existing account
conversation and E2EE behavior remain unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after prerequisites pass | Current disposition |
| --- | --- | --- |
| Key hierarchy and wrapping | Separate archive keys and protocol secrets; reviewed account-root KDF domains and authenticated wrapping context; normal-unlock provisioning and recovery; wrong-password and substitution rejection; no PGP, extra secret, phrase, or pairing requirement | Blocked; G3 selected no archive construction or wrapping contract |
| Epochs and rotation | Approved account/archive epoch identifiers, creation and rotation authority, overlap, rewrapping versus re-encryption rules, retirement, retention, password-change behavior, reset limitation, and captured-key limits | Blocked; epoch and lifecycle semantics are unspecified |
| Sender and recipient copies | Authenticated sender and recipient archive envelopes created at send time for online and offline participants, with canonical message, conversation, account, participant, purpose, direction, version, suite, epoch, and ciphertext bindings | Blocked; G3 envelope and copy inventory are unavailable |
| Complete-copy atomicity | One logical send commits every required hybrid transport/archive copy or none, with stable retry bytes and an auditable inventory proving no recoverable classical-only duplicate | Blocked; G4 and G6 transaction contracts are unavailable |
| Fresh-browser and offline history | Existing unlock secret recovers authorized sent and received history in a fresh browser, including unread messages whose original target device never reopened, without copying mutable ratchet state | Blocked; wrapping and recovery contracts are unavailable |
| Authorization and authenticated history | Participant-scoped list/fetch/decrypt authorization and rejection of forged archive data, context/key substitution, replay, cross-account access, and server-invented history | Blocked; identities, envelope bytes, provenance, and API authorization are unspecified |
| Retention and deletion | Approved bounds and cleanup for archive epochs and copies; participant-local deletion, authored-message placeholders, final shared deletion, account deletion, retry queues, backups, and restoration without resurrection | Blocked; G4 retention/deletion and G6 pending-state rules are unavailable |
| Export behavior | Regression coverage for the existing export scope and an explicit, accurately labelled user ceremony before any future deliberate plaintext chat export | Blocked; no archive export change is approved by G1 or G3 |
| Compromise claims | Documentation and tests showing the exact exposure of a stolen long-lived archive key, the non-retroactivity of rotation, and why ratchet progress does not revoke archive access | Blocked pending the reviewed hierarchy, scope, and lifecycle |

## Required Validation After Unblocking

The implementation must provide linked, non-secret evidence for:

1. normal unlock and fresh-device recovery in real Chromium, Firefox, and
   WebKit for both sent and received retained history;
2. sender and recipient history when either side was offline, including an
   unread message whose original target device is never reopened;
3. wrong-password rejection and tampering/substitution of the archive key,
   wrapped epoch key, account, participant, conversation, message, purpose,
   direction, version, suite, epoch, ciphertext, and sender/recipient copy;
4. retries and injected contribution/copy failures proving that all required
   copies commit atomically with unchanged bytes and no classical-only copy;
5. a persisted-copy audit across the database, blob storage, browser storage,
   retry/outbox state, notifications, exports, backups, and migration paths;
6. key separation tests and storage inspection proving that no protocol secret
   or old ratchet snapshot is retained in the archive;
7. epoch provisioning, password change with rewrapping, approved rotation,
   overlap, retention, retirement, and password reset without the old secret;
8. participant authorization, local deletion and remaining-participant
   placeholders, final shared deletion, account deletion, cleanup, backup
   restoration, and non-resurrection behavior; and
9. existing export-scope regression plus clear user-visible distinction for
   any separately approved deliberate plaintext export.

Real-browser evidence, cryptographic review, and human security approval must
remain pending until they are actually supplied. Tests must model archive-key
compromise independently of ratchet compromise and must not assert that
ratchet progress or rotation repairs ciphertext accessible with a stolen
long-lived archive key.

## Unblocking and Review Sequence

1. Obtain the pending G1 approvals and replace the G2 no-go with passing,
   pinned protocol evidence.
2. Complete and accept G3's exact archive hierarchy, hybrid construction,
   authenticated context, copy inventory, wrapping, epoch, recovery, deletion,
   export, and compromise-limit decisions on `codex/epic-2365`.
3. Implement and accept G4 and G6 against that contract. A readiness-only
   artifact does not satisfy either prerequisite.
4. Update `g8-readiness.json` to pin the accepted commits and transcribe the
   exact algorithms, domains, identifiers, bytes, bounds, and lifecycle rules
   into failing implementation tests before changing production behavior.
5. Implement the minimal archive integration and produce every validation item
   above, then obtain cryptography/browser and independent security review at
   the exact implementation commit. Resolve blocking findings before enabling
   upgraded traffic.

The implementation author cannot fill either reviewer disposition. A durable
archive intentionally trades ratchet-only forward-secrecy properties for
history availability; that boundary must remain explicit in code, tests, user
documentation, and security claims.

## Consequences

- No unreviewed archive primitive, key hierarchy, copy format, epoch lifecycle,
  recovery mechanism, export expansion, or classical fallback is introduced.
- Existing legacy conversation behavior, ciphertext, deletion, and export
  behavior remain intact.
- Every issue criterion and adversarial scenario has a concrete evidence slot
  instead of a fabricated design choice, browser result, or security approval.
- G8 remains incomplete until its prerequisites pass and production
  implementation, copy audit, browser evidence, and human reviews exist.

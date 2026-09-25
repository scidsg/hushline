# ADR-0004: Authenticated Devices and Prekey Lifecycle Readiness

Status: **Blocked before implementation**  
Date: 2026-09-24  
Decision gate: G5 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2370`

## Context

G5 must implement account-bound browser identities, signed device membership,
and a bounded, atomic prekey lifecycle so that a sender can establish a
protected session while the recipient is offline. Enrollment must be part of
the normal authenticated-login and existing-E2EE-unlock ceremony. Prekey or
capability failure must fail closed with an accessible recovery state, never a
silent classical fallback.

Those behaviors depend on G4's accepted device storage, authorization,
authenticated-envelope, transaction, retention, and migration contracts. The
prerequisite artifact is available at commit
`febe75caa6e7ad9ee1b1bedf786b0720f7767ad2`, but it records G4 as blocked
before implementation. The machine-readable
[G5 readiness record](g5-readiness.json) pins that result and inventories the
implementation and review evidence that cannot safely be produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G4 / `scidsg/hushline#2369` | Accepted schema and API implementation with reviewed device authorization, envelope, transaction, retention, and migration contracts | Commit `febe75caa6e7ad9ee1b1bedf786b0720f7767ad2`; [ADR-0003](adr-0003-server-storage-api-readiness.md) and [readiness record](g4-readiness.json) | **Unsatisfied:** G4 is blocked by G3 and explicitly records device identity, membership authorization, envelope provenance, transaction boundaries, and lifecycle rules as unspecified |

A merged readiness artifact or issue sequence is not proof that its decision
gate passed. G5 cannot define signatures, freshness, prekey types, atomic claim
semantics, or expiration around an unselected protocol and absent storage/API
contract.

## Decision

G5 is blocked before implementation. Do not add device/prekey models,
migrations, routes, browser key generation, enrollment, publication, claim,
replenishment, rotation, expiration, revocation, or cleanup behavior until G4
supplies its accepted exact contract. In particular, do not:

- enroll a device outside the authenticated-login and existing-E2EE-unlock
  ceremony, or accept device identity, capabilities, or membership that is not
  cryptographically bound to reviewed account-key continuity;
- invent signature inputs, identifier formats, capability negotiation,
  freshness windows, epoch rules, or rollback guarantees absent the reviewed
  protocol and authenticated-envelope contract;
- make a one-time prekey reusable, separate selection from atomic consumption,
  omit bounded consumption tombstones, or improvise signed/last-resort key
  rotation and depletion behavior;
- expose device fingerprints, IP addresses, personal labels, or internal
  device inventory to conversation peers; or
- silently establish a classical-only session when a current authenticated
  membership, required capability, or eligible prekey is unavailable.

No production model, migration, lifecycle, route, browser asset, dependency,
or security claim is changed by this decision. Existing account conversation
and E2EE behavior remain unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after G4 passes | Current disposition |
| --- | --- | --- |
| Enrollment and continuity | Login/unlock-only enrollment, proof-of-possession, account-key authorization, signed canonical membership, capability binding, replay/idempotency behavior, and key-cleanup tests | Blocked; device identity and membership authorization are unspecified |
| Device-list verification | Canonical signed list or equivalent authorization proof, monotonic freshness/epoch rules, substitution and omission rejection, revoked-device rejection, and documented server rollback/fork limits | Blocked; signature inputs and freshness model are unspecified |
| Prekey publication | Authenticated device ownership, canonical signed-key and one-time-key formats, uniqueness, batch bounds, safe retry behavior, and stale/revoked publisher rejection | Blocked; protocol key formats and API contract are unspecified |
| Atomic claim | A database transaction that authorizes current membership and atomically consumes exactly one eligible one-time prekey, plus concurrent-claim and crash/retry evidence | Blocked; storage schema and transaction boundaries are unspecified |
| Consumption retention | Bounded tombstones sufficient for the reviewed replay/idempotency window, with cleanup behavior that cannot make a consumed key eligible again | Blocked; identifier, retry, and retention domains are unspecified |
| Replenishment and rotation | Low-water replenishment, duplicate-safe publication, signed/last-resort key rotation, overlap, expiry, depletion, clock-skew, and revoked-device behavior | Blocked; selected protocol semantics and lifecycle limits are unavailable |
| Abuse and privacy bounds | Separate rate limits for device creation, publication, and claims; per-account/device active and stale record caps; peer responses without fingerprints, IP addresses, or personal labels | Blocked; endpoints and response shapes are unspecified |
| Offline and failure UX | Offline-recipient first-session setup with all required hybrid copies, plus accessible recoverable states for depletion, expiry, revocation, stale membership, and missing capabilities | Blocked; G4 storage and G3 complete-copy protocol contracts are unavailable |
| Retention and deletion | Account/device revocation and deletion cascades, stale-record pruning, tombstone bounds, backup/restore treatment, and synthetic cleanup evidence | Blocked; G4 retention and migration contracts are unavailable |

## Required Validation After Unblocking

The implementation must provide linked synthetic evidence for:

1. simultaneous claims proving that no one-time prekey is returned twice;
2. exhausted, expired, already-consumed, and revoked-device key handling;
3. forged membership, device/key/capability substitution, stale-list, replay,
   cross-account, and revoked-identity rejection;
4. authenticated login/unlock enrollment and first-message setup while the
   recipient is offline, without a pairing prompt or recipient action;
5. replenishment, signed/last-resort rotation, bounded-record cleanup, account
   deletion, and device revocation; and
6. rate-limit and peer-response tests proving that operational device details
   are not disclosed.

Real-browser evidence, cryptographic review, and human security approval must
remain pending until they are actually supplied.

## Unblocking and Review Sequence

1. Complete G1 through G3 and obtain their required exact-commit human
   approvals and passing protocol evidence.
2. Implement and accept G4's reviewed schema, authorization, envelope,
   transaction, retention, and migration contracts on `codex/epic-2365`.
3. Update `g5-readiness.json` to pin that accepted G4 commit and transcribe its
   exact device/prekey constraints into failing implementation tests before
   changing production behavior.
4. Implement the minimal schema, APIs, and browser flow; produce every
   synthetic validation item above and the epic's accessibility, performance,
   CSP, migration, and complete-copy evidence.
5. Obtain backend/browser and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling upgraded
   traffic.

The implementation author cannot fill either reviewer disposition. A server
cannot by itself prove freshness against malicious rollback or equivocation;
the accepted design must state the exact residual limit and avoid claiming
stronger detection than its evidence supports.

## Consequences

- No unauthenticated device insertion, unbound capability record, non-atomic
  prekey claim, reusable one-time key, or classical fallback is introduced.
- Existing legacy conversation behavior and ciphertext remain intact.
- Every issue criterion and required validation scenario has a concrete
  implementation evidence slot rather than a fabricated design choice.
- G5 remains incomplete until G4 passes and production implementation, browser
  evidence, and human reviews exist.

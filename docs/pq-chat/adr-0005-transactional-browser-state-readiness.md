# ADR-0005: Transactional Browser State Readiness

Status: **Blocked before implementation**  
Date: 2026-09-25  
Decision gate: G6 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2371`

## Context

G6 must persist only approved encrypted device and ratchet state while keeping
unlock material within the current authorized browser session. It must couple
each send transition to the exact ciphertext and stable logical identifier in
one durable transaction, couple each receive transition to deduplication and
the required archive result, and serialize all tabs and workers that can
advance a session. Quota denial, storage loss, stale restores, crashes, reload,
logout, and fresh-browser enrollment must fail safely without adding an
everyday unlock step.

Those behaviors depend on G3's accepted protocol, state-transition, archive,
device-state, transaction, wrapping, and recovery contracts. The prerequisite
artifact is available at commit
`9d7abd7a1ca83a64914cae6465e8ee4cf160132f`, but it records G3 as blocked
before design. The machine-readable
[G6 readiness record](g6-readiness.json) pins that result and inventories the
implementation and review evidence that cannot safely be produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G3 / `scidsg/hushline#2368` | Accepted combined protocol design with reviewed state transitions, archive, device state, transaction boundaries, wrapping, lifecycle, and recovery behavior | Commit `9d7abd7a1ca83a64914cae6465e8ee4cf160132f`; [ADR-0002](adr-0002-complete-protocol-design-readiness.md) and [readiness record](g3-readiness.json) | **Unsatisfied:** G3 is blocked by pending G1 approvals and the G2 no-go; its protocol, state transaction, archive, device-state, wrapping, and recovery deliverables remain pending |

A merged readiness artifact or issue sequence is not proof that its decision
gate passed. G6 cannot choose what state may be persisted, derive storage
wrapping keys, or define valid send and receive transitions around an
unselected protocol and absent state/recovery contract.

## Decision

G6 is blocked before implementation. Do not add an IndexedDB/session adapter,
ratchet persistence, an outbox, receive-state transitions, cross-tab locks, or
storage recovery behavior until G3 supplies its accepted exact contract. In
particular, do not:

- persist plaintext private/session state, persist unlocked secrets beyond the
  current authorized browser session, or create a server-readable session
  backup;
- advance a send state before atomically committing the next state with the
  exact outgoing ciphertext and stable logical/idempotency identifier, or
  regenerate ciphertext while retrying that logical message;
- advance a receive state separately from replay deduplication and the required
  archive result, or retain unbounded skipped keys or pending transitions;
- treat a cooperative browser lock as sufficient without reviewed ownership,
  fencing, expiration, and crash-recovery semantics, or let an expired owner
  write after another context has taken over;
- continue from missing, cleared, known-stale, or partially committed state,
  silently weaken encryption when durable storage is unavailable, or clone a
  mutable ratchet into a fresh browser; or
- claim that JavaScript/WASM secrets can be perfectly erased or that all
  rollback of browser storage can be detected.

No production browser asset, template, dependency, storage schema, endpoint,
or security claim is changed by this decision. Existing account conversation
and E2EE behavior remain unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after G3 passes | Current disposition |
| --- | --- | --- |
| Persisted-state allowlist and wrapping | Exact protocol-owned state allowlist, encrypted device-scoped records, authenticated metadata, key derivation and lifetime, versioning, corruption rejection, and proof that unlocked material remains session-scoped | Blocked; protocol state and device-key lifecycle are unspecified |
| Atomic send and durable outbox | One transaction committing the next ratchet state, exact ciphertext bytes, required-copy result, and stable logical/idempotency ID before transmission; unchanged-byte retry, acknowledgement, pruning, and crash-boundary evidence | Blocked; ratchet transition and wire/idempotency contracts are unspecified |
| Atomic receive | One transaction coupling ratchet advancement, replay deduplication, required archive result, delivery state, and bounded skipped-key/pending-state updates; duplicate, out-of-order, and crash-boundary evidence | Blocked; receive and archive transition contracts are unspecified |
| Cross-context serialization | Per-session ownership, fencing token or equivalent stale-writer rejection, lock acquisition ordering, expiration/renewal, tab/worker coordination, and abrupt-owner recovery | Blocked; session identity and valid transition authority are unspecified |
| Bounds and pruning | Reviewed limits and deterministic pruning for skipped keys, pending sends/receives, deduplication records, acknowledged outbox entries, expired locks, corrupt records, and obsolete epochs | Blocked; protocol windows and retention domains are unspecified |
| Storage-restricted and loss behavior | Explicit behavior for quota denial, private browsing, unavailable/throwing APIs, eviction, cleared storage, partial writes, reload, and known stale restores, with no stale send or downgrade | Blocked; safe session-reset and archive recovery behavior are unspecified |
| Browser and account lifecycle | Login/unlock initialization, same-session reload, logout cleanup, account/device revocation, password lifecycle, fresh-browser fresh sessions, and no additional everyday unlock prompt | Blocked; G3 device, wrapping, reset, and revocation behavior is unavailable |
| Claim limits | Documentation and tests for undetectable rollback and JavaScript/WASM memory-erasure limits, without claiming perfect secure deletion or rollback detection | Blocked pending the exact storage, wrapping, and recovery design |

## Required Validation After Unblocking

The implementation must provide linked synthetic evidence for:

1. fault injection before and after every storage transaction and network
   boundary for send, retry, acknowledgement, receive, archive, and cleanup;
2. simultaneous sends from multiple tabs/workers, owner termination during
   every transition, lock expiration, takeover, and stale-owner rejection;
3. offline retries proving the same logical message transmits unchanged bytes
   and cannot create duplicate visible messages or advance state twice;
4. duplicate, replayed, and out-of-order receives proving atomic ratchet,
   deduplication, archive, skipped-key, and pending-state behavior;
5. quota denial, private browsing, missing/throwing storage APIs, eviction,
   reload, logout, unlock, cleared storage, corrupt records, and known stale
   snapshots;
6. fresh-browser enrollment proving a fresh session is established instead of
   cloning mutable ratchet state; and
7. real Chromium, Firefox, and WebKit evidence plus the epic's accessibility,
   performance, CSP, unchanged-UX, and complete-copy confidentiality checks.

Real-browser results, cryptographic review, and human security approval must
remain pending until they are actually supplied.

## Unblocking and Review Sequence

1. Complete G1 and obtain its required exact-commit human approvals; replace
   the G2 no-go with passing, pinned protocol evidence.
2. Complete and accept G3's combined protocol, state-transition, archive,
   device-state, transaction, wrapping, lifecycle, and recovery contracts on
   `codex/epic-2365`.
3. Update `g6-readiness.json` to pin that accepted G3 commit and transcribe its
   exact state machine, identifier, bounds, and lifecycle rules into failing
   implementation tests before changing production behavior.
4. Implement the minimal encrypted adapter, transactional send/receive paths,
   outbox, serialization, recovery, and cleanup behavior; produce every
   synthetic and real-browser validation item above.
5. Obtain browser-engineering and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling upgraded
   traffic.

The implementation author cannot fill either reviewer disposition. Browser
storage can be rolled back outside the application's control, and managed
runtimes may retain copied secret bytes; the accepted design must state what
is and is not detectable or erasable without overstating its guarantees.

## Consequences

- No unreviewed state format, wrapping scheme, transition boundary, locking
  primitive, or recovery rule is introduced.
- Existing legacy conversation behavior and ciphertext remain intact.
- Every issue criterion and required fault scenario has a concrete evidence
  slot rather than a fabricated protocol assumption or browser guarantee.
- G6 remains incomplete until G3 passes and production implementation,
  real-browser evidence, and human reviews exist.

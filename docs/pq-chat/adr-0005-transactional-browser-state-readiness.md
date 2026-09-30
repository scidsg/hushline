# ADR-0005: Transactional Browser State Readiness

Status: **Implemented for integration; independent review pending**<br>
Date: 2026-09-30<br>
Decision gate: G6 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2401`

## Context

G6 must persist only approved encrypted device and ratchet state while keeping
unlock material within the current authorized browser session. It must couple
each send transition to the exact ciphertext and stable logical identifier in
one durable transaction, couple each receive transition to deduplication and
the required archive result, and serialize all tabs and workers that can
advance a session. Quota denial, storage loss, stale restores, crashes, reload,
logout, and fresh-browser enrollment must fail safely without adding an
everyday unlock step.

Those behaviors depend on G3's protocol, state-transition, archive,
device-state, transaction, wrapping, and recovery contracts. G3 now supplies a
proposed exact contract and structural fixtures. Its required independent
reviews remain pending, but that pending release disposition does not prevent
G6 development against the versioned proposal. The machine-readable
[G6 readiness record](g6-readiness.json) inventories the implementation and
review evidence that G6 itself still must produce.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G3 / `scidsg/hushline#2398` | Accepted combined protocol design with reviewed state transitions, archive, device state, transaction boundaries, wrapping, lifecycle, and recovery behavior | [ADR-0002](adr-0002-complete-protocol-design-readiness.md), [protocol design](protocol-design.md), [fixtures](g3-wire-fixtures.json), and [review record](g3-readiness.json) | **Development input available; release acceptance pending:** the exact state and recovery proposal exists, while both independent reviews remain pending |

A merged readiness artifact or issue sequence is not proof that its decision
gate passed. G6 must implement the specified state allowlist, wrapping labels,
and send/receive transitions without treating pending review as acceptance.

## Decision

G6 now has an integration implementation in
`assets/js/pq-browser-state.js`. It provides encrypted IndexedDB records,
session-only key ownership, atomic pending-send/outbox and receive/replay
transactions, durable fencing leases, exact-byte delivery retry, bounded
state, known-stale revision rejection, and logout cleanup. The protocol worker
remains responsible for producing the opaque ratchet transition and the
server remains responsible for authenticating acknowledgements. Production
enablement still requires integration with those components and independent
review. In particular, do not:

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

The new browser asset is loaded on existing pages but does not activate a PQ
writer by itself. Existing account conversation ciphertext and E2EE behavior
remain unchanged until the protocol worker integrates this adapter.

## Implementation Matrix

<!-- prettier-ignore -->
| Area | Implemented contract | Current disposition |
| --- | --- | --- |
| Persisted-state allowlist and wrapping | AES-256-GCM envelopes for ratchet state, pending transitions, exact ciphertext requests, receipts, replay markers, and archive results; authenticated metadata; non-extractable session key | Implemented; worker key-wrapping integration and review pending |
| Atomic send and durable outbox | Pending next state and exact request bytes commit together before delivery; acknowledgement promotes state, records durable logical/idempotency deduplication, and removes outbox atomically | Implemented and exercised with post-commit and ambiguous-response faults |
| Atomic receive | State, replay marker, receipt, archive result, skipped keys, and pending transitions commit together | Implemented with duplicate no-advance behavior |
| Cross-context serialization | Account/device lease with monotonic fencing, expiry, renewal, takeover, and stale-owner rejection | Implemented; BroadcastChannel is wakeup-only |
| Bounds and pruning | Fixed bounds; acknowledged outbox is removed; live replay markers are not evicted and exhaustion fails closed | Implemented |
| Storage-restricted and loss behavior | Missing, stale, corrupt, denied, or quota-exhausted state fails closed | Implemented; full engine execution remains release evidence |
| Browser and account lifecycle | Reload recovery uses encrypted records; logout clears the partition and invalidates leases; fresh devices use distinct partitions | Implemented without a new prompt |
| Claim limits | Undetectable full rollback and managed-runtime erasure limits are explicit in the protocol design | Documented |

## Validation

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

`tests/playwright/pq-state/pq-browser-state.spec.js` is the executable synthetic
browser suite for Chromium, Firefox, and WebKit. It covers termination after a
durable send, exact-byte retry, ambiguous network acknowledgement, concurrent
lease takeover, stale-owner rejection, atomic receive deduplication, state
bounds, storage denial, known stale state, encrypted-at-rest inspection, and
logout. Measured browser results, cryptographic review, and human security
approval remain pending until the configured suite runs in review/CI.

## Unblocking and Review Sequence

1. Run the dedicated Playwright suite in Chromium, Firefox, and WebKit and
   retain the measured CI artifacts.
2. Integrate the protocol worker and its device-storage-key wrapping lifecycle
   with this adapter, then run the complete-copy end-to-end flow.
3. Exercise remaining eviction, corrupt-record, cleared-storage,
   private-browsing, worker-termination, accessibility, performance, and CSP
   scenarios in the integrated application.
4. Obtain browser-engineering and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling upgraded
   traffic.

The implementation author cannot fill either reviewer disposition. Browser
storage can be rolled back outside the application's control, and managed
runtimes may retain copied secret bytes; the accepted design must state what
is and is not detectable or erasable without overstating its guarantees.

## Consequences

- The implemented state format and transition boundary are concrete inputs for
  independent review rather than release claims.
- Existing legacy conversation behavior and ciphertext remain intact.
- Every issue criterion and required fault scenario has a concrete evidence
  slot rather than a fabricated protocol assumption or browser guarantee.
- G6 implementation is complete for integration; release approval remains
  pending real-browser evidence, protocol-worker integration, and human review.

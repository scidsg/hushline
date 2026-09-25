# ADR-0008: PQ Chat Protected-Delivery Readiness

Status: **Blocked before implementation**

Date: 2026-09-25

Decision gate: G9 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2374`

## Context

G9 must route both the opening profile submission and every later reply through
one protected-delivery path. One logical message must bind the protocol output,
the authenticated sender and recipient records, every required device and
self-history/archive copy, the initial nonce and context, and a stable retry
identity into the reviewed signed envelope. The server must acknowledge that
logical message only after the complete required copy set commits atomically.

Retries after offline, network, browser, or server failure must reuse the exact
committed send rather than re-encrypting it, duplicating a visible message, or
dropping an acknowledged message. The existing draft, submit, unlock,
chronology, unread/read, notification, participant-deletion, and placeholder
behavior must remain unchanged. A protected conversation must fail closed when
JavaScript is absent or its payload or protocol operation is invalid; the
current server-side classical intake fallback cannot be used to bypass that
contract.

Those behaviors depend directly on G7's accepted protocol integration and
G8's accepted archive construction. Both prerequisite artifacts are present on
this branch, but both record blocked decisions and no production
implementation. The machine-readable [G9 readiness record](g9-readiness.json)
pins those findings and inventories the delivery and review evidence that
cannot safely be produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G7 / `scidsg/hushline#2372` | Accepted protocol implementation producing reviewed authenticated output, stable state transitions, required device results, and continuous-PQ failure semantics | Commit `1470c65380187184ce1ae5b6c3324c6ea2326254`; [ADR-0006](adr-0006-protocol-integration-readiness.md) and [readiness record](g7-readiness.json) | **Unsatisfied:** G7 is blocked before implementation and supplies no approved protocol library, suite, serialization, authenticated context, worker adapter, or protocol output |
| G8 / `scidsg/hushline#2373` | Accepted archive implementation producing every authenticated sender, recipient, self-history, and offline copy under a reviewed complete-copy contract | Commit `b7fd9a2292dd7c2f0311380a2180b2f62822e553`; [ADR-0007](adr-0007-pq-archive-readiness.md) and [readiness record](g8-readiness.json) | **Unsatisfied:** G8 is blocked before implementation and supplies no archive hierarchy, envelope, copy inventory, wrapping, lifecycle, recovery, or atomic-copy result |

A merged readiness artifact, issue order, or the existing classical message
flow is not proof that either gate passed. G9 cannot invent canonical envelope
bytes, signature input, nonce rules, required copy cardinality, authorization,
idempotency scope, commit boundaries, or acknowledgement semantics on behalf of
the missing designs and their human reviewers.

## Decision

G9 is blocked before implementation. Do not change the profile-submission or
reply path until G7 and G8 are accepted and available on `codex/epic-2365` as
production implementations with exact reviewed contracts. In particular, do
not:

- leave an opening message on classical encryption, or label a conversation
  protected when only later replies, transport output, or some copies satisfy
  the complete-copy contract;
- invent a signed-envelope format, canonicalization, signature algorithm,
  nonce derivation, context binding, logical identifier, device selection, or
  sender/recipient/archive copy inventory;
- acknowledge a message before all required protocol and archive records have
  committed, persist a partial required copy set, or emit user-visible
  messages, unread state, or notifications more than once;
- regenerate protocol output or ciphertext after an ambiguous result, accept
  the same idempotency identity with different bytes or context, or drop a
  message after returning a committed acknowledgement;
- accept malformed, unsigned, replayed, substituted, unauthorized, stale, or
  cross-conversation envelope values;
- use missing JavaScript, protocol failure, unavailable recipient material, or
  malformed client input to reach a plaintext or classical-only server
  fallback for a protected conversation; or
- claim real-browser, cryptographic, UX, fault-injection, or independent-review
  evidence that has not run.

No production browser asset, template, route, model, notification path, CSP,
dependency, or security claim is changed by this decision. Existing legacy
conversation and separate one-way intake behavior remain unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after the prerequisites pass | Current disposition |
| --- | --- | --- |
| Shared initial/reply coordinator | One browser coordinator used by profile submission and reply, with the reviewed protocol/archive inputs and no opening-message downgrade | Blocked; G7 and G8 supply no callable production outputs or exact contracts |
| Signed envelope and context | Canonical reviewed bytes binding application, account, conversation, logical message, sender, recipient, direction, devices, versions, suites, epochs, purposes, nonces, protocol output, archive copies, and authorization | Blocked; identifiers, signature input, canonicalization, and context rules are unspecified |
| Complete-copy inventory | Deterministic authenticated inventory covering sender and recipient records, all required recipient devices, self-history/archive, and offline delivery, with rejection of missing, extra, mixed, or substituted copies | Blocked; G7 device results and G8 archive copy inventory do not exist |
| Atomic server commit | One authorization and transaction boundary validating and persisting the logical message and all required records, deduplicating retries, and exposing the message only after the complete write | Blocked; schema, validation, authorization, and transaction contracts are unavailable |
| Stable retry and acknowledgement | Durable exact-byte retry across offline and ambiguous failures; stable logical/idempotency identity; same-result replay; different-byte collision rejection; committed acknowledgement recovery | Blocked; G7/G8 outputs and G6 outbox semantics were never implemented |
| Conversation side effects | Chronology, unread/read counts, generic notifications, deletion, and placeholders derived once from the committed logical message without partial or duplicate effects | Blocked; accepted commit and side-effect boundaries are unavailable |
| Fail-closed protected paths | Missing JavaScript, unsupported capability, malformed input, invalid protocol/archive output, and authorization failure disable the protected send without plaintext or classical fallback | Blocked; protected-conversation state and accepted error taxonomy are unspecified |
| Unchanged everyday UX | Draft preservation, existing unlock, one submit action, success destination, reply composer, accessibility, performance, CSP, and adjacent legacy intake regressions | Blocked pending an implementation and real-browser evidence |

## Required Validation After Unblocking

The implementation must provide linked, non-secret evidence for:

1. opening profile submissions and bidirectional replies across supported
   sender/recipient device combinations, including offline recipients and
   self-history, in Chromium, Firefox, and WebKit;
2. persisted-copy inspection proving every required sender, recipient, device,
   transport, and archive record belongs to one authenticated logical message
   and no protected opening or reply copy is plaintext or classical-only;
3. signature, authorization, nonce, context, logical identifier, conversation,
   participant, device, version, suite, epoch, purpose, direction, inventory,
   and ciphertext tamper, substitution, replay, omission, and extra-copy tests;
4. faults before and after browser state/outbox persistence, request dispatch,
   server validation, each required-copy write, transaction commit, response,
   acknowledgement persistence, notification enqueue, and client cleanup;
5. offline and ambiguous-result retries proving exact-byte reuse, one visible
   message, one set of count/notification effects, acknowledgement recovery,
   collision rejection, and no dropped committed send;
6. missing JavaScript, malformed payload, protocol/archive failure, missing
   device material, storage denial, and authorization rejection with no
   plaintext or classical-only protected fallback;
7. draft preservation and unchanged submit/unlock, destination, chronological
   display, unread/read, notification, participant deletion, placeholder, and
   adjacent legacy intake behavior; and
8. CSP, accessibility 100, performance at least 95, unchanged interaction
   count, responsiveness budgets, and capture-free synthetic UI artifacts.

Real-browser results, cryptographic review, and human security approval remain
pending until they are actually supplied. Fault instrumentation must not log
plaintext, private keys, protocol state, archive secrets, exact sensitive
ciphertext payloads, or authentication tokens.

## Unblocking and Review Sequence

1. Complete the earlier gate sequence, including pending G1 approval and a
   passing exact G2 protocol candidate.
2. Implement and accept G7 and G8 on `codex/epic-2365`; readiness-only records
   do not satisfy either prerequisite.
3. Update `g9-readiness.json` to pin those accepted commits and transcribe the
   exact envelope, context, nonce, inventory, transaction, idempotency,
   acknowledgement, authorization, and failure rules into failing tests.
4. Implement the smallest shared initial/reply coordinator and server commit
   path, then produce every validation item above without changing the normal
   interaction flow.
5. Obtain full-stack/security and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling or
   labelling protected delivery.

The implementation author cannot fill either reviewer disposition. A server
acknowledgement is meaningful only under the accepted transaction contract,
and retry safety requires stable protocol-produced bytes; neither can be
approximated around the existing classical flow.

## Consequences

- No unreviewed envelope, nonce, signature, copy inventory, transaction,
  idempotency rule, or classical fallback is introduced.
- Existing legacy conversation behavior and ciphertext remain intact.
- Every acceptance criterion and required fault boundary has an evidence slot
  rather than a fabricated prerequisite, browser result, or approval.
- G9 remains incomplete until G7 and G8 pass and the production integration,
  fault evidence, real-browser evidence, and human reviews exist.

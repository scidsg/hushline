# ADR-0006: Hybrid Handshake and Continuous-PQ Integration Readiness

Status: **Blocked before implementation**  
Date: 2026-09-25  
Decision gate: G7 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2372`

## Context

G7 must integrate the exact reviewed protocol library, suite, and serialization
behind a narrow worker adapter. It must bind the authenticated application
context and capability/version negotiation, establish sessions from claimed
prekeys while recipients are offline, process bidirectional and out-of-order
traffic, complete repeated post-handshake PQ epochs, replace sessions only
with authenticated authority, and expose a truthful compliance status. It
must reject replay, substitution, downgrade, and either-contribution failure
without logging key material or running cryptography on the UI thread.

Those behaviors depend on G5's accepted device/prekey implementation and G6's
accepted transactional browser-state implementation. The prerequisite
artifacts are available on this branch, but both record blocked decisions.
G2 also remains a no-go: there is no exact reviewed library, suite,
serialization, reproducible browser build, or independently observed
continuous-PQ/reference-peer evidence to integrate. The machine-readable
[G7 readiness record](g7-readiness.json) pins those findings and inventories
the implementation and review evidence that cannot safely be produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G5 / `scidsg/hushline#2370` | Accepted authenticated device membership and bounded, atomic prekey lifecycle | Commit `f9ba0777a5a4029a1c95bac3e5fed6c7199b9229`; [ADR-0004](adr-0004-device-prekey-readiness.md) and [readiness record](g5-readiness.json) | **Unsatisfied:** G5 is blocked before implementation; authenticated membership, prekey formats, atomic claim, freshness, and lifecycle rules remain unspecified |
| G6 / `scidsg/hushline#2371` | Accepted encrypted transactional ratchet storage, send/receive boundaries, outbox, replay state, and cross-context serialization | Commit `fe312ab3bef6ded364c115ec29b8c2c8f2dce60f`; [ADR-0005](adr-0005-transactional-browser-state-readiness.md) and [readiness record](g6-readiness.json) | **Unsatisfied:** G6 is blocked before implementation; persisted state, valid transitions, retry, replay, recovery, and ownership rules remain unspecified |
| G2 / `scidsg/hushline#2367` | Exact approved browser library, suite, serialization, source/artifact pin, reference interoperability, and observed continuous-PQ epochs | Commit `f84fb98e86286f3183f4c1f7e9f714549f10f9e2`; [ADR-0001](adr-0001-browser-protocol-candidate.md) and [evidence record](g2-evidence.json) | **Unsatisfied:** G2 is no-go at the reviewed revisions and explicitly forbids selecting or integrating a candidate |

A merged artifact, dependency order, package claim, successful handshake, or
ordinary ciphertext round trip is not proof that any gate passed. G7 cannot
invent the protocol inputs, state transitions, or authentication rules needed
to turn those results into production cryptography.

## Decision

G7 is blocked before implementation. Do not add a protocol dependency,
worker, adapter, application integration, new wire value, status claim, or CSP
source until G5 and G6 are accepted and G2 is replaced by a passing exact
candidate decision. In particular, do not:

- implement custom KEM mixing, change the reviewed library's ratchet logic, or
  translate through an unreviewed serialization profile;
- treat PQ setup followed by classical-only traffic, a disabled refresh path,
  or an unobserved epoch transition as continuous PQ compliance;
- accept participant, account, conversation, device, capability, version,
  suite, epoch, prekey, ciphertext, or transcript values outside the reviewed
  authenticated context;
- replace a session without authenticated authority, retry with regenerated
  ciphertext, accept a replay, or retain unbounded skipped keys, pending
  epochs, failures, or recovery attempts;
- fall back to classical-only traffic or create only a subset of required
  hybrid copies when a classical or PQ contribution fails;
- perform protocol cryptography on the UI thread, emit secret-bearing
  telemetry, fetch runtime cryptographic assets from a third party, or broaden
  CSP without explicit minimal-scope approval and regression tests; or
- claim protocol-vector, reference-peer, browser, performance, reproducible
  build, vulnerability, or independent-review evidence that has not run.

No production asset, dependency lockfile, template, route, state store, wire
format, CSP, or security claim is changed by this decision. Existing account
conversation and E2EE behavior remain unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after the prerequisites pass | Current disposition |
| --- | --- | --- |
| Exact protocol dependency | Approved library, suite, serialization, exact package/source/dependency revisions, integrity hashes, reproducible self-hosted build, SBOM, license, vulnerability disposition, and maintenance ownership | Blocked; G2 is no-go and no candidate is approved |
| Worker and narrow adapter | Self-hosted worker/WASM assets under the approved CSP; narrow typed operations for initialization, prekey establishment, encrypt/decrypt, state import/export, and non-secret status; no protocol reimplementation | Blocked; protocol API and state format are unselected |
| Authenticated context and negotiation | Canonical bindings for application, account, conversation, participant, device, capability, version, suite, session, prekey, transcript, epoch, and direction, with downgrade and cross-context rejection | Blocked; G3/G5 authentication and wire contracts are unspecified |
| Offline establishment and replacement | Atomic claimed-prekey consumption, offline recipient establishment, both contribution checks, transcript authentication, idempotent failure handling, and authenticated session replacement/reset | Blocked; G5 prekey and G6 transaction/recovery contracts are unavailable |
| Continuous PQ traffic | Bidirectional traffic with instrumented non-secret proof of repeated actual post-handshake PQ epoch completion, bounded skipped/out-of-order delivery, replay rejection, and library-defined ratchet behavior | Blocked; candidate evidence and valid transition/bounds contracts are unavailable |
| Complete-copy integration | Atomic integration with sender, recipient, offline/history, and every other required content copy; any missing or invalid hybrid result fails the whole write closed | Blocked; G3/G4 copy and transaction contracts are unavailable |
| Truthful application status | State derived from verified negotiated capability and completed current refresh behavior; handshake-only, disabled, failed, stale, or unobserved refresh can never be labelled compliant | Blocked; exact protocol state and approved product terminology are unavailable |
| Bounded failure behavior | Reviewed bounds and deterministic outcomes for malformed input, missing capabilities/prekeys, contribution failure, skipped messages, pending epochs, retries, replacement, corruption, storage denial, and worker termination | Blocked; G5/G6 bounds and recovery semantics are unavailable |
| Privacy, CSP, and performance | No secret/plaintext/private-state telemetry, UI-thread responsiveness budgets, worker isolation and termination behavior, unchanged CSP or approved minimal expansion, and unchanged everyday UX | Blocked pending exact assets and real-browser implementation |

## Required Validation After Unblocking

The implementation must provide linked, non-secret evidence for:

1. official protocol vectors and a pinned reference peer using the exact
   selected suite and serialization;
2. offline prekey establishment, bidirectional traffic, reload/recovery, and
   at least two independently observed post-handshake PQ epoch completions;
3. skipped, delayed, duplicated, and out-of-order delivery within reviewed
   bounds, plus deterministic rejection outside those bounds;
4. replay and substitution of participants, accounts, conversations, devices,
   capabilities, versions, suites, sessions, prekeys, epochs, transcripts, and
   ciphertexts;
5. authenticated session replacement and rejection of unauthorized, stale,
   rolled-back, cross-device, and cross-conversation replacement attempts;
6. separate classical-contribution and PQ-contribution failure injection,
   with no classical fallback, partial required-copy write, or compliant
   status;
7. malformed input, prekey depletion, storage denial, worker termination,
   concurrent contexts, retry, and failure-bound exhaustion without livelock,
   state divergence, or secret-bearing telemetry;
8. two matching clean builds, integrity verification, SBOM, license and
   vulnerability review, self-hosted asset loading, and CSP regression; and
9. real Chromium, Firefox, and WebKit worker traces covering responsiveness,
   accessibility, unchanged UX, and complete-copy confidentiality.

Instrumentation may expose only reviewed non-secret event and counter data.
It must never log plaintext, private keys, prekeys, message keys, chain/root
keys, shared secrets, serialized ratchet state, or sensitive tokens. Real
browser results, cryptographic review, and human security approval remain
pending until they are actually supplied.

## Unblocking and Review Sequence

1. Obtain the pending G1 approvals and replace the G2 no-go with a passing
   exact-candidate decision containing its required build, interoperability,
   epoch, browser, CSP, vulnerability, and ownership evidence.
2. Accept G3 and G4, then implement and accept G5 and G6 on
   `codex/epic-2365`; a readiness-only merge does not satisfy either gate.
3. Update `g7-readiness.json` to pin the accepted prerequisite commits and
   transcribe the exact suite, serialization, context, identifiers, state
   transitions, limits, and failure rules into failing tests.
4. Pin the reviewed dependency and self-hosted reproducible assets, implement
   the worker adapter and minimal application integration without changing
   library internals, and produce every validation item above.
5. Obtain cryptography/browser and independent security review at the exact
   implementation commit. Resolve blocking findings before enabling or
   labelling upgraded traffic.

The implementation author cannot fill either reviewer disposition. Status
must be derived from verified protocol behavior, not a configuration flag or
the existence of a handshake. Non-secret epoch instrumentation is evidence
for review, not permission to expose protocol secrets.

## Consequences

- No unreviewed cryptographic dependency, custom combiner, partial adapter,
  classical fallback, CSP expansion, or premature PQ claim is introduced.
- Existing legacy conversation behavior and ciphertext remain intact.
- Every acceptance criterion and adversarial scenario has a concrete evidence
  slot rather than a fabricated implementation or approval.
- G7 remains incomplete until its prerequisites pass and production
  integration, interoperability, repeated-epoch, browser, supply-chain, and
  human-review evidence exists.

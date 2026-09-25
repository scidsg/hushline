# ADR-0010: PQ Chat Conversation-Migration Readiness

Status: **Blocked before implementation**

Date: 2026-09-25

Decision gate: G11 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2376`

## Context

G11 must make PQ the automatic path for eligible authenticated conversations
without adding a setup flow, credential, pairing ceremony, confirmation, or
normal-path prompt. The first accepted protected write must advance an
authoritative conversation minimum monotonically. After that transition,
server and browser writers must reject version-2/classical writes even when a
stale client omits capability fields, an intermediary strips negotiation data,
a feature flag is disabled, or the application is rolled back.

The same timeline must continue to render retained legacy and protected
messages in chronological order. Security status is a property of each
authenticated message/version and the current conversation write floor:
activation cannot relabel historical classical ciphertext as PQ. An old or
temporarily failing client must preserve the draft and expose an accessible
update-needed or retry state; it cannot silently downgrade, report success, or
clear the composer before protected storage is acknowledged.
Authenticated negotiation also does not upgrade the separate classical
authentication limitation into a PQ-authentication claim.

These behaviors depend directly on G9's atomic protected-delivery contract and
G10's accepted capability, device, archive, stale-client, and lifecycle
behavior. Both prerequisite artifacts are present on this branch, but both
record blocked decisions and no production implementation. The
machine-readable [G11 readiness record](g11-readiness.json) pins those findings
and inventories the migration and review evidence that cannot safely be
produced yet.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G9 / `scidsg/hushline#2374` | Accepted protected opening/reply writes with authenticated versions and capabilities, complete-copy atomic commit, stable retry, and commit-coupled acknowledgement | Commit `4df7845b5d5a494f3314e24e3d8b551d99458878`; [ADR-0008](adr-0008-protected-delivery-readiness.md) and [readiness record](g9-readiness.json) | **Unsatisfied:** G9 is blocked before implementation and supplies no protected write, authenticated negotiation input, complete-copy transaction, stable retry, or acknowledgement implementation |
| G10 / `scidsg/hushline#2375` | Accepted device/archive lifecycle with capability freshness, stale-device rejection, epoch transitions, and routine fresh-browser recovery | Commit `a78b5c361cfbbf70a5678f4eabb8230dab359d90`; [ADR-0009](adr-0009-credential-lifecycle-readiness.md) and [readiness record](g10-readiness.json) | **Unsatisfied:** G10 is blocked before implementation and supplies no accepted capability/device lifecycle, archive epoch, stale-client recovery, or fresh-browser implementation |

A merged readiness artifact, issue order, or a closed checkbox is not proof
that either gate passed. G11 cannot invent the protected protocol version,
authenticated capability representation, eligibility rule, transition
transaction, downgrade error taxonomy, or rollback floor on behalf of the
missing designs and their human reviewers.

## Decision

G11 is blocked before implementation. Do not change production conversation
models, migrations, readers, writers, templates, browser assets, status copy,
or feature controls until G9 and G10 are accepted and available on
`codex/epic-2365` as production implementations with exact reviewed contracts.
In particular, do not:

- infer eligibility from unauthenticated or client-controlled capability
  fields, or treat a missing field as permission to write classically;
- select a protected version number or advance a conversation before the
  complete protected write and its minimum-version transition commit under the
  accepted transaction contract;
- decrease, clear, or bypass the protected write floor during a flag change,
  kill switch, deploy rollback, retry, restore, or request from an old client;
- rewrite, rewrap, relabel, or summarize retained legacy ciphertext as PQ, or
  derive per-message status from only the conversation's current version;
- clear a draft, show send success, update the timeline, or emit notification
  side effects before the accepted protected-storage acknowledgement;
- add a routine opt-in, setup wizard, credential, pairing step, confirmation,
  algorithm choice, or capability prompt; or
- claim migration, browser, accessibility, performance, downgrade-resistance,
  rollback, or independent-review evidence that has not run.

No production model, migration, route, browser asset, template, CSP, feature
flag, status label, dependency, or security claim is changed by this decision.
Existing legacy conversation behavior and ciphertext remain unchanged.

## Deferred Migration Contract

<!-- prettier-ignore -->
| Area | Evidence required after the prerequisites pass | Current disposition |
| --- | --- | --- |
| Eligibility and automatic activation | Reviewed eligibility derived from authenticated current account/device capabilities; normal login, open, and send flows activate without an opt-in, setup page, credential, pairing ceremony, confirmation, or added click | Blocked; G9/G10 supply no accepted capability or activation input |
| Monotonic conversation floor | Authoritative server state advances only forward in the same transaction as the first complete protected write; every later write is checked against that floor independent of request omissions, flags, or client age | Blocked; protected version and transaction semantics are unspecified |
| Authenticated negotiation | Canonical capability/version/suite/participant/device context is authenticated end to end, with omission, stripping, substitution, replay, fork, and stale-view rejection on server and client | Blocked; G9 has no envelope or capability binding and G10 has no lifecycle freshness contract |
| Mixed-history reader | One chronological timeline reads retained legacy and protected records; each record keeps its authenticated version and exact security description without re-encryption or relabelling | Blocked; accepted legacy/new schemas, envelope metadata, and archive readers do not exist |
| Status and details | Accessible conversation-level write state and per-message details distinguish legacy history, protected messages, pending/retry state, unsupported clients, and the classical-authentication limitation using approved non-misleading copy | Blocked; product terminology and authenticated status inputs are unapproved |
| Stale/old-client behavior | Server refuses classical or below-floor writes even with omitted negotiation fields; client keeps the draft and exposes update-needed guidance without reporting success or attempting fallback | Blocked; version floor, error taxonomy, and acknowledgement contract are unavailable |
| Retry and acknowledgement | Transient failures keep the exact draft/outbox operation; only a protected-storage acknowledgement clears the composer or creates success UI, and ambiguous retries remain idempotent | Blocked; G9 supplies no stable retry or commit-coupled acknowledgement implementation |
| Feature controls and kill switch | Controls may stop new activation or protected writes, but never lower an upgraded conversation's floor, enable a classical writer, hide retained protected reads, or alter per-message truth | Blocked; safe control ownership and writer/read behavior are unspecified |
| Deployment and rollback | Expand with legacy/protected readers before writers; set a tested rollback floor that retains protected reads and below-floor refusal; prohibit rollback to binaries that lack either invariant | Blocked; no production reader, writer, schema, or compatible deployment floor exists |
| Everyday UX and quality | Existing login, inbox, thread, and one-action send/reply flows; draft behavior; browser/private-mode support; accessibility 100; performance at least 95; and approved timing budgets remain intact | Blocked pending implementation and real-browser evidence |

## Required State Invariants After Unblocking

The implementation and tests must demonstrate all of these invariants without
assuming a particular unapproved wire format or protected version number:

1. The server is authoritative for a conversation's minimum accepted write
   version, and updates to it are monotonic under concurrent requests.
2. The first protected message and the floor advance are one atomic outcome;
   neither is visible alone.
3. A write below the floor fails closed whether its capability/version fields
   are explicit, absent, stripped, stale, replayed, or internally inconsistent.
4. Client-side checks provide early feedback but cannot replace server
   enforcement; stale assets and direct API callers receive the same refusal.
5. Feature controls can prevent new activation or protected writes but cannot
   reduce stored minimums or re-enable classical writes in upgraded threads.
6. Rollback retains protected readers and server-side floor enforcement. A
   binary that cannot do both is below the permitted rollback floor.
7. Each message's authenticated stored version drives its description. The
   current conversation floor never upgrades the claim for an older message.
8. A success state is reachable only from an acknowledgement for the complete
   protected commit. Rejection or uncertainty preserves the draft and safe
   retry identity without adding a fallback path.

## Required Validation After Unblocking

The implementation must provide linked, non-secret evidence for:

1. eligible and ineligible authenticated conversations across supported
   participant/device capability combinations, proving automatic activation
   adds no prompt, credential, pairing, page, confirmation, or click;
2. synthetic legacy-only, protected-only, and interleaved histories with exact
   chronology, decryptability, authenticated per-message versions, truthful
   details including the classical-authentication limitation, unread/read
   state, deletion, and notification behavior;
3. concurrent first-upgrade writes and every later lower-version attempt,
   including absent, stripped, substituted, replayed, forged, stale, and
   conflicting capability/version fields at both browser and direct APIs;
4. stale cached assets and old clients before and after activation, proving
   accessible update-needed behavior, draft preservation, no false success,
   no classical write, and recovery after a supported client loads;
5. network, protocol, storage, transaction, response, and acknowledgement
   failures proving retry guidance, exact-operation reuse, one committed
   message, and no premature composer clearing or side effect;
6. flag enable/disable/re-enable and kill-switch drills before and after
   activation, proving protected reads and stored minimums persist and no
   classical writer becomes reachable;
7. expand/deploy/rollback/roll-forward drills with mixed application versions,
   proving the safe reader/server-enforcement floor and refusing an unsafe
   rollback rather than losing reads or accepting downgrade writes; and
8. Chromium, Firefox, and WebKit normal/private modes, keyboard and screen
   reader states, accessibility 100, performance at least 95, approved timing
   budgets, synthetic before/after click and prompt counts, CSP, and
   capture-free Playwright artifacts.

Real-browser results, cryptographic review, product copy approval, and human
security approval remain pending until actually supplied. Instrumentation must
not log plaintext, drafts, private keys, protocol state, archive secrets, exact
sensitive ciphertext, authentication tokens, or stable user/device
fingerprints.

## Unblocking and Review Sequence

1. Complete the earlier gate sequence, including pending G1 approval and a
   passing exact G2 protocol candidate.
2. Implement and accept G9 and G10 on `codex/epic-2365`; readiness-only records
   do not satisfy either prerequisite.
3. Update `g11-readiness.json` to pin those accepted commits and transcribe the
   exact authenticated capability, eligibility, version, transition, status,
   error, acknowledgement, feature-control, and rollback rules into failing
   implementation tests.
4. Deploy additive readers and server-side floor enforcement before enabling
   any protected writer. Implement automatic activation and UI states only
   after mixed-version and downgrade tests pass.
5. Produce the required browser, private-mode, fault, stale-asset, flag, and
   rollback evidence, then obtain product/accessibility, full-stack/security,
   and independent security review at the exact implementation commit.

The implementation author cannot fill any reviewer disposition. Disabling a
feature is not a protocol downgrade mechanism, and application rollback is
safe only to a version that retains both protected reads and the authoritative
write floor.

## Consequences

- No unauthenticated negotiation, invented version transition, misleading
  history label, stale-client fallback, or unsafe rollback path is introduced.
- Existing conversation ciphertext and behavior remain intact.
- Every acceptance criterion and downgrade/rollback drill has an evidence slot
  rather than a fabricated prerequisite, browser result, or approval.
- G11 remains incomplete until G9 and G10 pass and the production migration,
  mixed-version, real-browser, rollback, quality, and human-review evidence
  exists.

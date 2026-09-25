# ADR-0011: PQ Chat Release-Validation Readiness

Status: **Blocked before validation**

Date: 2026-09-25

Decision gate: G12 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2377`

## Context

G12 must validate the integrated PQ-chat system rather than infer protection
from unit tests, configuration, upstream documentation, or the presence of a
handshake. Release evidence must cover reference interoperability and repeated
post-handshake PQ epochs; adversarial protocol and authorization behavior;
storage, network, crash, tab, and retry boundaries; every retained content
copy; actual supported browsers and restricted modes; unchanged adjacent
flows; accessibility and performance budgets; applicable dependency audits;
and independent review.

The report must bind every result to one exact implementation build, protocol
and wire suite, dependency graph, browser/driver build, hardware class,
network profile, corpus, and feature configuration. A pass without that
identity and a durable evidence link is not release evidence. Logs and
artifacts may contain reviewed non-secret counters, hashes, sizes, timings,
and synthetic identifiers, but never plaintext disclosures, drafts, private
keys or prekeys, shared/message/chain/root/archive secrets, serialized private
state, credentials, tokens, or production data.

G12 depends on G11's accepted integrated conversation migration. The local G11
artifact exists at commit `1646e579c03eed0d418037dab30d24e579963d68`, but it
records `blocked-prerequisites`, no production implementation, and no accepted
build. The machine-readable [G12 validation report](g12-validation-report.json)
therefore records required results as blocked and leaves measurements and
evidence links empty instead of fabricating successful validation.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G11 / `scidsg/hushline#2376` | Accepted integrated migration with authenticated negotiation, monotonic version floor, protected delivery/archive/device lifecycle, mixed-history readers, stale-client behavior, and safe rollout/rollback | Commit `1646e579c03eed0d418037dab30d24e579963d68`; [ADR-0010](adr-0010-conversation-migration-readiness.md) and [readiness record](g11-readiness.json) | **Unsatisfied:** G11 is blocked before implementation and supplies no integrated PQ-chat build, protocol behavior, copy paths, browser behavior, or release candidate to validate |

A merged readiness artifact, issue order, or closed checkbox is not proof that
G11 passed. G12 cannot choose missing protocol rules, manufacture an
implementation build, reinterpret classical account-chat evidence as PQ-chat
evidence, or fill human reviewer dispositions. G1's threat model and UX
contract also remain proposed for human approval, so there is no approved
threat matrix or complete-copy inventory against which to record a pass.

## Decision

G12 is blocked before validation. Do not run or publish a partial matrix as a
passing release report until G11 and all transitive gates are accepted and the
exact integrated release candidate is available on `codex/epic-2365`. In
particular, do not:

- treat a successful handshake as proof of continuous PQ protection;
- substitute same-implementation round trips for a pinned reference peer;
- omit failed, unsupported, private, storage-restricted, or stale-restore
  browser cases from the denominator;
- reduce the required corpus, participant/device set, retained-copy inventory,
  or fault matrix to meet a budget;
- accept a protected message when any required content-bearing copy is
  plaintext, classical-only, missing, unauthenticated, or on a stale epoch;
- report an ambiguous retry as safe without exact-operation reuse, one visible
  message, one side-effect set, and recovery of acknowledged writes;
- publish a score, timing percentile, audit result, CI pass, screenshot, or
  review that was not produced for the exact recorded build; or
- include secret-bearing diagnostic output in logs, traces, screenshots,
  archives, CI artifacts, or reviewer packets.

No production model, migration, route, cryptographic dependency, browser
asset, template, CSP, test runner, or workflow is changed by this decision.
Existing account-chat and anonymous one-way flows remain unchanged.

## Release-Evidence Contract

### Build and result identity

Every executable result must record the implementation commit; production
bundle and container digests; lockfile and SBOM digests; protocol dependency,
source revision, artifact integrity, suite, serialization, and wire version;
database revision; feature configuration; browser and driver versions;
operating system; hardware; network profile; synthetic corpus; run count; UTC
time; CI run; and artifact link. Reproduction instructions must start from the
recorded source and verified dependencies.

Changing any cryptographic artifact, wire behavior, copy topology, browser
build, corpus, or release configuration invalidates affected results. Warm and
cold timings require at least 30 measured runs per case on the same runner
class. Results must retain raw non-secret samples or summaries sufficient to
recompute the reported percentiles.

### Protocol and adversarial evidence

The exact selected suite must pass official vectors and a pinned independent
reference implementation for offline handshake, bidirectional messages, and
multiple observed post-handshake PQ epoch completions. The same harness must
cover bounded delayed, out-of-order, duplicated, and long-offline traffic;
prekey depletion and replenishment; rejected replay; and deterministic
skipped-key exhaustion without unbounded work or state.

Negative cases must independently forge, omit, reorder, replay, or substitute
identity/device membership, capabilities, versions, suites, conversations,
participants, purposes, directions, logical identifiers, prekeys, transcripts,
epochs, ciphertexts, archive wrappers, and copy inventories. It must test
unauthorized read/write and cross-account/device/conversation access, downgrade
attempts, stale and revoked devices, malformed inputs, and payloads at, below,
and above every reviewed limit. Failure must be closed and must not consume or
reuse secret material incorrectly.

### Fault, retry, and persisted-copy evidence

Fault injection must bracket browser state/outbox persistence, cryptographic
state transitions, request dispatch, server validation, each required-copy
write, transaction commit, response, acknowledgement persistence,
notification enqueue, render, and client cleanup. It must cover concurrent
tabs, worker/tab/browser termination, offline intervals, network loss and
duplication, quota/storage denial, retries, and known stale restores.

For every boundary, evidence must prove no key or nonce reuse, no divergent
ratchet/archive state, no duplicate visible message or notification/count side
effect, and no loss of a server-acknowledged message. Ambiguous operations must
reuse the accepted stable operation and exact protocol-produced bytes; a
collision or mismatched retry must fail.

The approved copy inventory must enumerate transport, sender/self history,
every current recipient/device, offline queue, retry/outbox, archive, backup,
restore, notification, export, deletion, and diagnostic paths. Each
content-bearing retained copy of a protected message must be either covered by
the approved classical+PQ hybrid and authenticated context or explicitly
prohibited. A generic notification may carry no content. A deliberate export
requires its separately approved user ceremony and label; it cannot silently
become a classical-only retained copy.

### Browser, UX, quality, and operational evidence

Real Chromium, Firefox, and WebKit builds must exercise normal and private
contexts plus unavailable/quota-limited storage and missing/partitioned
cross-tab APIs. The matrix must include fresh-browser retained history,
offline gaps, tabs/crashes/retries, password change and reset, logout/session
expiry, device and participant deletion, account deletion, notification modes,
mixed legacy/protected history, and the separate anonymous intake path.

The exact build must score 100 for accessibility and at least 95 for
performance on affected pages. Keyboard, screen-reader/live-status, CSP, and
zero-new-prompt/click behavior must pass. Cold and warm timing runs must enforce
the approved p95 regression ceilings, and no individual PQ task may block the
main thread for more than 50 ms without yielding. Payload/storage/amplification
and crypto-specific budgets must be approved before measurement; G12 cannot
invent thresholds omitted by the blocked protocol design.

Operational evidence must state supported limits, exhaustion behavior,
monitoring that contains no sensitive values or stable fingerprints, runbook
ownership, rollback floor, and residual limitations. Mandatory failures block
release; suppressing, retrying away, or marking them flaky does not pass the
gate.

## Required Checks After Unblocking

The final report must link results for repository lint; focused protocol,
authorization, persistence, copy-inventory, lifecycle, and browser tests; the
full behavior suite and CI-style coverage; `Workflow Security Checks`; CodeQL;
and the required GitHub checks. It must also link Python and Node runtime
dependency audits, the full Node audit when frontend/runtime dependencies
change, and Rust/WASM advisories, licenses, SBOM, source/artifact integrity,
and reproducible-build evidence when those components exist. Synthetic
end-to-end screenshots and traces must cover the approved flow matrix without
capturing secrets.

An audit blocked by infrastructure remains a failed mandatory evidence slot
until the protected workflow passes. A reachable runtime CVE blocks release
unless maintainers record a formal risk acceptance. Test-only success cannot
replace the real-browser matrix or human review.

## Unblocking and Review Sequence

1. Complete the earlier gate sequence, including human G1 approval, a passing
   exact G2 candidate, and accepted G3 through G11 implementations on
   `codex/epic-2365`.
2. Replace the blocked build identity and scenario slots in
   `g12-validation-report.json` with the exact release candidate and its
   approved protocol, copy inventory, limits, and crypto budgets.
3. Run protocol/reference, adversarial, authorization, fault, copy-audit,
   adjacent-flow, browser, accessibility, and benchmark matrices using only
   synthetic data; preserve durable, non-secret evidence links.
4. Run and link every applicable CI, workflow-security, CodeQL, coverage, and
   dependency/supply-chain check for the same candidate.
5. Obtain QA/security, browser/accessibility, operations, and independent
   security review at the exact implementation commit. Resolve mandatory
   failures and record residual limitations before release approval.

The implementation author cannot fill reviewer dispositions or approve a
failed gate. Each result must be traceable to the build that produced it, and
every claimed release property must have linked evidence rather than an empty
or inherited slot.

## Consequences

- No fabricated interoperability, browser, benchmark, CI, audit, screenshot,
  user-research, or independent-review claim is introduced.
- Existing E2EE behavior and adjacent flows remain unchanged.
- Every issue criterion has a versioned, machine-readable evidence slot with a
  defined identity and failure rule.
- G12 remains incomplete until G11 passes and the exact integrated candidate
  has complete passing evidence and human review with explicit residual
  limitations.

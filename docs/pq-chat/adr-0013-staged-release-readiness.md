# ADR-0013: PQ Chat Staged Release and Rollback Readiness

Status: **Blocked before release**

Date: 2026-09-26

Decision gate: G14 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2379`

## Context

Shipping PQ account chat is a security-critical production change, not the
automatic consequence of merging a library, a disabled feature flag, a
readiness document, or a research prototype. Release requires an exact,
independently reviewed integration; a human-approved runbook; staged schema,
reader, and writer deployment; synthetic smoke evidence; privacy-reviewed
aggregate health observations; a safe kill-switch and rollback drill; accurate
public documentation; and a deployment record for the approved population.

G14 depends on G13's accepted independent review and release decision. The
local G13 artifact exists at commit
`1d2c17f0ef4bc22694bd50ce1a24f892e8eb9cc1`, but it records
`blocked-prerequisite-and-human-review`, no review subject, no independent
review, and no human release approval. G1 is still pending human approval, G2
is a no-go at the reviewed revisions, and G3 through G12 remain blocked. The
machine-readable [G14 rollout record](g14-rollout-record.json) therefore leaves
all operational owners, thresholds, approvals, build identities, populations,
results, and release links pending.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G13 / `scidsg/hushline#2378` | Independent review of the exact validated integration, remediated and independently retested findings, reconciled security wording, and explicit human release approval | Commit `1d2c17f0ef4bc22694bd50ce1a24f892e8eb9cc1`; [ADR-0012](adr-0012-independent-review-readiness.md) and [review record](g13-independent-review.json) | **Unsatisfied:** G13 contains no release candidate, reviewer, report, finding disposition, retest, reconciled wording, or human release decision |

A closed issue, merge, passing legacy test suite, enabled configuration, or
calendar date is not release authorization. Production access and release
approval remain human actions. This packet does not deploy anything.

## Decision

G14 is blocked before release. Preserve the runbook below for review, but do
not execute a production phase until G1 through G13 are accepted for the exact
candidate, all final checks pass, integration conflicts are resolved, the
threshold and ownership record is complete, and the named human release
approver authorizes that phase.

No production model, migration, route, cryptographic dependency, browser asset,
template, CSP, feature control, telemetry, or documentation claim changes
through this decision. Existing E2EE and conversation behavior remain
unchanged.

## Invariants That Override Rollout Progress

Every phase, including rollback, must preserve these invariants:

1. Protected history remains readable by supported clients and eligible
   participants. Reader and required schema compatibility are not kill-switched
   away.
2. Once a conversation's authenticated version floor requires protected
   writes, no flag, stale client, deploy rollback, restore, or retry may create
   a classical-only send. When a protected writer is unavailable, sending
   fails closed with an actionable, accessible error.
3. A stopped or failed write preserves its local pending draft, operation
   identity, and protocol-produced bytes needed for safe retry. It must not
   consume fresh secret state, duplicate a visible message, or claim success.
4. Every required transport, self-history, recipient/device, offline, retry,
   archive, notification, export, backup, and deletion copy follows the
   reviewed complete-copy contract. Generic notifications contain no content.
5. Anonymous one-way intake and legacy account-chat history keep their reviewed
   behavior. A legacy message is never relabeled as PQ protected.
6. Health evidence contains no plaintext, drafts, keys, ratchet or archive
   state, ciphertext, credentials, tokens, stable user/account/device/
   conversation/message identifiers, or sensitive user-level events.

Any invariant breach stops advancement immediately even when aggregate numeric
thresholds appear healthy.

## Release Preflight

The release owner must link all of the following for one immutable candidate:

- approved G1 through G13 decisions and every child deliverable on
  `codex/epic-2365`;
- the signed, independently reviewed integration commit and verifiable release
  tag, production bundle and container digests, lockfile and SBOM digests,
  database revision, protocol dependency identity, suite, serialization and
  wire versions, and feature configuration;
- resolved integration conflicts and a conflict-free target-branch result;
- passing required CI, `Workflow Security Checks`, CodeQL, focused and full
  tests, coverage, browser/accessibility/performance evidence, and applicable
  dependency and supply-chain audits for that candidate;
- closed or explicitly disposed independent-review findings, required retests,
  affected G12 reruns, and reconciled security wording;
- named release, operations, security, product, incident, and rollback owners;
- privacy approval for the exact aggregate observations, dimensions, minimum
  aggregation, retention, access, thresholds, dashboards, and alerts; and
- the named human release approver's dated approval of this runbook, candidate,
  initial population, thresholds, observation windows, and rollback authority.

Changing the code, dependency set, database contract, build output, feature
configuration, population rule, thresholds, or observation design invalidates
the affected approvals and evidence.

## Staged Rollout Runbook

Each phase has a separate human gate. Record start and end times, immutable
configuration identity, approved population definition, non-secret results,
incidents, owner decision, and evidence before advancing. Do not infer approval
from elapsed time or the absence of an alert.

### R0: Prepare and hold writers off

Record the approved candidate and owners. Verify that the global activation
control and protected-write control start closed. Confirm the release record,
dashboards, paging, incident channel, rollback authority, and tested recovery
artifact are available before a production deploy.

### R1: Expand schema and deploy readers

Deploy only the reviewed additive schema and backward-compatible readers. Keep
activation and protected writers off. Verify, with synthetic accounts, that
legacy history still reads accurately, protected fixtures read only through the
reviewed path, unsupported or malformed states fail closed, and the previous
reader-compatible application build can be restored without a destructive
schema rollback.

Do not contract schema or remove legacy readers during this issue's rollout.
R1 must be fully deployed and observed before any R2 writer is enabled.

### R2: Enable synthetic writers only

Enable the reviewed writer solely for explicitly allowlisted synthetic
accounts. Exercise offline handshake, bidirectional messages, repeated
post-handshake PQ epoch refresh, self-history and every recipient/device copy,
fresh-browser archive recovery, long-offline delivery, ambiguous retry,
concurrent tabs, password and device lifecycle, notifications, export/deletion,
writer stop, deploy rollback, and restore. Use no real disclosure data.

Advance only when every synthetic result and required copy audit passes, the
observation window completes, all health thresholds pass, and the named human
gate approver records the decision.

### R3: Enable the approved eligible canary

Apply the preapproved eligibility rule and bounded canary size; do not select or
observe accounts through stable telemetry identifiers. Threads not explicitly
eligible stay on their existing behavior. An eligible conversation upgrades
only through the reviewed authenticated negotiation, and its version floor is
monotonic thereafter.

During the approved observation window, operations reviews only the approved
aggregate counters, rates, distributions, and performance percentiles. Advance,
hold, or roll back through a recorded human gate decision.

### R4: Expand within the approved eligible population

Increase exposure only through the recorded steps and maximum population that
the human release approval names. Repeat the R3 observation and gate at each
step. A phase approval cannot authorize a larger or materially different
population, deployment, region, tenant, browser support set, or security claim.

### R5: Complete or hold

After the final observation window, record the exact released version,
production configuration, approved and reached population, aggregate results,
incidents, rollback status, remaining limitations, gate decisions, and release
link. Keep compatible readers and schema for the documented retention window.
Removing rollout controls or contracting schema requires a separately reviewed
change; rollout completion does not authorize it.

## Privacy-Preserving Health Contract

Before R1, privacy and security reviewers must approve every metric and set its
owner, numerator, denominator, minimum aggregation threshold, alert threshold,
observation window, retention, access policy, dashboard, and response action.
Missing denominators, quiet dashboards, or empty evidence do not constitute a
pass.

The minimum observation set is aggregate counts or distributions for:

- attempted, completed, rejected, and failed protected handshakes;
- attempted, acknowledged, safely retried, rejected, and failed protected
  sends;
- successful and failed protected reads and archive recovery;
- completed post-handshake PQ refresh epochs and refresh failures;
- protected-write-unavailable and stale/downgrade attempts;
- duplicate-visible-message, acknowledged-message-loss, copy-audit, and
  authorization invariant failures; and
- approved p50/p95 operation latency, payload/storage amplification, browser
  main-thread budget, and application error/availability regressions.

Permitted dimensions must be low-cardinality and approved in advance, such as
rollout phase, reviewed protocol version, and coarse client family. Do not log
raw request context or introduce stable pseudonyms, hashes, fingerprintable
dimension combinations, per-account sampling, event joins, or drill-downs that
could reconstruct a user's activity. Suppress any bucket below the approved
minimum aggregation threshold and delete raw aggregation inputs under the
approved short retention policy.

The following always trigger an immediate hold and writer stop: any
classical-only write to an upgraded conversation; protected-history loss; an
authorization or complete-copy failure; duplicate or lost acknowledged
messages; secret, content, ciphertext, or stable identifier exposure in
telemetry; or an unreviewed security-claim mismatch. Quantitative failure-rate
and performance thresholds remain pending until owners approve them before
rollout; this packet does not invent passing values.

## Kill Switch and Rollback Drill

The kill switch has two fail-closed operations: stop new conversation
activation, then stop new protected writes. It never lowers a conversation's
version floor, enables a classical writer, disables protected/legacy readers,
deletes browser or server state, clears a draft, or marks a pending send as
delivered. Affected composers retain their local draft and show an accessible,
actionable explanation that sending is temporarily unavailable and can be
retried safely when restored.

The approved drill must use synthetic accounts and prove all of the following:

1. activate a synthetic conversation and complete enough traffic to cross
   multiple PQ refresh epochs and persist every required copy;
2. preserve an unsent draft and an ambiguous pending operation, invoke the
   writer stop, and verify no classical send, duplicate, or success indication;
3. read legacy and protected history while writers are stopped;
4. restore the previous reader-compatible application build without reverting
   additive schema, weakening the floor, or losing protected data;
5. restore the reviewed writer and retry with the accepted operation identity
   and bytes, producing exactly one visible and acknowledged message;
6. exercise an unsupported stale client and confirm an actionable blocked-send
   state without downgrade; and
7. reconcile aggregate counters, alerts, incident ownership, recovery time,
   screenshots, and evidence without recording secrets or real user data.

If the current release cannot safely retry the pending operation, it must keep
the draft and explicitly require the user to review and resubmit after recovery;
it may not silently construct a replacement send. A schema rollback is not an
incident shortcut. Contracting data structures occurs only after the approved
compatibility and retention window in a separate change.

## Documentation and Release Evidence

`docs/TWO-WAY-CHAT-E2EE.md` and `docs/USE-CASES.md` currently describe the
deployed classical account-chat design accurately. They must not claim PQ chat
while G14 is blocked. Before R3, the independently reviewed wording must update
both documents for the exact release and clearly state:

- which complete copies receive hybrid PQ confidentiality and that successful
  ongoing traffic performs continuous PQ refresh;
- that legacy history is excluded and is never relabeled as PQ protected;
- archive, fresh-browser, offline, deletion, export, and current recovery
  behavior;
- archive compromise, stale restore, browser-state loss, and recovery limits;
- that authentication remains classical and is not PQ authentication;
- the trustworthy served-JavaScript, browser-state loss, password guessing,
  metadata, device compromise/revocation, and retroactive-erasure limits; and
- eligibility, unsupported/stale-client behavior, fail-closed sending, and how
  preserved pending drafts are resumed after an operational stop.

The final release record must link the published version/release, approved and
reached population, every phase decision, synthetic smoke and rollback-drill
result, privacy approval, aggregate observation summary, incidents and
resolutions, documentation revision, and the final human production decision.
No artifact may contain real disclosures or sensitive user-level data.

## Consequences

- The release procedure, observation boundary, kill-switch semantics, and
  evidence slots are reviewable without pretending the blocked implementation
  exists.
- Existing E2EE behavior and public documentation remain accurate and
  unchanged.
- Production deployment, population selection, metric approval, and release
  approval remain explicitly human-owned.
- G14 remains incomplete until the exact reviewed build is actually deployed
  through the approved stages and the production release record links every
  required result and gate decision.

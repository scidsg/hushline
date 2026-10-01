# Post-Quantum Chat Review Packets

The PQ chat discovery work is split into independently reviewable gates:

- **G1:** this directory's baseline flow, unchanged-UX contract, and threat
  model remain proposed for human approval below. The
  [approval record](g1-approval-record.json) pins the review subject and keeps
  the gate open until the required human decisions are recorded.
- **G2:** the [browser protocol candidate evaluation](candidate-evaluation.md),
  [machine-readable evidence manifest](g2-evidence.json), and
  [go/no-go ADR](adr-0001-browser-protocol-candidate.md) record the browser
  implementation feasibility result for `scidsg/hushline#2397`. The
  [isolated synthetic browser prototype](../../prototypes/pq-ratchet/README.md)
  supplies an executable harness but no unexecuted result or missing human
  disposition is treated as evidence.
- **G3:** the [complete-design ADR](adr-0002-complete-protocol-design-readiness.md),
  [implementable protocol](protocol-design.md), [wire fixtures](g3-wire-fixtures.json),
  and [machine-readable review record](g3-readiness.json) provide the combined
  development contract for `scidsg/hushline#2398` (which replaces delivery
  scope from `scidsg/hushline#2368`). Independent cryptographic review and the
  recorded G1/G2 release evidence remain pending.
- **G4:** the [server-storage readiness ADR](adr-0003-server-storage-api-readiness.md)
  and [machine-readable readiness record](g4-readiness.json) preserve G3 as a
  hard prerequisite for `scidsg/hushline#2369` and inventory the schema, API,
  migration, and test evidence that cannot safely be implemented yet.
- **G5:** the [device and prekey readiness ADR](adr-0004-device-prekey-readiness.md)
  and [machine-readable readiness record](g5-readiness.json) preserve G4 as a
  hard prerequisite for `scidsg/hushline#2370` and inventory the enrollment,
  membership, prekey-lifecycle, privacy, and failure evidence that remains
  blocked.
- **G6:** the [transactional browser-state readiness ADR](adr-0005-transactional-browser-state-readiness.md)
  and [machine-readable readiness record](g6-readiness.json) preserve G3 as a
  hard prerequisite for `scidsg/hushline#2371` and inventory the encrypted
  storage, atomic send/receive, cross-context serialization, recovery, and
  browser evidence that remains blocked.
- **G7:** the [protocol integration readiness ADR](adr-0006-protocol-integration-readiness.md)
  and [machine-readable readiness record](g7-readiness.json) preserve G5 and
  G6 as hard prerequisites for `scidsg/hushline#2372` and inventory the exact
  dependency, worker adapter, authenticated context, continuous-PQ epoch,
  failure, interoperability, and supply-chain evidence that remains blocked.
- **G8:** the [archive readiness ADR](adr-0007-pq-archive-readiness.md) and
  [machine-readable readiness record](g8-readiness.json) preserve G4 and G6 as
  hard prerequisites for `scidsg/hushline#2373`, confirm that G3 supplied no
  accepted archive construction, and inventory the wrapping, complete-copy,
  fresh-browser, lifecycle, authorization, deletion, export, and
  archive-compromise evidence that remains blocked.
- **G9:** the [protected-delivery readiness ADR](adr-0008-protected-delivery-readiness.md)
  and [machine-readable readiness record](g9-readiness.json) preserve G7 and
  G8 as hard prerequisites for `scidsg/hushline#2374` and inventory the
  initial-send, reply, signed-envelope, complete-copy, idempotency, atomic
  acknowledgement, failure, and unchanged-workflow evidence that remains
  blocked.
- **G10:** the [credential-lifecycle readiness ADR](adr-0009-credential-lifecycle-readiness.md)
  and [machine-readable readiness record](g10-readiness.json) preserve G5, G8,
  and G9 as hard prerequisites for `scidsg/hushline#2375` and inventory the
  password, session, device-revocation, archive-rotation, stale-device,
  deletion, compromise-boundary, and unchanged-unlock evidence that remains
  blocked.
- **G11:** the [conversation-migration ADR](adr-0010-conversation-migration-readiness.md)
  and [machine-readable readiness record](g11-readiness.json) record the
  implementation for `scidsg/hushline#2406`: authenticated negotiation,
  monotonic versions, mixed-history truth, stale-client refusal, draft safety,
  and rollout controls. Browser, quality, and independent review evidence is
  still pending.
- **G12:** the [release-validation readiness ADR](adr-0011-release-validation-readiness.md)
  and [versioned validation report](g12-validation-report.json) preserve G11
  as a hard prerequisite for `scidsg/hushline#2377` and inventory the
  interoperability, adversarial, fault, persisted-copy, real-browser,
  quality-budget, CI, audit, and human-review evidence that remains blocked.
- **G13:** the [independent-review readiness ADR](adr-0012-independent-review-readiness.md)
  and [versioned review record](g13-independent-review.json) preserve G12 as a
  hard prerequisite for `scidsg/hushline#2378` and define the human reviewer
  booking, full-integration scope, finding ownership, remediation, independent
  retest, residual-risk, evidence-rerun, security-wording, and release-gate
  records that remain blocked or pending.
- **G14:** the [staged-release readiness ADR and runbook](adr-0013-staged-release-readiness.md)
  and [versioned rollout record](g14-rollout-record.json) preserve G13 as a
  hard prerequisite for `scidsg/hushline#2379` and define preflight approval,
  readers-before-writers staging, synthetic smoke checks, privacy-preserving
  health observations, stop thresholds, safe rollback, documentation, and
  production evidence that remain blocked or pending.

G2 is a **no-go at the reviewed revisions**. The isolated prototype adds no
production cryptographic dependency and changes no production behavior. Its
SPQR wire observer, traffic faults, reload path, benchmark collection, and CSP
probe are ready to execute after the dependency lock is generated and reviewed.
Missing real-browser, reference-peer, reproducibility, vulnerability, and
ownership evidence is recorded as missing rather than inferred from harness
code or upstream claims.

G3 is **proposed for independent cryptographic review**. `HL-PQCHAT-1` now pins
the transport and archive suites, authenticated context, account/device/prekey
lifecycle, password-root and browser storage hierarchy, archive epochs,
complete-copy inventory, atomic state transitions, migration/rollback rules,
failure behavior, data-flow diagrams, and executable structural wire fixtures.
The fixtures do not claim fabricated cryptographic vectors. G1 acceptance, G2
execution/reference-peer evidence, and both named G3 human reviews remain
release gates rather than blockers to dependent development.

G4's checked-in readiness packet remains **incomplete before implementation**,
but G3 now supplies its development contract. G4 may implement against that
versioned proposal while keeping review as a release gate. Production
conversation models, migrations, lifecycle code, and message routes remain
unchanged in the current packet.

G5 is **blocked before implementation** because G4 produced no accepted device
storage, authorization, authenticated-envelope, or transaction contract. No
device or prekey records, endpoints, browser enrollment flow, or PQ chat claim
is added; existing E2EE behavior remains unchanged.

G6 is **implemented for integration with independent review pending**. The
browser adapter provides encrypted device-scoped IndexedDB records, fenced
cross-context ownership, atomic pending-send/outbox and receive/replay
transactions, exact-byte retry, durable outgoing deduplication, bounded state,
and fail-closed cleanup and recovery behavior. It does not independently
enable a PQ writer or make a PQ chat product claim; protocol-worker integration
and release evidence remain pending.

G7 is **blocked before implementation** because G5 remains blocked, G6 awaits
integration review, and G2 still records a no-go for every reviewed browser
protocol candidate. No protocol dependency, worker/adapter, handshake, ratchet
integration, CSP change, or PQ chat claim is added; existing E2EE behavior
remains unchanged.

G8's checked-in readiness packet remains **incomplete before implementation**
because G4 and the G6 archive-worker integration have not produced their full
evidence. G3 now supplies the archive construction, hierarchy, context,
inventory, epoch, and recovery
development contract while independent review remains a release gate. The
current packet adds no archive key, copy, schema, recovery path, or export
change.

G9 is **blocked before implementation** because G7 and G8 are both blocked and
there is no accepted protocol output, archive-copy construction, signed
envelope, complete-copy inventory, or atomic delivery contract to wire into
initial messages and replies. No production message path, template, browser
asset, fallback, notification, or conversation behavior is changed.

G10 is **blocked before implementation** because G5, G8, and G9 are blocked and
there is no accepted device membership, archive hierarchy, complete-copy
delivery, revocation, or epoch-transition contract to rotate safely. No
production password, session, device, archive, account-deletion, emergency-exit,
or browser-state behavior is changed.

G11 is **implemented for integration with validation and review pending**.
Eligible conversations migrate automatically on the first complete protected
write, upgraded floors remain monotonic, mixed history retains per-message
truth, old writers fail closed, and deployment controls cannot reactivate a
classical writer. No merge or production-release approval is asserted.

G12 is **pending validation**. G11 now supplies an integrated build, but the
versioned report still needs the required browser, adversarial, quality,
rollback, audit, and human-review results at the final revision. Existing
readiness entries do not become release evidence automatically.

G13 is **blocked before independent review** because G12 is blocked and
supplies no accepted release candidate, pinned dependency identity, or passing
validation evidence. Reviewer booking remains a human action, and every review,
finding, retest, risk disposition, wording reconciliation, and release decision
field remains empty; the packet does not represent an independent audit.

G14 is **blocked before release** because G13 is blocked and supplies no
independently reviewed release candidate or human release approval. No schema,
reader, writer, feature control, monitoring, deployment, public PQ claim, or
production population changes through the readiness packet. The rollout record
keeps every approval, threshold, owner, release identity, production result, and
gate decision empty until humans provide linked evidence for the exact release
candidate.

## G1 Review Packet

Status: **Proposed for human approval**  
Issue: `scidsg/hushline#2396` (replaces delivery scope from
`scidsg/hushline#2366`)<br>
Parent epic: `scidsg/hushline#2365`  
Baseline commit: `ab1d5ce3` (`v0.7.25`)  
Review packet commit: `37abae6e11dd9c0e8306f5e962ae97504f5c0888`<br>
Recorded: 2026-09-24

This packet defines the product and security contract that must be approved
before implementation details are selected for post-quantum (PQ) account chat.
It closes only the epic's G1 review gate after the required human approvals are
recorded. It does not select a protocol, claim that PQ chat is implemented, or
change production behavior.

The contract is grounded in:

- [Hush Line use cases](../USE-CASES.md), especially the account conversation
  and anonymous disclosure paths;
- [current two-way chat E2EE reference](../TWO-WAY-CHAT-E2EE.md);
- [repository threat model](../THREAT-MODEL.md); and
- [ISO 37002](../ISO-37002.md), especially documented review and approval,
  data protection, confidentiality, accessible reporting channels, change
  control, and measurable evaluation.

## Review Artifacts

- [Baseline flow and evidence checklist](baseline-flows.md) maps current
  behavior, participant topology, browser evidence, and synthetic artifacts.
- [Unchanged-UX and security contract](unchanged-ux-contract.md) defines the
  claim matrix, history-availability rule, downgrade policy, UX budgets, and
  private-browsing behavior.
- [PQ chat threat model](threat-model.md) defines assets, adversaries, trust and
  compromise boundaries, and what revocation can and cannot repair.
- [G1 approval record](g1-approval-record.json) pins the exact packet revision
  and artifact digests and provides criterion-level product and security
  disposition fields.

The committed browser artifacts referenced by this packet use only seeded,
fictional accounts. They are engineering evidence, not user research, an
independent audit, or evidence about production data.

## Acceptance Traceability

<!-- prettier-ignore -->
| Issue criterion | Evidence for review |
| --- | --- |
| Map login/unlock, send/reply, offline and fresh-browser history, tabs, password lifecycle, deletion, notifications, aliases, export/deletion, anonymous flows, browsers, and topology | [Flow checklist](baseline-flows.md#flow-checklist), [browser/storage matrix](baseline-flows.md#browser-and-storage-support-baseline), [topology](baseline-flows.md#participant-topology) |
| Approve the security claim matrix | [Claim matrix](unchanged-ux-contract.md#security-claim-matrix) |
| Preserve history without new credentials, pairing, apps, or prompts; record reset limitation | [History contract](unchanged-ux-contract.md#history-availability-contract), [password flows](baseline-flows.md#password-change-reset-and-account-recovery) |
| Specify compromise and trust boundaries and revocation limits | [Trust boundaries](threat-model.md#trust-and-compromise-boundaries), [revocation matrix](threat-model.md#revocation-and-repair-matrix) |
| Approve measurable UX/performance budgets and restricted-storage behavior | [Budgets](unchanged-ux-contract.md#measurable-ux-and-performance-budgets), [restricted environments](unchanged-ux-contract.md#private-browsing-and-storage-restrictions) |

## Required Reviewer Disposition

Approval is a human governance action. A code-authoring agent cannot fill the
reviewer or evidence fields, infer approval from a merge, or mark G1 complete.
The approving review must identify this packet's commit and explicitly accept
or reject every row below. The authoritative dispositions and dated evidence
links are recorded in `g1-approval-record.json`; the current record is pending.

<!-- prettier-ignore -->
| Decision ID | Decision | Product maintainer | Security reviewer | Status |
| --- | --- | --- | --- | --- |
| G1-D1 | Preserve the everyday flows and zero-new-prompt rules in the UX contract | Pending | Review | Pending |
| G1-D2 | Require complete-copy hybrid PQ confidentiality with no classical-only downgrade | Review | Pending | Pending |
| G1-D3 | Accept classical authentication as an explicit limitation, not a PQ claim | Review | Pending | Pending |
| G1-D4 | Accept the archive-compromise and browser-erasure limits as stated | Review | Pending | Pending |
| G1-D5 | Accept the malicious-served-JavaScript exclusion and messaging limits | Review | Pending | Pending |
| G1-D6 | Preserve normal-login history access and the reset-without-old-secret limitation | Pending | Pending | Pending |
| G1-D7 | Accept the browser/storage support matrix and fail-closed behavior | Pending | Pending | Pending |
| G1-D8 | Accept the measurable accessibility, performance, and flow budgets | Pending | Review | Pending |

`Review` means the role must verify consistency but is not the designated final
approver for that row. `Pending` means affirmative approval is required. A
rejection must link a replacement decision and update all affected artifacts.
Any proposed UX regression or weaker confidentiality claim reopens G1 for
explicit product and security reconsideration.

### Approval Record

<!-- prettier-ignore -->
| Role | Reviewer | Disposition | Reviewed commit | Dated evidence |
| --- | --- | --- | --- | --- |
| Product maintainer | Pending | Pending | Pending | Link to approving review or signed decision required |
| Security reviewer | Pending | Pending | Pending | Link to approving review or signed decision required |

An approval applies only to the recorded commit. Later material changes require
both roles to confirm or replace their disposition.

## Completion Gate

G1 is complete only when all of the following are true:

1. G1-D1 through G1-D8 are explicitly approved by the designated humans for
   the exact reviewed commit.
2. Rejected or qualified rows have no unresolved blocking decision.
3. The synthetic evidence index remains accurate for that commit; later test
   results are linked without rewriting them as user research.
4. The approved packet is available on `codex/epic-2365` before dependent
   cryptographic implementation begins.

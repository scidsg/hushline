# Post-Quantum Chat Review Packets

The PQ chat discovery work is split into independently reviewable gates:

- **G1:** this directory's baseline flow, unchanged-UX contract, and threat
  model remain proposed for human approval below.
- **G2:** the [browser protocol candidate evaluation](candidate-evaluation.md),
  [machine-readable evidence manifest](g2-evidence.json), and
  [go/no-go ADR](adr-0001-browser-protocol-candidate.md) record the browser
  implementation feasibility result for `scidsg/hushline#2367`.
- **G3:** the [complete-design readiness ADR](adr-0002-complete-protocol-design-readiness.md)
  and [machine-readable readiness record](g3-readiness.json) preserve the
  prerequisite blocker for `scidsg/hushline#2368` and inventory every deferred
  design and review artifact.
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
- **G11:** the [conversation-migration readiness ADR](adr-0010-conversation-migration-readiness.md)
  and [machine-readable readiness record](g11-readiness.json) preserve G9 and
  G10 as hard prerequisites for `scidsg/hushline#2376` and inventory the
  authenticated negotiation, monotonic version, mixed-history, truthful
  status, stale-client, draft-safety, feature-control, and rollback evidence
  that remains blocked.
- **G12:** the [release-validation readiness ADR](adr-0011-release-validation-readiness.md)
  and [versioned validation report](g12-validation-report.json) preserve G11
  as a hard prerequisite for `scidsg/hushline#2377` and inventory the
  interoperability, adversarial, fault, persisted-copy, real-browser,
  quality-budget, CI, audit, and human-review evidence that remains blocked.

G2 is a **no-go at the reviewed revisions**. It does not add a cryptographic
dependency or change production behavior. Missing real-browser, continuous-PQ
epoch, reference-peer, reproducibility, vulnerability, and ownership evidence
is recorded as missing rather than inferred from upstream claims.

G3 is **blocked before design** because G1 remains pending human approval and
G2 has no passing protocol candidate or reviewed suite. No combined protocol,
archive, device-state, wire, or migration design is selected, and all reviewer
dispositions remain pending.

G4 is **blocked before implementation** because G3 produced no reviewed schema
or protocol contract. Production conversation models, migrations, lifecycle
code, and message routes remain unchanged; in particular, no unreviewed
classical fallback or incomplete device/archive-copy write path is introduced.

G5 is **blocked before implementation** because G4 produced no accepted device
storage, authorization, authenticated-envelope, or transaction contract. No
device or prekey records, endpoints, browser enrollment flow, or PQ chat claim
is added; existing E2EE behavior remains unchanged.

G6 is **blocked before implementation** because G3 produced no accepted
protocol, state-transition, archive, device-state, or recovery contract. No
ratchet state, IndexedDB adapter, durable outbox, cross-tab lock, or PQ chat
claim is added; existing E2EE behavior remains unchanged.

G7 is **blocked before implementation** because G5 and G6 are both blocked and
G2 still records a no-go for every reviewed browser protocol candidate. No
protocol dependency, worker/adapter, handshake, ratchet integration, CSP
change, or PQ chat claim is added; existing E2EE behavior remains unchanged.

G8 is **blocked before implementation** because G4 and G6 are both blocked and
G3 produced no accepted archive construction, key hierarchy, wrapping context,
copy inventory, epoch lifecycle, or recovery contract. No archive key, copy,
schema, browser recovery path, export change, or PQ chat claim is added;
existing E2EE behavior remains unchanged.

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

G11 is **blocked before implementation** because G9 and G10 are blocked and
there is no accepted protected write, acknowledgement, capability,
conversation-version, archive, or lifecycle contract to migrate safely. No
production model, migration, route, browser asset, template, feature control,
legacy reader, status copy, or conversation behavior is changed.

G12 is **blocked before validation** because G11 is blocked and supplies no
accepted integrated PQ-chat build to test. The report records every required
result as blocked with no evidence link or measurement; it does not turn
legacy tests, upstream claims, or this readiness review into release evidence.

## G1 Review Packet

Status: **Proposed for human approval**  
Issue: `scidsg/hushline#2366`  
Parent epic: `scidsg/hushline#2365`  
Baseline commit: `ab1d5ce3` (`v0.7.25`)  
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
or reject every row below.

<!-- prettier-ignore -->
| Decision ID | Decision | Product maintainer | Security architect | Status |
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
| Security architect | Pending | Pending | Pending | Link to approving review or signed decision required |

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

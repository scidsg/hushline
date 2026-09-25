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

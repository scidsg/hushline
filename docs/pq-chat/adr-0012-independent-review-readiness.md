# ADR-0012: PQ Chat Independent Review and Retest Readiness

Status: **Blocked before independent review**

Date: 2026-09-25

Decision gate: G13 of `scidsg/hushline#2365`

Issue: `scidsg/hushline#2378`

## Context

G13 requires an independent assessment of Hush Line's complete deployed
PQ-chat design. An upstream protocol audit, primitive review, initial spike,
same-author review, or test-suite pass does not assess Hush Line's adapter,
browser state, archive, authorization, retained copies, migration, deployment,
or operational behavior.

The assessment must be booked early enough to reserve an independent reviewer
and a remediation retest window, but its final conclusions must identify the
exact release-candidate revision and pinned dependencies. It must cover the
protocol adapter and build supply chain; key hierarchy and archive; device
authorization; concurrency; API and storage; CSP and served JavaScript;
migration and lifecycle behavior; claimed guarantees; and operational
disable, rollback, and compromise recovery. Transport is only one content
path: the reviewer must trace the archive and every alternate content-bearing
copy as well.

G13 depends on G12's accepted release-candidate validation. The local G12
artifact exists at commit `21b356c81e488b6a47c185a6b4788b3a0ba9a0b4`, but
it records `blocked-prerequisite`, no integrated release candidate, no pinned
dependency identity, and no passing validation results. No independent
reviewer, booking, report, finding, retest, or human release decision is
present. The machine-readable [G13 review record](g13-independent-review.json)
therefore preserves those fields as pending or blocked rather than presenting
this preparation as an audit.

This gate implements the documented-audit, impartiality, corrective-action,
and management-review principles in ISO 37002 sections 9.2, 9.3, and 10.2. It
does not turn repository authorship into independent review authority.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G12 / `scidsg/hushline#2377` | Accepted integrated release candidate with exact pinned build/dependency identity and complete protocol, adversarial, fault, copy, browser, quality, CI, audit, and human-review evidence | Commit `21b356c81e488b6a47c185a6b4788b3a0ba9a0b4`; [ADR-0011](adr-0011-release-validation-readiness.md) and [validation report](g12-validation-report.json) | **Unsatisfied:** G12 is blocked before validation and supplies no release candidate or passing evidence against which an independent reviewer can make final findings |

A merged readiness document, issue sequence, upstream audit, or closed
checkbox does not satisfy G12 or G13. Reviewer booking is a human coordination
action that may proceed while implementation is underway; final review and
every dispositive retest must use the exact pinned release candidate.

## Decision

G13 is blocked before independent review. Do not claim that the deployed
design was reviewed, remediated, retested, or approved until the prerequisite
passes and the machine-readable record links the human-produced evidence. In
particular, do not:

- substitute review of an upstream protocol or cryptographic primitive for
  review of the complete Hush Line integration;
- assess an initial spike, mutable dependency, or different build and apply
  the conclusion to the final release candidate;
- omit archive, self-history, offline, retry, notification, export, backup,
  deletion, logging, or other alternate content copies from confidentiality
  review;
- describe classical authentication as post-quantum authentication, or omit
  the trustworthy served-JavaScript, password-guessing, browser-erasure,
  rollback, and compromise-recovery limits;
- publish exploit details, secrets, or real user data in a public artifact;
- accept author-only verification as independent remediation retest; or
- waive a finding that invalidates complete-copy PQ confidentiality or the
  unchanged everyday UX contract.

No production model, migration, route, protocol dependency, browser asset,
template, CSP, feature control, test runner, or public security claim changes
through this decision. Existing E2EE and conversation behavior remain
unchanged.

## Engagement and Review-Subject Contract

The engagement owner must record a named reviewer or review organization, an
independence and conflict attestation, a secure reporting channel, accepted
scope, final-assessment window, remediation retest window, and durable booking
evidence. Booking must not be recorded as a completed assessment.

Before substantive final assessment begins, the review subject must identify:

- implementation commit and release-candidate identifier;
- production bundle and container digests;
- lockfile and SBOM digests;
- protocol dependency name, source revision, artifact integrity, suite,
  serialization version, and wire version;
- database revision and exact feature configuration;
- browser/driver manifest; and
- the completed G12 validation report for that same subject.

Any material change to cryptographic dependencies, wire format, archive or
copy topology, device authorization, browser-state transitions, migration,
lifecycle behavior, CSP, build output, or security claims invalidates affected
review conclusions and retests. The record must identify the replacement
subject and affected evidence rather than silently carrying conclusions
forward.

## Mandatory Review Coverage

The independent reviewer must assess the complete Hush Line integration and
record evidence for all of these areas:

1. Protocol adapter correctness, official vectors, pinned independent peer,
   authenticated context, and repeated post-handshake PQ epochs.
2. Dependency source pins, integrity, licenses, advisories, SBOM,
   reproducibility, worker/bundle boundaries, and release artifact provenance.
3. Root, identity, device, session, chain, message, and archive key separation;
   wrapping; rotation; recovery; revocation; deletion; and compromise scope.
4. Device enrollment and authorization, membership, prekey publication and
   claim, replenishment, concurrent claim, stale devices, and churn bounds.
5. Cross-tab and worker serialization, durable outbox behavior, crashes,
   ambiguous retries, stale restores, transaction rollback, and atomic server
   commit/acknowledgement.
6. API authentication and authorization, cross-scope access, validation,
   replay and downgrade resistance, malformed inputs, resource limits, and
   every storage path.
7. CSP, server-served JavaScript trust, asset integrity and caching, worker
   scope, stale clients, and the consequences of an active-origin compromise.
8. Authenticated migration, monotonic version floor, mixed history, feature
   disable, stale-client refusal, deploy rollback, and roll-forward.
9. Password change and reset, offline guessing cost, session expiry, archive
   unlock and rotation, device/account deletion, and recovery limitations.
10. Transport, archive, sender self-history, recipient/device history, offline
    queue, retry/outbox, backups, notifications, export, deletion, diagnostics,
    and every other content-bearing copy.
11. Public and in-product guarantees, including classical-authentication,
    anonymity, metadata, retroactive protection, browser erasure, served-JS,
    and compromise-recovery boundaries.
12. Production feature controls, monitoring without secrets, incident
    response, disable/rollback floors, restore behavior, and operational
    compromise-recovery drills.

The review must include code/design analysis, pinned supply-chain review,
adversarial testing, fault and concurrency injection, complete-copy tracing,
real-browser review, migration/rollback drills, and security-wording review.
Test data must be synthetic. Detailed vulnerability reproducers stay in the
coordinated private-disclosure channel; the repository receives only a
public-safe status and durable restricted evidence reference.

## Finding, Remediation, and Retest Contract

Every finding requires a stable identifier, restricted tracking reference,
public-safe title, severity, security impact, affected guarantee and data
paths, exact affected revision/dependencies, reviewer-authored reproducer or
durable reproducer location, accountable remediation owner, remediation link,
regression evidence, author verification, and independent retest disposition.

Critical and high findings require remediation and a passing independent
retest. The same rule applies at any severity when a finding affects
confidentiality, a required content copy, authorization, downgrade resistance,
or the unchanged everyday UX contract. Retest must use the remediated pinned
build and attempt the original reproducer plus relevant variants; a unit test
added by the author is supporting evidence, not the independent retest.

A nonblocking residual finding may remain only when the reviewer and a
maintainer both record an explicit risk disposition, bounded scope, follow-up
owner, linked follow-up, and target date. No disposition can mark a finding
complete when it invalidates the epic's confidentiality, complete-copy, or UX
contract. Findings and dispositions remain empty in the record until supplied
by the responsible humans.

## Evidence Rerun and Security Wording

After each remediation, rerun every affected G12 result for the remediated
release candidate, including protocol/reference, adversarial authorization,
fault/concurrency, persisted-copy, real-browser, accessibility/performance,
CSP, migration/lifecycle/rollback, CI, CodeQL, workflow-security, and
dependency-audit evidence. A reviewer must identify the affected set; absence
of an impact assessment does not justify skipping a category.

Reconcile public and in-product security wording with the final reviewer
conclusions. The record must link the conclusion, affected documents, approved
changes, approver, and evidence. Wording cannot retain a broader guarantee
than the review supports or hide a material limitation behind a nonblocking
finding disposition.

## Human Release Gate

Production enablement remains a human decision. Approval requires all of the
following for the same pinned release candidate:

1. the independent final report or public-safe summary and exact reviewed
   revision/dependencies are linked;
2. all security-critical findings have remediation and passing independent
   retests;
3. every remaining nonblocking finding has the required maintainer and
   reviewer disposition and follow-up;
4. affected G12 evidence has been rerun and passes;
5. public security wording matches the reviewer conclusions; and
6. the designated human release owner records the decision, time, and durable
   evidence.

The implementation author or agent cannot book on another person's behalf,
fill reviewer findings or dispositions, attest independence, or approve the
release gate.

## Unblocking Sequence

1. Assign a human engagement owner, book the independent reviewer and retest
   window, confirm scope, and establish a secure reporting channel.
2. Complete and accept G12 on `codex/epic-2365`, including its transitive
   gates, for one exact release candidate and pinned dependency graph.
3. Fill the review-subject identity in `g13-independent-review.json`; provide
   the G12 evidence and only synthetic review data through the agreed channel.
4. Conduct the final assessment, record findings with owners and reproducers,
   and remediate blocking findings with regression tests.
5. Have the independent reviewer retest the remediated pinned build. Rerun all
   affected G12 evidence and reconcile security wording.
6. Record residual risk dispositions and the designated human release-gate
   decision. Do not enable production before the gate is approved.

## Consequences

- The repository has a concrete, versioned contract for reviewer booking,
  scope, finding ownership, remediation, independent retest, evidence reruns,
  residual risk, public wording, and the human release decision.
- No independent audit, finding closure, browser result, or approval is
  fabricated.
- Existing E2EE behavior, CSP, data paths, and everyday UX remain unchanged.
- G13 remains incomplete until G12 passes and human-produced review,
  remediation/retest, evidence, wording, and release-decision records exist.

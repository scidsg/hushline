# ADR-0002: Complete Protocol Design Readiness

Status: **Blocked before design**  
Date: 2026-09-24  
Decision gate: G3 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2368`

## Context

G3 must select and independently review the combined account-chat design:
protocol and library interfaces, authenticated envelope context, archive key
hierarchy and every retained copy, device identity and enrollment, prekeys,
transactional state, password-root wrapping, epochs, revocation, reset,
migration, failure behavior, and the exact limits of its security claims.

That work depends on two accepted inputs. G1 must provide an approved product
and security contract. G2 must provide a passing browser protocol and suite with
the required provenance, interoperability, continuous-PQ, browser, performance,
CSP, vulnerability, and ownership evidence. The machine-readable
[G3 readiness record](g3-readiness.json) pins the local evidence inspected for
both dependencies and inventories the deliverables that cannot yet be produced.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G1 / `scidsg/hushline#2366` | Human-approved product and security contract at an exact commit | Commit `37abae6e11dd9c0e8306f5e962ae97504f5c0888`; [review packet](README.md#g1-review-packet) | **Unsatisfied:** product-maintainer and security-architect dispositions remain pending |
| G2 / `scidsg/hushline#2367` | Passing, pinned browser protocol and reviewed suite | Commit `f84fb98e86286f3183f4c1f7e9f714549f10f9e2`; [ADR-0001](adr-0001-browser-protocol-candidate.md) and [evidence](g2-evidence.json) | **Unsatisfied:** the recorded decision is no-go and no suite is selected |

A closed issue, merged artifact, package claim, or automated review is not a
substitute for either required result.

## Decision

G3 is blocked before cryptographic design. Do not select or specify protocol
revisions, cipher suites, archive constructions, KDF parameters, envelope wire
formats, device/prekey semantics, recovery behavior, or migration behavior
against the unresolved inputs. Doing so would either assume decisions reserved
for G1 reviewers or build the combined system around a protocol candidate that
G2 explicitly rejected.

No complete integration specification, wire fixture, security approval, or
independent review is claimed by this ADR. Existing production chat behavior,
wire/storage formats, CSP, dependencies, and security claims remain unchanged.
Production-dependent tickets remain blocked.

## Deferred Deliverable Matrix

<!-- prettier-ignore -->
| Review area | Evidence required after prerequisites pass | Current disposition |
| --- | --- | --- |
| Protocol and library boundary | Exact dependency/source revisions, reviewed suite and combiner, stable interface/error contract, provenance and ownership | Blocked by G2 no-go |
| Authenticated envelope | Canonical bindings for message ID, conversation ID, account/device recipients, sender, purpose, key version, capability negotiation, exact transport bytes, and archive hashes | Blocked; no selected wire protocol |
| Archive and complete-copy inventory | Established hybrid wrapping construction, domain separation, key hierarchy, and sender/recipient/offline/history/backup copy analysis proving no recoverable classical-only duplicate | Blocked by G1 approval and G2 selection |
| Identity and devices | Account identity continuity, signed membership, enrollment/removal, freshness and rollback limits, and storage-tier recovery boundaries | Blocked by G1 approval and G2 selection |
| Prekeys and state | Generation, publication, atomic consumption, replay/exhaustion policy, replenishment, transaction boundaries, crash/retry ordering, and rollback behavior | Blocked; candidate semantics are unapproved |
| Password and archive lifecycle | Password-root KDF/wrapping costs, encrypted device storage, fresh-browser unlock, archive epochs, change/reset, revocation, and migration without recoverable old ratchet backups | Blocked by unresolved history/reset contract and protocol selection |
| Claim limits | Active-quantum authentication and deniability limits, browser erasure limits, and archive effects on forward secrecy and compromise recovery | Blocked pending combined-system analysis |
| Review evidence | Versioned specification, key/data-flow diagrams, wire fixtures, state-transition tables, failure matrix, and dispositions resolving all blocking findings | Not produced; human review cannot begin on an unspecified system |

## Unblocking and Review Sequence

1. Record the designated G1 human approvals, including dated evidence and the
   exact reviewed commit, and resolve every rejected or qualified row.
2. Replace the G2 no-go only with a passing ADR and evidence set satisfying its
   reconsideration gate, including a pinned suite and named ownership.
3. Update `g3-readiness.json` to reference those accepted commits. Draft the
   combined specification and non-secret fixtures only after both
   prerequisites are true.
4. Have a named cryptographic engineer review the construction and a separate
   human design reviewer record approval or blocking findings for the exact
   specification commit. Resolve blocking findings before G3 can be complete.

The author of a future specification cannot self-approve either review role.
Approval must remain pending until the reviewers provide dated, linked
evidence.

## Consequences

- No classical-only fallback, partial-copy design, or provisional algorithm is
  introduced to create apparent progress.
- No synthetic wire bytes or cryptographic vectors are fabricated without an
  approved implementation and reference peer.
- A future G3 artifact must review the combined system; updating primitive
  names or reviewing components independently is insufficient.
- This blocked disposition preserves the current G1 UX/security proposal and
  the G2 no-go rather than silently overriding either one.

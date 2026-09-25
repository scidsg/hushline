# ADR-0003: Server Storage and API Readiness

Status: **Blocked before implementation**  
Date: 2026-09-24  
Decision gate: G4 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2369`

## Context

G4 must add versioned server storage and APIs for one logical conversation
message with separately authorized device-transport and account-archive
copies. Its schema and request validation depend on G3's reviewed protocol,
authenticated-envelope bindings, account/device identity rules, archive
construction, transaction boundaries, and migration behavior.

The prerequisite artifact is available at commit
`9d7abd7a1ca83a64914cae6465e8ee4cf160132f`, but it records G3 as blocked
before design. The machine-readable [G4 readiness record](g4-readiness.json)
pins that evidence and inventories the implementation evidence that remains
blocked.

## Dependency Finding

<!-- prettier-ignore -->
| Gate | Required input | Local evidence | Finding |
| --- | --- | --- | --- |
| G3 / `scidsg/hushline#2368` | Accepted combined protocol design with reviewed schema, wire contract, lifecycle, and migration decisions | Commit `9d7abd7a1ca83a64914cae6465e8ee4cf160132f`; [ADR-0002](adr-0002-complete-protocol-design-readiness.md) and [readiness record](g3-readiness.json) | **Unsatisfied:** G3 is blocked by pending G1 approvals and the G2 no-go; every required design deliverable and both independent reviews remain pending |

A merged prerequisite artifact or issue sequence is not evidence that its
decision gate passed. G4 cannot derive a production schema from the issue's
field categories without deciding the protocol semantics reserved for G3.

## Decision

G4 is blocked before implementation. Do not add conversation columns, device
or archive-copy tables, migrations, lifecycle behavior, or message endpoints
until G3 supplies an accepted, exact contract. In particular, do not:

- label existing classical ciphertext or the current version-2 application
  envelope as post-quantum;
- choose opaque identifier sizes, uniqueness domains, copy cardinality, epoch
  semantics, envelope bounds, or idempotency scope without the reviewed wire
  and lifecycle contracts;
- accept a logical message unless every transport and archive copy required by
  that contract is authorized, context-bound, validated, and committed in one
  transaction; or
- create a rollback path that discards protected data or resumes classical
  writes after upgraded traffic exists.

No production model, migration, lifecycle, route, dependency, or security
claim is changed by this decision. Existing legacy reads, participant access,
rate limits, read state, notifications, retention, and deletion behavior remain
unchanged.

## Deferred Implementation Matrix

<!-- prettier-ignore -->
| Area | Evidence required after G3 passes | Current disposition |
| --- | --- | --- |
| Logical message and versioning | Reviewed protocol-version representation and monotonic conversation-version transaction semantics | Blocked; protocol and state transitions are unspecified |
| Device transport | Reviewed device/session identifier format, membership authorization, copy cardinality, uniqueness, and foreign keys | Blocked; device identity and enrollment are unspecified |
| Account archive | Reviewed epoch lifecycle, archive-copy inventory, wrapping context, uniqueness, and foreign keys | Blocked; archive construction and recovery are unspecified |
| Envelope and payload validation | Canonical full-context bindings, provenance verification, exact byte limits, version negotiation, and fail-closed errors | Blocked; authenticated envelope and suite are unspecified |
| Atomic and idempotent writes | Reviewed idempotency domain, retry result, advisory-lock ordering, all-required-copy rule, and concurrent transaction tests | Blocked; transaction boundaries are unspecified |
| Authorization and reads | Cross-account/device denial tests, participant-only reads, admin exclusion, and one-logical-message rendering across legacy and upgraded records | Blocked; identity and copy ownership are unspecified |
| Retention and deletion | Cascade/retention rules for transport copies, archive copies, epochs, devices, participants, conversations, and accounts | Blocked; lifecycle rules are unspecified |
| Expansion and rollback | Additive migration, synthetic legacy/upgraded/mixed fixtures, safe-reader deployment order, backfill rules, and classical-write refusal after upgraded traffic | Blocked; migration behavior is unspecified |

## Unblocking and Review Sequence

1. Complete G1 with exact-commit product-maintainer and security-architect
   approvals.
2. Replace the G2 no-go with a passing, pinned browser protocol and reviewed
   suite.
3. Complete G3's combined design, required evidence, cryptographic-engineer
   review, and independent design review at an exact commit.
4. Update `g4-readiness.json` to pin that accepted G3 commit and transcribe its
   exact schema, API, state, and migration contracts into implementation tests
   before changing production code.
5. Implement the additive expansion and dual readers first. Only enable
   upgraded writes after synthetic migration evidence and security review;
   retain safe readers during rollback and fail closed on classical writes once
   upgraded records exist.

The G4 implementation and migration evidence still require human security
review. No reviewer disposition may be inferred or filled by the author.

## Consequences

- Legacy ciphertext and current conversation behavior remain intact.
- No partial-copy, classical-only fallback, or misleading PQ label is added.
- The exact decisions needed to implement and test G4 are visible to reviewers
  without fabricating a schema from an unapproved protocol.
- G4 remains incomplete until production implementation and all acceptance
  evidence exist after G3 passes.

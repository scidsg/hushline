# ADR-0002: Complete PQ Account-Chat Protocol Design

Status: **Proposed for independent cryptographic review**<br>
Date: 2026-09-29<br>
Decision gate: G3 of `scidsg/hushline#2365`  
Issue: `scidsg/hushline#2398` (replaces delivery scope from
`scidsg/hushline#2368`)

## Context

The earlier revision stopped before design because G1 human acceptance and G2
execution evidence were pending. Maintainer direction now makes those release
gates rather than development blockers. This revision therefore supplies the
combined, implementable proposal and preserves every missing execution or
human-review result as an explicit release condition.

G1's unchanged-UX/security packet is the product baseline. G2 supplies the
pinned PQXDH/SPQR browser boundary at `0f6d5e9e211b0310290a12bdcb9e2cf797ea3ec2`.
Its prototype is still recorded as implemented but unexecuted, and the official
reference peer, physical-browser matrix, supply-chain review, named ownership,
and CSP disposition remain missing. This ADR does not turn those missing
results into passing evidence.

## Decision

Adopt the [version-1 proposed protocol](protocol-design.md) as the exact G3
implementation and independent-review subject:

- online delivery is pinned to the G2 Signal PQXDH revision 3, round-3
  Kyber1024, and SPQR v1 candidate without calling Kyber FIPS 203 ML-KEM;
- retained history is independently sealed for each participant archive epoch
  with the `MLKEM768-X25519` construction from the pinned concrete-hybrid-KEM
  and PQ-HPKE drafts, in HPKE base mode using HKDF-SHA-256 and AES-256-GCM;
- RFC 8785 JCS contexts bind message, conversation, sender, account/device
  recipients, purpose, key/version/epoch, membership freshness, capabilities,
  suite, exact transport bytes, and archive ciphertext hashes;
- account identity, signed device membership, paired classical/PQ one-time
  prekeys, password-root wrapping, encrypted device-local state, archive
  epochs, revocation, reset, and fresh-browser recovery have exact lifecycle
  and storage boundaries;
- send, receive, retry, prekey consumption, and copy publication have atomic
  transitions and fail closed; and
- migration is monotonic, legacy history is not relabelled, and rollback keeps
  the new reader while stopping writers.

The [wire fixtures](g3-wire-fixtures.json) pin canonical bytes, hashes, copy
order, idempotency input, and required mutation failures. Their ciphertext is
explicitly opaque synthetic framing data. It is not a fabricated hybrid-KEM,
Signal, HPKE, or signature known-answer vector.

## Archive choice

`MLKEM768-X25519` is selected because the pinned IETF drafts supply its
analyzed classical/PQ combiner, HPKE mapping, and test vectors instead of asking
Hush Line to invent them. HPKE seals a separate sender and recipient archive
copy. No classical duplicate, server escrow, root-derived archive keypair, old
ratchet snapshot, plaintext retry, or partial-copy commit is permitted.

The exact pinned draft revisions and combined application profile still require
cryptographic review. The drafts define HPKE KEM ID `0x647a`; it is fixed in the
suite derivation rather than accepted from wire data. The wire carries the
textual suite name and does not negotiate an algorithm identifier.

## Review and release disposition

The design and fixture deliverables are complete enough for implementation and
review, but G3 is not accepted. A named cryptographic engineer and a separate
independent design reviewer must review the same exact revision, record findings
in `g3-readiness.json`, and independently retest remediations. Blocking findings
must be resolved before production-dependent cryptographic implementation or a
release claim.

The following also remain release evidence, not inferred facts: passing G2
prototype/reference-peer results, actual supported-browser and storage results,
reviewed dependency provenance/SBOM/vulnerability evidence, named maintenance
ownership, approved CSP behavior, and G1 product/security acceptance.

## Consequences

- Downstream tickets now have concrete interfaces, algorithms, bytes,
  transitions, copy inventory, recovery rules, and failure behavior to
  implement and test.
- Production chat behavior, schema, dependencies, CSP, and claims remain
  unchanged by this specification PR.
- Classical authentication, browser erasure, archive compromise, ratchet
  forward-secrecy, and malicious-served-JavaScript limits remain explicit.
- Any algorithm, context field, copy rule, KDF cost, epoch rule, or migration
  change requires a new specification/fixture version and renewed review.

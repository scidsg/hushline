# Issue #411 Symmetric Crypto Modernization Feasibility

Date: 2026-05-25

## Executive Summary

Pull request #411 should not be retrofitted directly into the current Hush Line
codebase. The branch is too stale, edits historical migrations, changes
encrypted column storage types without a forward data migration, changes
application secret bootstrap behavior, and combines field encryption, secret
management, and password hashing into one high-risk change set.

Several ideas from #411 are still worth recreating, but only as a staged
modernization program:

- Versioned encrypted-field envelopes for crypto agility.
- Explicit domain separation for each encrypted field.
- Authenticated associated data that binds ciphertext to stable application
  context.
- Dual-read migration behavior so existing ciphertext remains readable until
  migration is proven complete.
- Tests that fail closed when ciphertext is decrypted under the wrong domain or
  context.

The work can benefit Hush Line if it is narrowed to database-only exposure risks
and implemented with a no-data-loss migration plan. It should not be treated as
a solution for full application compromise, because an attacker who can execute
code in the app can still reach configured keys and plaintext at use time.

## Source Material Reviewed

GitHub item #411 is a closed draft pull request, not an open issue. This study
treats it as the preserved implementation record for the original proposal.

- Closed draft PR #411,
  `[DRAFT] feat: begin modernization of symmetric crypto [#268][#289][#357]`.
- Linked issue #268, `Better encryption key management`.
- Linked issue #289, `Determine utility of encrypted DB fields`.
- Linked epic #357, `Future-Proofing - Sprint 1`.
- Current encrypted-field implementation in `hushline/crypto.py`.
- Current encrypted model fields in:
  - `hushline/model/user.py`
  - `hushline/model/notification_recipient.py`
  - `hushline/model/field_value.py`
- Current password hashing compatibility layer in `hushline/password_hasher.py`.
- Current app bootstrap in `hushline/__init__.py`.
- Current Alembic migration history under `migrations/versions/`.

## Current State

Hush Line currently encrypts selected database fields through
`hushline.crypto.encrypt_field()` and `hushline.crypto.decrypt_field()`. The
implementation uses Fernet with an environment-provided `ENCRYPTION_KEY`. The
helper intentionally calls `encrypt_at_time(..., current_time=0)` so Fernet
tokens do not reveal per-write timestamps.

Encrypted database values are currently stored as text-like ciphertext in
existing columns:

| Model                   | Fields                                                                              |
| ----------------------- | ----------------------------------------------------------------------------------- |
| `User`                  | TOTP secret, notification email, SMTP server, SMTP username, SMTP password, PGP key |
| `NotificationRecipient` | recipient email, recipient PGP key                                                  |
| `FieldValue`            | custom message field values                                                         |

The current helper already has optional `scope` and `salt` parameters for key
derivation, but the model properties reviewed do not currently pass
field-specific scope or row-specific salt values. In practice, encrypted DB
fields use the same Fernet key.

Password hashing is separate from field encryption. The current password hasher
supports the existing passlib scrypt scheme, optional Werkzeug scrypt, and
rehash-on-auth compatibility behavior. Any Argon2 migration should remain
separate from encrypted-field modernization.

## What #411 Attempted

The #411 branch introduced a broader crypto redesign:

- A `SecretsManager` using Argon2, `shake_256`, canonical packing, and
  ChaCha20-Poly1305.
- Field encryption helpers that accept explicit domains and authenticated
  associated data.
- A new infrastructure-admin secret model.
- Per-user secret material for associated data.
- Conversion of several encrypted fields from text columns to binary columns.
- Password hashing changes that derive password material through the new vault.
- Application startup changes that initialize a vault and derive Flask secret
  material.

Relative to its 2024 merge base, the branch changed 17 files with roughly 758
additions and 82 deletions. Relative to current `main`, the branch is massively
divergent, with hundreds of unrelated file differences caused by stale history.
Direct cherry-picking or merging would be high risk and low signal.

## Benefits Worth Preserving

### Domain Separation

Field encryption should not let ciphertext from one logical field decrypt
cleanly in another logical field. Explicit domains such as `user.totp_secret`,
`user.smtp_password`, and `notification_recipient.email` would reduce accidental
cross-context use and make cryptographic intent auditable.

### Authenticated Associated Data

Authenticated associated data can bind ciphertext to stable non-secret context,
such as an envelope version, table name, column name, and immutable row
identifier. This would help detect row or column swapping in a database-only
compromise.

The associated data design must avoid mutable values unless their historical
values are retained. If AAD includes a username, email address, or other mutable
profile data, ordinary user edits could make old ciphertext undecryptable.

### Versioned Envelopes

Hush Line needs a versioned ciphertext format before changing algorithms. A
versioned envelope lets old Fernet ciphertext coexist with future AEAD
ciphertext, and it gives operators a safe rollback window.

### Failure Tests

The current test suite should grow explicit coverage for:

- Legacy ciphertext remains decryptable.
- New ciphertext decrypts only with the expected domain.
- New ciphertext decrypts only with the expected associated data.
- Wrong domain, wrong AAD, wrong key, truncated ciphertext, and malformed
  envelopes fail closed.

## Risks In #411 As Written

### No Safe Forward Migration

#411 modified historical migration files and changed encrypted column types
instead of adding forward-only Alembic revisions. That is not safe for deployed
databases.

Any current work must preserve existing migrations and add new forward migrations
only. Existing production ciphertext must remain readable throughout deployment,
migration, rollback, and post-deploy verification.

### Text To Binary Storage Change

#411 changed several encrypted fields from text-like storage to raw bytes.
Current production data is Fernet text ciphertext. A direct type conversion
risks failed casts, truncated values, unreadable rows, or deployment-time locks.

If a future algorithm produces binary ciphertext, the first migration should
still consider ASCII armor such as base64 inside a versioned text envelope.
Binary column conversion can be a later, separately proven migration if it
provides enough benefit.

### Mixed Scope

#411 combines at least four separate migrations:

- Database field encryption format.
- Application secret management.
- Password hashing.
- Flask/session secret derivation.

Combining them increases rollback complexity and makes it harder to identify
which part caused a failure. Each should be split into its own design, PR, and
migration plan.

### Startup And Multi-Instance Risk

#411 introduced application startup behavior that creates infrastructure secret
records and changes how Flask secret material is derived. Startup-time writes are
risky in multi-instance deployments and can race during deploys.

Current Hush Line uses Flask-Migrate. Future work should not add
`db.create_all()` or implicit schema mutation during app startup.

### Password Hash Migration Risk

#411 moves password hashing toward Argon2 and vault-derived prehashing. That may
be worth evaluating, but it conflicts with the current compatibility layer in
`hushline/password_hasher.py`.

Password hash modernization should remain separate because authentication
lockout is a service-disruption risk. It needs legacy verification,
rehash-on-login, metrics, rollback behavior, and tests for existing hashes.

### Python Memory Clearing Limits

#411 attempts to clear bytearrays after use. That is directionally good for
handling mutable secret buffers, but Python cannot guarantee that all secret
copies are wiped because strings, framework internals, cryptography bindings,
garbage collection, logging, and exception paths can retain copies.

Memory clearing should be treated as best-effort hardening, not as a primary
security guarantee.

### Threat Model Ambiguity

Encrypted database fields protect against some database-only exposure scenarios,
including leaked snapshots, direct DB reads, and accidental disclosure of raw
database contents. They do not protect against a compromised application server
that can call decryption code with configured keys.

The modernization should therefore be justified in terms of database-only
compromise and operational exposure, not as a complete mitigation for remote code
execution or malicious app administrators.

## Feasibility Assessment

### Direct Retrofit

Direct retrofit is not feasible. The old branch is stale against current `main`,
contains unsafe migration patterns, and combines too many security-sensitive
changes.

Decision: do not merge, rebase, or cherry-pick #411 as a whole.

### Selective Recreation

Selective recreation is feasible and beneficial if the work is phased and
migration-first.

Decision: recreate the best ideas from #411 in small PRs after a threat model
and migration design are accepted.

### Net Product Benefit

The net benefit is positive for Hush Line if the scope is limited to:

- Protecting encrypted fields from database-only exposure.
- Improving cryptographic context binding.
- Creating future algorithm agility.
- Preserving service availability and existing data.

The net benefit becomes negative if the work attempts a one-shot replacement of
field encryption, password hashing, infrastructure secret management, and
session secret derivation.

## Recommended Plan

### Phase 0: Threat Model And ADR

Write an architecture decision record that defines:

- Which attacker capabilities are in scope.
- Which encrypted fields are protected.
- Which fields are only protected against database-only compromise.
- Which attacks remain out of scope.
- Operator recovery expectations if `ENCRYPTION_KEY` or future key material is
  lost.

Status: completed in
[`ENCRYPTED-FIELD-MODERNIZATION-ADR.md`](ENCRYPTED-FIELD-MODERNIZATION-ADR.md).

### Phase 1: Inventory And Tests

Add tests that inventory every encrypted field and lock current behavior before
changing code. The inventory should include `User`, `NotificationRecipient`, and
`FieldValue`.

The tests should prove that current Fernet ciphertext can still be decrypted by
the new compatibility layer.

### Phase 2: Versioned Envelope Interface

Introduce a versioned encrypted-field interface without changing storage columns
or default write behavior.

Requirements:

- Legacy unprefixed Fernet tokens remain readable.
- New code can identify envelope versions.
- Malformed versions fail closed.
- No schema migration is required in this phase.

### Phase 3: Domain And AAD Design

Define stable domains and AAD for each encrypted field.

Requirements:

- Domains are stable strings owned by the codebase.
- AAD uses immutable or permanently retained values.
- AAD never depends on mutable usernames, emails, profile display names, or
  message text.
- Tests prove field swapping fails for new envelopes.

### Phase 4: Dual-Read, Single-Write Rollout

Deploy a reader that supports old and new formats before writing new ciphertext.

Then enable new writes behind a feature flag or explicit config setting:

- Read legacy Fernet.
- Read new envelope.
- Write only one configured format.
- Keep the legacy reader deployed until migration verification and rollback
  windows are complete.

### Phase 5: Data Migration Runbook

Only after phases 0 through 4 should Hush Line migrate existing rows.
The operator runbook is drafted in
[`ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md`](ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md).
Production enablement is blocked until maintainers review a completed
[`ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md`](ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md)
artifact for restored-backup or staging validation and the
[`ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md`](ENCRYPTED-FIELD-MIGRATION-RUNBOOK.md)
production release gate reports ready.

Migration requirements:

- Forward-only Alembic revisions.
- No edits to historical migrations.
- Preflight row counts and decryptability checks.
- Dry-run mode.
- Small batch processing.
- Idempotent resume behavior.
- Per-row verification after re-encryption.
- Backup and restore rehearsal before production.
- Reviewed rehearsal evidence covering restore, preflight, dry-run, live batch,
  interruption/resume, rollback, and operator signoff.
- A passing `flask encrypted-field release-gate` result before production
  write-format configuration changes.
- Observable migration progress.
- Clear rollback plan that preserves the old reader.

### Phase 6: AEAD Evaluation And Production Write Path

After the envelope and migration path are proven, evaluate whether to switch new
writes from Fernet to an AEAD such as ChaCha20-Poly1305 or AES-GCM. Before an
existing production ciphertext migration can be called domain-bound or
best-in-class, implement and approve the production AEAD write path.

Status: AEAD evaluation completed in
[`ENCRYPTED-FIELD-AEAD-EVALUATION.md`](ENCRYPTED-FIELD-AEAD-EVALUATION.md);
the production AEAD write path remains future implementation work.

The 2026-05-26 maintainer decision makes production AEAD writes required before
existing production ciphertext migration can be considered complete in the
domain-bound or best-in-class sense. `envelope-fernet` remains a transitional
compatibility format and must not satisfy any epic Definition of Done item that
requires production AAD guarantees.

The evaluation should include:

- Dependency surface.
- Maintenance status.
- Ciphertext size.
- FIPS or deployment constraints if relevant.
- Nonce generation and misuse resistance.
- Operational key rotation.
- Test vectors and interoperability.

### Phase 7: Separate Password Hashing Work

If Argon2 remains desirable, open a separate password hashing issue and PR
series. It should build on `hushline/password_hasher.py` instead of replacing it
as part of field encryption.

Status: completed in
[`PASSWORD-HASH-MODERNIZATION-EVALUATION.md`](PASSWORD-HASH-MODERNIZATION-EVALUATION.md).

### Phase 8: Separate Operational Key Management Work

Operational key management should remain separate from encrypted-field envelope
modernization because it affects deployment, recovery, operator workflows, and
multi-instance startup behavior.

Status: completed in
[`OPERATIONAL-KEY-MANAGEMENT-DESIGN.md`](OPERATIONAL-KEY-MANAGEMENT-DESIGN.md).

## Migration Safety Requirements

Any implementation that touches encrypted production data must satisfy these
requirements before merge:

- Existing production ciphertext remains readable before, during, and after
  deployment.
- The old decrypt path remains available until migration completion is verified.
- No migration rewrites historical Alembic files.
- No migration drops or overwrites encrypted source values until replacement
  values are verified.
- No startup path mutates schema or creates required secret rows implicitly.
- No deploy changes Flask `SECRET_KEY`, `SESSION_FERNET_KEY`, or password hash
  behavior as part of field-encryption migration.
- No maintenance window is assumed unless explicitly approved.
- Rollback is documented and tested.

## Suggested Follow-Up Issues

1. Completed: write the encrypted-field threat model and ADR.
2. Add an encrypted-field inventory test suite.
3. Introduce a versioned encryption envelope that preserves legacy Fernet reads.
4. Design stable domains and AAD for each encrypted field.
5. Add dual-read, single-write support behind configuration.
6. Write and test a resumable encrypted-field migration runbook.
7. Evaluate AEAD algorithms for future new writes.
8. Evaluate password hash modernization separately.
9. Completed: evaluate operational key management separately.
10. Implement production domain-bound AEAD writes before claiming
    best-in-class migration completion for existing encrypted-field
    ciphertext.

## Recommendation

Do not revive #411 as an implementation branch.

Open a new epic for symmetric crypto modernization and recreate the useful parts
incrementally. The first implementation PR should be compatibility-only: a
versioned envelope reader that can read existing Fernet ciphertext and has tests
for future domain and AAD behavior, without changing database schema or write
format.

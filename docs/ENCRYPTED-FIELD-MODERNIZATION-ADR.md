# ADR: Encrypted Field Modernization Threat Model

Date: 2026-05-25

Status: Proposed

## Context

Hush Line currently encrypts selected database fields with
`hushline.crypto.encrypt_field()` and decrypts them with
`hushline.crypto.decrypt_field()`. The current implementation uses Fernet with
the environment-provided `ENCRYPTION_KEY`.

Issue #411 explored a broader symmetric crypto redesign. The follow-up
feasibility study concluded that selected ideas are worth recreating, but not by
retrofitting #411 directly. Before implementation, Hush Line needs a clear
threat model for what encrypted database fields are intended to protect.

This ADR covers server-side encrypted database fields only. It does not change
runtime encryption behavior, migrations, models, password hashing, sessions,
client-side OpenPGP encryption, or operator secret management.

## Decision

Hush Line will treat encrypted-field modernization as protection against
database-only exposure, not as a mitigation for full application-server
compromise.

Future encrypted-field work must preserve existing ciphertext readability,
separate database-field encryption from password hashing and session secret
management, and explicitly document any new key material before it is introduced.

## Protected Field Inventory

The following fields are in scope for encrypted-field modernization because they
are currently passed through `encrypt_field()` and `decrypt_field()`:

| Model                   | Database column                   | Application property | Intended protected data                   |
| ----------------------- | --------------------------------- | -------------------- | ----------------------------------------- |
| `User`                  | `users.totp_secret`               | `totp_secret`        | TOTP shared secret for 2FA                |
| `User`                  | `users.email`                     | `email`              | Legacy or synchronized notification email |
| `User`                  | `users.smtp_server`               | `smtp_server`        | Custom SMTP hostname                      |
| `User`                  | `users.smtp_username`             | `smtp_username`      | Custom SMTP username                      |
| `User`                  | `users.smtp_password`             | `smtp_password`      | Custom SMTP password                      |
| `User`                  | `users.pgp_key`                   | `pgp_key`            | Recipient public PGP key material         |
| `NotificationRecipient` | `notification_recipients.email`   | `email`              | Notification recipient email address      |
| `NotificationRecipient` | `notification_recipients.pgp_key` | `pgp_key`            | Notification recipient public PGP key     |
| `FieldValue`            | `field_values._value`             | `value`              | Custom field values or PGP ciphertext     |

`FieldValue.value` needs special handling in future designs. For custom fields
marked encrypted, Hush Line may store recipient PGP ciphertext inside the
database-field encryption wrapper. For custom fields not marked encrypted, Hush
Line stores submitted values inside the database-field encryption wrapper only.
In both cases, access to the wrapper depends on server-side encrypted-field key
material.

## Stable Domain And AAD Contract

Future encrypted-field envelopes must authenticate a code-owned domain string
and canonical associated data (AAD). This contract is defined in
`hushline.crypto.ENCRYPTED_FIELD_CONTRACTS` and is intentionally keyed to stable
database concepts rather than SQLAlchemy model names, route names, form labels,
profile text, or user-entered values.

| Contract ID                     | Stable domain                                              | AAD row values                                        |
| ------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------- |
| `User.totp_secret`              | `hushline.encrypted-field.users.totp_secret`               | `user_id`                                             |
| `User.email`                    | `hushline.encrypted-field.users.email`                     | `user_id`                                             |
| `User.smtp_server`              | `hushline.encrypted-field.users.smtp_server`               | `user_id`                                             |
| `User.smtp_username`            | `hushline.encrypted-field.users.smtp_username`             | `user_id`                                             |
| `User.smtp_password`            | `hushline.encrypted-field.users.smtp_password`             | `user_id`                                             |
| `User.pgp_key`                  | `hushline.encrypted-field.users.pgp_key`                   | `user_id`                                             |
| `NotificationRecipient.email`   | `hushline.encrypted-field.notification_recipients.email`   | `notification_recipient_id`, `user_id`                |
| `NotificationRecipient.pgp_key` | `hushline.encrypted-field.notification_recipients.pgp_key` | `notification_recipient_id`, `user_id`                |
| `FieldValue.value`              | `hushline.encrypted-field.field_values._value`             | `field_definition_id`, `field_value_id`, `message_id` |

Canonical AAD bytes include the envelope algorithm, envelope version, AAD
schema identifier, stable domain, table, column, and the row values listed
above. Row values must be immutable database identifiers that are retained with
the ciphertext for as long as that ciphertext must remain decryptable.

AAD must not require mutable usernames, email addresses, display names, bio or
profile text, custom field text, message text, SMTP settings, PGP key text, or
other user-editable values unless a future migration permanently retains the
historical value that was authenticated when the ciphertext was written. The
current contract rejects those mutable context names when building AAD.

Domain strings remain stable across model refactors. If a SQLAlchemy property,
Python class, route, template, or form changes while the underlying encrypted
data remains the same logical field, the existing domain and AAD schema must be
preserved. If a database migration splits, merges, or replaces an encrypted
field, the migration plan must either retain the old domain for migrated
ciphertext or introduce a new explicit domain with dual-read compatibility,
rollback guidance, and decryptability tests for both formats.

The Phase 3 prototype envelope uses AES-256-GCM with AAD to demonstrate
wrong-domain and wrong-AAD failures. It is not wired into production model
writes. Production writes default to the legacy Fernet path, with the
versioned Fernet envelope available through the rollout control below.

## Production Write-Format Decision

Maintainers recorded this decision on 2026-05-26:

- `envelope-fernet` is a transitional compatibility format only.
- `envelope-fernet` must not be documented or represented as domain-bound
  authenticated field encryption.
- Existing production encrypted-field values must not be rewritten until the
  migration helper, dry-run/live workflow, rollback tests, staging or
  restored-backup rehearsal evidence, release gates, and this write-format
  decision documentation are complete.
- Domain-bound AEAD is required before any best-in-class migration of existing
  production ciphertext is considered complete.

`envelope-fernet` keeps the existing Fernet confidentiality and authentication
properties for the wrapped token and adds explicit format versioning for
dual-read rollout, schema-fit checks, and rollback planning. It does not
cryptographically bind ciphertext to the encrypted-field contract, stable
domain, table, column, or immutable row identifiers listed above. Copying an
`envelope-fernet` value between fields, rows, or deployments therefore is not
expected to fail closed because of AAD mismatch.

Before production AEAD writes exist, maintainers may approve compatibility-only
work such as the dual reader, widened storage, preflight checks, rehearsal
evidence, and transitional `envelope-fernet` writes for newly updated values.
They may also approve a compatibility rewrite of existing ciphertext only after
the migration helper and release gates above are complete, but that rewrite must
remain labeled transitional and must not close the domain-bound encryption goal.

The following remain blocked until a domain-bound AEAD write path is implemented
and separately approved for production: claims of production AAD guarantees,
removal of ambiguity in favor of "domain-bound" completion language for
existing ciphertext, and any best-in-class migration completion claim for
existing encrypted-field values.

## Dual-Read, Single-Write Rollout Controls

`ENCRYPTED_FIELD_WRITE_FORMAT` controls the format used for newly written
encrypted database fields. Supported values are:

- `legacy-fernet`: write the existing unprefixed Fernet token format. This is
  the default.
- `envelope-fernet`: write the transitional `hlfield:` versioned envelope that
  wraps one Fernet ciphertext without domain-bound AAD.

Readers support both formats before operators enable envelope writes. Legacy
Fernet decrypt support remains enabled while envelope writes are tested,
migration planning is completed, and rollback windows remain open.

Operator rollout sequence:

1. Deploy code with the dual reader while leaving
   `ENCRYPTED_FIELD_WRITE_FORMAT` unset or set to `legacy-fernet`.
2. Deploy migration `b2039e7c0a1d` to widen encrypted short-string columns
   before any envelope write is allowed.
3. Run the schema and ciphertext preflight and confirm it reports readiness.
4. Set `ENCRYPTED_FIELD_WRITE_FORMAT=envelope-fernet` for transitional new
   writes only after the widening migration, migration tests, ciphertext fit
   tests, and preflight verification have all passed.
5. Verify newly updated settings, notification recipients, and encrypted custom
   field values read back successfully.
6. Leave legacy Fernet read support deployed until a later migration issue
   verifies all existing rows and documents rollback completion.

Envelope writes are release-blocked until the schema widening migration has
completed. The application guard must fail closed when `envelope-fernet` is
configured against legacy `VARCHAR(255)` encrypted columns. Downgrades from the
widening migration must refuse to narrow columns when any stored envelope
ciphertext exceeds the legacy limit, because truncating ciphertext would make
protected data unrecoverable.

Fields outside this inventory are not protected by encrypted-field
modernization. Examples include account IDs, usernames, directory/profile
visibility, message status, timestamps, field labels, notification preferences,
SMTP port/encryption mode/sender, billing identifiers, and other relational or
operational metadata unless future ADRs explicitly add them.

Sensitive fields found during the Phase 1 inventory that are intentionally not
encrypted by the current database-field wrapper and should remain visible for
maintainer review:

- `User.password_hash`: password verifier is hashed, not encrypted.
- `User.smtp_port`, `User.smtp_encryption`, and `User.smtp_sender`: custom SMTP
  metadata remains plaintext.
- `User` Stripe billing identifiers and subscription metadata: billing
  integration identifiers remain plaintext.
- `User.account_category`, `User.country`, `User.city`, and `User.subdivision`:
  profile and directory classification data remains plaintext.
- `Username` username, display name, bio, and extra profile fields: public,
  profile, and alias metadata remains plaintext.
- `Username.embed_allowed_origins`: embed configuration metadata remains
  plaintext.
- `FieldDefinition` labels, field type, requirements, choices, and sort order:
  custom form definitions remain plaintext.
- `Message` status, timestamps, reply slug, and username link: message metadata
  remains plaintext.

## In-Scope Attacker Capabilities

Encrypted-field modernization is intended to reduce harm when an attacker can
inspect database contents but cannot execute application code or read configured
application secrets.

In-scope scenarios include:

- Read-only exposure of Postgres tables, snapshots, backups, exports, logs, or
  support bundles that include encrypted columns.
- Accidental disclosure of raw database contents without `ENCRYPTION_KEY`.
- A database operator or database-only credential with direct SQL read access
  but no access to application environment variables, secret stores, app
  memory, deploy artifacts, or running containers.
- Database row or column tampering that future authenticated associated data can
  detect for new ciphertext formats.
- Ciphertext copied between encrypted fields, rows, or deployments where future
  domain separation and associated data can make misuse fail closed.

## Out-of-Scope Attacker Capabilities

Encrypted database fields do not protect plaintext when the attacker can use the
application as a decryption oracle or access the key material used by the
application.

Out-of-scope scenarios include:

- Remote code execution, template execution, malicious dependency execution, or
  any compromise that lets an attacker run code in the Hush Line application.
- Theft of `ENCRYPTION_KEY`, future encrypted-field key material, process
  memory, container environment variables, deploy secrets, or application
  configuration.
- A malicious or fully compromised application administrator, operator, CI/CD
  pipeline, build system, or release artifact.
- Client-side OpenPGP bypass caused by malicious JavaScript, compromised static
  assets, or compromised build and deployment paths.
- Authenticated recipient account compromise where the attacker can use normal
  application views to access messages or settings.
- Traffic analysis, endpoint compromise, subpoena or coercion of operators, and
  other operational-security threats outside server-side field encryption.

## Database-Only Exposure Versus Application Compromise

Database-only exposure means the attacker has database data but not the
application runtime, not application secrets, and not code execution. In that
case, encrypted fields should keep their plaintext unavailable, and future
envelope work should improve field/domain binding and migration safety.

Application-server compromise means the attacker can run or influence Hush Line
application code, inspect environment variables, read configured secrets, or call
the same decryption helpers the application uses. In that case, server-side
encrypted fields no longer provide a confidentiality boundary for data the
application can decrypt at use time.

Modernization should therefore be justified as defense in depth against
database-only and backup-only exposure. It must not be described as a complete
solution for app compromise, malicious operators, or broken client-side E2EE.

## Operator Recovery Expectations

Operators must treat `ENCRYPTION_KEY` and any future encrypted-field key
material as required recovery material for existing encrypted database fields.

If `ENCRYPTION_KEY` is lost and no valid backup exists:

- Existing encrypted database-field plaintext should be considered
  unrecoverable through Hush Line.
- Operators must not expect Hush Line to derive, bypass, or escrow the missing
  key.
- Restoring a database backup without the matching encrypted-field key material
  should not be considered a complete disaster recovery path.
- User-managed secrets and settings may need to be reset or re-entered,
  including TOTP setup, notification email addresses, custom SMTP settings, and
  PGP keys.
- Stored custom field values wrapped only by database-field encryption may be
  permanently unreadable.
- Stored custom field values containing recipient PGP ciphertext may still be
  inaccessible to the application if the outer database-field encryption wrapper
  cannot be decrypted.

Future key rotation or envelope work must document how old key material remains
available until all ciphertext written under it is migrated or intentionally
retired. A migration plan must include backup, restore, rollback, and
decryptability verification steps before production rollout.

## Why #411 Should Not Be Retrofitted Directly

#411 should not be merged, rebased, cherry-picked, or manually recreated as one
large change set because it combines multiple security-sensitive migrations:

- Encrypted-field format changes.
- Secret-management changes.
- Password-hashing changes.
- Flask/session secret derivation changes.
- Startup behavior that risks implicit schema or secret mutation.
- Historical migration edits and encrypted column type changes without a safe
  forward migration plan.

Those changes have different threat models, rollback requirements, and user
impact. Retrofitting them together would increase the risk of unreadable data,
authentication lockout, session invalidation, and deployment failure.

The appropriate path is phased recreation: first document this threat model,
then add inventory and compatibility tests, then introduce versioned envelopes,
domain separation, associated data, and migration tooling in separate reviewed
changes.

## Consequences

- Future encrypted-field implementation PRs must state whether they address
  database-only exposure, migration safety, domain separation, associated data,
  key rotation, or another explicitly documented concern.
- Password hashing remains separate from encrypted-field modernization.
- Session and Flask secret derivation remain separate from encrypted-field
  modernization.
- Any future encrypted-field migration must preserve legacy Fernet reads until
  migration completion and rollback windows are verified.
- Any new key material must have documented backup, restore, rotation, and loss
  behavior before it is used for production data.
- Epic #2013 is not complete in the domain-bound encryption sense while
  production writes use only `legacy-fernet` or transitional `envelope-fernet`.
  The epic Definition of Done must keep compatibility milestones separate from
  production AAD guarantees and require production AEAD before existing
  ciphertext migration is called best-in-class or domain-bound.

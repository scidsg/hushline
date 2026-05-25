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
| `FieldValue`            | `field_values.value`              | `value`              | Custom field values or PGP ciphertext     |

`FieldValue.value` needs special handling in future designs. For custom fields
marked encrypted, Hush Line may store recipient PGP ciphertext inside the
database-field encryption wrapper. For custom fields not marked encrypted, Hush
Line stores submitted values inside the database-field encryption wrapper only.
In both cases, access to the wrapper depends on server-side encrypted-field key
material.

Fields outside this inventory are not protected by encrypted-field
modernization. Examples include account IDs, usernames, directory/profile
visibility, message status, timestamps, field labels, notification preferences,
SMTP port/encryption mode/sender, billing identifiers, and other relational or
operational metadata unless future ADRs explicitly add them.

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

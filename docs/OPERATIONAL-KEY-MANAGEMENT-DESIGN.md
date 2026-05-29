# Operational Key Management Design

Date: 2026-05-26

Status: Recommendation to keep environment-managed encrypted-field key rotation

## Scope

This memo separates operational key management from encrypted-field envelope
modernization. It documents current expectations for `ENCRYPTION_KEY`,
`SESSION_FERNET_KEY`, and the Flask `SECRET_KEY`; recovery requirements for
lost or rotated key material; deployment constraints for multi-instance
operation; and whether Hush Line should introduce a separate external key
service or sealed local secret store now.

It does not change encrypted-field write format, Flask session secret
derivation, migrations, models, password hashing, client-side OpenPGP behavior,
or application startup behavior.

## Current Secret Expectations

Hush Line currently expects operators to provide stable secret material outside
the database. Application boot reads configured environment values and does not
create secret records in the database.

`ENCRYPTION_KEY`:

- Current source: environment variable read directly by `hushline.crypto`.
- Current use: Fernet key for server-side encrypted database fields. AES-GCM
  encrypted-field helpers also derive from it.
- Operational expectation: active write key for encrypted database fields; same
  value on every app instance that writes encrypted fields; backed up with
  disaster-recovery material; not generated at app boot.

`ENCRYPTION_KEY_FALLBACKS`:

- Current source: optional comma-separated environment variable read directly by
  `hushline.crypto`.
- Current use: ordered read-only fallback keys for server-side encrypted
  database fields. Hush Line tries `ENCRYPTION_KEY` first, then each fallback in
  order. New encrypted-field writes always use `ENCRYPTION_KEY`.
- Operational expectation: only old encrypted-field keys still needed to read
  existing ciphertext belong here. Fallback entries must be valid Fernet keys,
  must not be empty, and must be present on every app instance until the data
  written under those keys is migrated or intentionally retired.

`SESSION_FERNET_KEY`:

- Current source: environment variable loaded into app config.
- Current use: Fernet key for encrypted browser session cookies through
  `EncryptedSessionInterface`.
- Operational expectation: same value on every web instance. Rotation
  invalidates active sessions unless a future multi-key reader is designed.

Flask `SECRET_KEY`:

- Current source: environment variable loaded into app config.
- Current use: Flask application secret expectation. Current password-reset and
  embed rate-limit HMAC helpers prefer it before falling back to session or
  encryption secrets.
- Operational expectation: stable across instances. Rotating changes HMAC
  buckets and may invalidate active token workflows depending on the code path.

`ENCRYPTION_KEY` is required recovery material for protected database fields.
`SESSION_FERNET_KEY` and `SECRET_KEY` are operational web secrets, not
encrypted-field keys. They must not be bundled into encrypted-field envelope
work or silently derived from encrypted-field key material.

## Recovery Requirements

Operators need recoverability for both data and the key material that makes that
data usable. A database backup without the matching encrypted-field key material
is not a complete recovery artifact.

If `ENCRYPTION_KEY` is lost and no valid copy exists:

- Existing encrypted database-field plaintext should be considered
  unrecoverable through Hush Line.
- Hush Line must not derive, bypass, or escrow a replacement key.
- Operators may need users to re-enter affected secrets and settings, including
  TOTP setup, notification email addresses, custom SMTP settings, PGP keys, and
  encrypted custom field values.
- Restoring a database backup without the matching `ENCRYPTION_KEY` should be
  treated as an incomplete restore.

If `SESSION_FERNET_KEY` is lost or intentionally rotated:

- Active browser sessions should be expected to become unreadable and users
  should sign in again.
- The database does not need encrypted-field migration solely because the
  session key changed.
- A future graceful session-key rotation would need an explicit multi-key cookie
  reader and a retirement window; it should not be inferred at startup.

If Flask `SECRET_KEY` is lost or intentionally rotated:

- HMAC-based password reset attempt identifiers and embed rate-limit buckets may
  stop matching earlier values.
- Operators should expect any workflows depending on the prior HMAC key to
  expire or restart according to their normal TTLs.
- Changing `SECRET_KEY` must not change `ENCRYPTION_KEY` or
  `SESSION_FERNET_KEY`.

If `ENCRYPTION_KEY` is rotated while old protected database-field ciphertext
remains in service, operators must keep the previous encrypted-field key in
`ENCRYPTION_KEY_FALLBACKS` on every app instance. Current Hush Line
encrypted-field storage does not include key identifiers; missing key
identifiers are handled by ordered trial decryption. If none of the configured
keys decrypts a value, the read fails closed. If the fallback list is malformed,
encrypted-field reads and writes fail rather than silently ignoring the bad
configuration.

## Options Evaluated

### Current Environment-Based Secrets

Environment-provided secrets fit the currently supported deployment shapes:
local development, personal-server style compose deployments, staging, and
managed app instances that inject secrets through their platform. This model is
simple, already implemented, compatible with multi-instance deployments when
operators inject the same values everywhere, and avoids adding a new startup
dependency.

The main weakness is operational: backup, restore, access control, and rotation
discipline live outside the application. That weakness should be addressed with
operator documentation and deployment procedures before changing runtime key
loading.

### External Key Service

An external key service could provide centralized access control, audit logs,
versioned key material, and managed rotation for larger deployments. It also
adds a network dependency, IAM policy design, local development complexity,
startup failure modes, and product decisions about supported providers.

This does not fit the next encrypted-field envelope step because Hush Line would
need provider abstraction, outage behavior, local fallback rules, recovery
drills, and multi-instance rollout tests before production use. It is a future
managed-deployment design, not a prerequisite for encrypted-field envelopes.

### Sealed Local Secret

A sealed local secret, such as an operator-provisioned encrypted file or
platform-unsealed credential, could make personal-server backups easier to
reason about than ad hoc shell environment variables. It still needs installer
support, backup guidance, permissions checks, restore rehearsal, and a clear
answer for how multiple app instances receive the same unsealed value.

This is plausible future work for single-host personal deployments, but it
should not be introduced as an implicit app boot side effect.

## Multi-Instance Startup And Deploy Constraints

Multi-instance deployments require the same active key material on every app
instance that serves the same database and browser cookie domain.

Required constraints:

- All instances must use the same `ENCRYPTION_KEY` before reading or writing
  encrypted database fields.
- During encrypted-field key rotation, all instances must use the same active
  `ENCRYPTION_KEY` and the same ordered `ENCRYPTION_KEY_FALLBACKS` before
  reading or writing encrypted database fields.
- All web instances should use the same `SESSION_FERNET_KEY` before serving
  authenticated sessions.
- Flask `SECRET_KEY` should be consistent across instances that share reset,
  embed, and rate-limit workflows.
- Rolling deploys must not mix encrypted-field write keys or fallback-key order
  across instances.
- Session-key rotation may intentionally log users out, but it should be a
  planned operator action rather than an accidental per-instance mismatch.
- Schema migrations and data migrations must run as explicit deploy steps, not
  as application factory side effects.
- App boot must not create secret rows, mutate schema, generate replacement
  production secrets, or opportunistically rewrite encrypted fields.

Startup-time schema mutation or implicit secret-row creation is explicitly
rejected. It can race across instances, surprise operators during deploys,
break rollback expectations, and make disaster recovery depend on hidden app
side effects.

## ENCRYPTION_KEY Rotation Procedure

Hush Line uses ordered multi-key readers rather than key identifiers for
encrypted database fields. This applies only to server-side encrypted-field
storage. It does not affect recipient PGP keys, client-side E2EE payloads,
browser session secrets, Flask `SECRET_KEY`, password hashes, or application
tokens.

Rotation procedure:

1. Generate and back up a new Fernet key outside Hush Line.
2. Deploy every app instance with the new value in `ENCRYPTION_KEY` and the
   immediately previous encrypted-field key in `ENCRYPTION_KEY_FALLBACKS`.
   Include older fallback keys only while ciphertext written under those keys
   still exists.
3. Confirm normal encrypted-field reads and settings updates work before
   retiring any old key material.
4. Use the encrypted-field migration helper, with maintainer-approved release
   evidence, to rewrite existing rows under the active key when the operation is
   ready.
5. Remove retired fallback keys only after migration evidence proves no
   remaining encrypted-field rows require them and a rollback window has closed.

Rollback behavior:

- If a deployment must roll back before existing rows are rewritten, restore the
  previous `ENCRYPTION_KEY` and place the briefly active new key in
  `ENCRYPTION_KEY_FALLBACKS` so any new ciphertext written during the attempted
  rotation remains readable.
- If fallback keys are removed too early, rows written under retired keys become
  unreadable until the matching key is restored.
- If key material is lost, Hush Line cannot recover the affected plaintext.

Operational risks:

- More fallback keys increase the amount of key material that must be protected,
  backed up, and removed after retirement.
- Trial decryption is intentionally silent about which key succeeded and must
  not log key material, plaintext field values, or raw encrypted-field
  contents.
- Malformed fallback configuration blocks encrypted-field operations and should
  be treated as a deploy failure.
- This mechanism is for encrypted database fields only; it must not be used to
  rotate recipient PGP keys or session secrets.

## Decision Record

Keep the environment-based operational key model and add explicit read-only
encrypted-field fallback keys for graceful `ENCRYPTION_KEY` rotation.

Proceed with encrypted-field envelope modernization only within
operator-provided encrypted-field key material. Defer external key service and
sealed local secret implementation until maintainers approve a separate
operational key-management project with provider choices, recovery drills,
rotation semantics, and multi-instance rollout tests.

Future work may revisit key management when Hush Line needs managed-provider
audit controls, key identifiers, personal-server sealed secret tooling, or
automated encrypted-field rewrap workflows. Until then, do not change Flask
session secret derivation, and do not add startup-time schema mutation or
implicit secret-row creation.

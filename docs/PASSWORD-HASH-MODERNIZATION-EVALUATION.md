# Password Hash Modernization Evaluation

Date: 2026-05-26

Status: Recommendation for authentication-hash modernization

## Scope

This memo evaluates whether Hush Line should adopt Argon2 for user password
hashes and defines the requirements for any future password-hash migration.

It does not change production authentication behavior. Current password writes
and compatibility behavior remain controlled by `hushline/password_hasher.py`,
`PASSWORD_HASH_WRITE_USE_WERKZEUG_SCRYPT`, and
`PASSWORD_HASH_REHASH_ON_AUTH_ENABLED`.

Password hashing is separate from encrypted-field modernization. Do not combine
password-hash changes with encrypted database-field envelope, AAD, algorithm, or
migration changes.

## Recommendation

Defer Argon2 adoption for now and keep the current migration path: verify
legacy passlib `$scrypt$` hashes, optionally write pinned Werkzeug scrypt, and
optionally rehash legacy passlib hashes to pinned Werkzeug scrypt on successful
authentication.

Argon2id remains a credible future candidate because it is a modern
memory-hard password hashing algorithm with broad security review and common
framework support. It is not urgent enough to justify a new production write
format in the same cycle as encrypted-field modernization, because Hush Line's
current passlib and Werkzeug paths already use memory-hard scrypt and the
account-lockout risk is higher than the near-term security gain.

Proceed only with documentation, reporting, and compatibility hardening until
maintainers explicitly approve an Argon2 rollout plan.

## Current Behavior Reviewed

Hush Line currently supports two password hash families:

- passlib scrypt, with prefixes like `$scrypt$ln=16,r=8,p=1$...`.
  This is the legacy default for existing accounts and the current default
  write format unless Werkzeug writes are enabled. Verification uses
  `passlib.hash.scrypt.verify()`.
- Werkzeug scrypt, with prefixes like `scrypt:65536:8:1$...`.
  This is the native prefix-based target for optional new writes and legacy
  rehash-on-auth. Verification uses
  `werkzeug.security.check_password_hash()`.
- Unknown dollar-style hashes, such as `$argon2id$...`, are unsupported today
  and fail closed without mutating the stored password hash.
- Unknown native-style prefixes, such as `hl-v2:...`, are reserved for future
  primary verifiers. They route to `verify_primary_password_hash()` and are
  denied unless a reviewed verifier exists.

`PINNED_WERKZEUG_SCRYPT_METHOD` is `scrypt:65536:8:1`, which matches the legacy
passlib cost baseline of `ln=16,r=8,p=1`. That keeps the current migration from
being an algorithm-strength downgrade.

The existing compatibility layer already emits non-sensitive telemetry for:

- successful and failed password hash verification
- password hash writes
- successful and failed rehash-on-auth attempts
- hash format and prefix classification without logging usernames, plaintext
  passwords, or full stored hashes

## Argon2 Evaluation

Argon2id would be the only Argon2 variant Hush Line should consider for
password storage. Argon2d is not appropriate for password hashing because of
side-channel concerns, and Argon2i is less preferred for password-verifier use
than Argon2id in modern guidance.

Benefits:

- strong memory-hard design intended for password hashing
- tunable memory, time, and parallelism parameters
- broad familiarity among security reviewers
- clean algorithm-agility story when introduced through
  `hushline/password_hasher.py`

Costs and risks:

- likely adds or promotes a runtime dependency such as `argon2-cffi`
- needs deployment-specific memory and CPU tuning before production writes
- increases login-path denial-of-service risk if parameters are too expensive
- creates another stored verifier format that must be supported through a full
  migration and rollback window
- does not directly improve encrypted-field confidentiality, E2EE behavior, or
  disclosure handling

Argon2 is worth reconsidering after the current passlib-to-Werkzeug scrypt path
has completed or reached a stable operating point. Until then, adding Argon2
would create two simultaneous password-hash migrations and make account-lockout
signals harder to interpret.

## Migration Requirements If Recommended Later

A future Argon2 migration must be compatibility-first:

- keep passlib scrypt and Werkzeug scrypt verification deployed before, during,
  and after the first Argon2 write rollout
- add Argon2 verification only inside `hushline/password_hasher.py`
- write Argon2 only behind an explicit configuration flag after maintainer
  approval
- rehash only after successful authentication of the existing stored hash
- preserve the original stored hash if the replacement write fails, the session
  state changes, or a second factor has not completed
- continue to fail closed for unknown or malformed prefixes
- never prehash passwords through encrypted-field or vault-derived material as
  part of this migration
- add tests for registration, password change, login without 2FA, login with
  2FA, failed login, malformed hash, rollback, and telemetry behavior

Rehash-on-auth should update one account at a time during normal successful
login. Bulk offline password rehashing is not possible because plaintext
passwords are not available.

## Metrics And Reporting

Before any Argon2 write flag is enabled, operators need enough reporting to
avoid account lockout and detect rollback pressure:

- database counts by stored hash format: passlib scrypt, Werkzeug scrypt,
  Argon2id, unknown native prefix, and unknown dollar prefix
- verification success and failure counters by hash format
- rehash-on-auth success and failure counters by source and target format
- new hash write counters by target format
- login failure-rate monitoring during each rollout step
- a removal gate requiring legacy verification success volume to stay at zero
  for a full release window before any legacy verifier is removed
- reporting that never includes usernames, plaintext passwords, full password
  hashes, disclosure content, private keys, or sensitive tokens

The existing `password-hash report` and `password-hash can-remove-passlib`
commands cover the current passlib removal gate. An Argon2 rollout should extend
that reporting rather than introduce a separate migration dashboard.

## Rollback Behavior

Rollback must favor account availability:

- if Argon2 writes are disabled, existing Argon2 hashes must still verify
- reverting to a build that cannot verify Argon2 is not a valid rollback after
  any Argon2 hash has been written
- the old passlib and Werkzeug verifiers must remain until measured use is zero
  for the approved release window
- failed rehash-on-auth must leave the original stored hash unchanged
- rollback must not require users to reset passwords solely because the write
  algorithm flag was disabled
- removing an Argon2 dependency or verifier requires a separate removal gate
  with zero stored rows and zero measured Argon2 verification successes

## Decision Record

Do not adopt Argon2 in this issue.

Keep the current compatibility path and finish the passlib-to-Werkzeug scrypt
operational migration first. Revisit Argon2id only as a separate
authentication-focused proposal with explicit maintainer approval, dependency
review, parameter benchmarking, compatibility tests, rehash-on-auth telemetry,
and rollback criteria.

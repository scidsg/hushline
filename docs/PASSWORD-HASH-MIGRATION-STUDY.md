# Password Hash Migration Study

Date: 2026-03-12

## Recommendation

Use `werkzeug.security` scrypt for all new password writes, keep `passlib` in a read-only compatibility role for existing `$scrypt$...` hashes during the transition, and opportunistically rehash legacy hashes after successful password verification.

This is the lowest-risk path because it:

- avoids a new runtime dependency;
- stays inside the Flask/Werkzeug stack already shipped by Hush Line;
- preserves logins for existing users without a forced password reset; and
- lets rollout happen in phases with a clean stop point before any write-path change.

`passlib` package removal should not be coupled to the first migration release. Without a forced reset policy, dormant accounts can keep legacy hashes indefinitely. Full removal therefore requires one of these end states:

- legacy hash count reaches zero; or
- a separately reviewed in-repo verifier for the legacy passlib `$scrypt$` format ships and is locked down with fixture-based tests.

## Current State

Current password hashing lives in [`hushline/model/user.py`](../hushline/model/user.py):

- `User.password_hash` writes a passlib scrypt hash.
- `User.check_password()` verifies via passlib.

Current auth flows that depend on this behavior:

- registration in [`hushline/routes/auth.py`](../hushline/routes/auth.py);
- login in [`hushline/routes/auth.py`](../hushline/routes/auth.py); and
- password change in [`hushline/settings/common.py`](../hushline/settings/common.py).

Existing tests already prove the current write format is passlib scrypt and that login/password-change flows rely on it.

## Candidate Evaluation

| Candidate                                                                        | Outcome                      | Why                                                                                                                                                          |
| -------------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `werkzeug.security` scrypt                                                       | Selected                     | Already in stack, maintained with Flask/Werkzeug, explicit write/verify API, lowest adoption risk.                                                           |
| `argon2-cffi` or another dedicated password-hash library                         | Rejected for first migration | Strong option long term, but adds a new runtime dependency and combines a dependency migration with an algorithm migration.                                  |
| Custom `hashlib.scrypt` or `cryptography` wrapper that reproduces passlib format | Rejected for first migration | Could remove `passlib` sooner, but bespoke hash parsing/serialization in a security-critical path is higher risk than using maintained framework primitives. |
| Staying on `passlib`                                                             | Rejected                     | Dependency is already marked unmaintained in-repo and is producing warning suppression in test configuration.                                                |

## Target Hashing API

Recommended target for new hashes: `werkzeug.security.generate_password_hash(..., method=<explicit scrypt method string>)` with `check_password_hash()` for all non-legacy hashes.

Two constraints are required:

1. Do not rely on library defaults.
   The implementation should pin an explicit scrypt method string so the work factor is stable across upgrades.
2. Do not ship a weaker cost than the current passlib output.
   The implementation issue should first capture one canonical passlib-generated fixture and compare the effective cost parameters before switching any write path.

The target algorithm should remain scrypt for this migration. Changing both dependency and algorithm at once is avoidable risk in a safety-critical login path.

## Legacy Compatibility Strategy

During transition, verification should dispatch by stored hash format:

- `$scrypt$...`: verify with `passlib` only.
- `scrypt:...` or any future Hush Line native prefix: verify with the new primary verifier.
- unknown prefix: fail closed, emit structured error telemetry, and leave the stored hash untouched.

This keeps compatibility logic narrow and auditable. It also avoids attempting heuristic detection based on hash length or field contents.

## Migration Semantics

Recommended behavior:

- no forced password reset by default;
- no bulk data migration;
- opportunistic rehash after a successful legacy-password verification; and
- password change always writes the new format once the write switch is enabled.

Rehash-on-auth should only run when all of these are true:

- verification succeeded against a legacy passlib hash;
- the request already reached the authenticated path;
- the account is not mid-2FA failure handling; and
- a feature flag for legacy rehash is enabled.

This lets maintainers separate three risks:

- adding a format-aware verifier;
- changing the write path; and
- mutating user data during login.

## Rollout Phases

### Phase 1: Abstraction and telemetry only

- add a password-hasher module with format dispatch;
- keep all writes in passlib format;
- instrument auth success by hash format; and
- prove zero behavior change in login, registration, and password-change tests.

Rollback: trivial. Writes are unchanged.

### Phase 2: Dual-format verification

- ship verifier support for both passlib legacy hashes and the target format;
- keep writes on passlib for one release while telemetry burns in.

Rollback: safe. No new stored hash format yet.

### Phase 3: Switch new writes

- move registration and password changes to Werkzeug scrypt;
- keep dual-format verification in place;
- keep rehash-on-auth disabled initially.

Rollback: only roll back to a release that still includes dual-format verification. Rolling back to a passlib-only release would strand users whose password was written in the new format.

### Phase 4: Enable opportunistic rehash

- on successful login against a legacy hash, rewrite to the target format;
- record that the upgrade happened; and
- keep all error handling fail-closed.

Rollback: disable the feature flag first. Existing upgraded hashes continue to verify because dual-format verification remains in the codebase.

### Phase 5: Remove passlib

Only remove the dependency after one of these conditions is met:

- no legacy `$scrypt$` rows remain in production and staging; or
- maintainers approve a separate legacy-verifier implementation that no longer depends on passlib.

## Telemetry Needed

Telemetry must stay aggregate and must not log usernames, password material, or raw hashes.

Recommended counters:

- successful password verifications by hash format;
- failed password verifications by hash format prefix;
- new password writes by hash format;
- rehash-on-auth success count;
- rehash-on-auth failure count;
- current count of rows with legacy `$scrypt$` hashes.

Removal gate:

- legacy row count at zero for at least one full release cycle; and
- no legacy verification successes observed during the same window.

If maintainers do not want a dormant-account reset policy, plan for the possibility that `passlib` remains in read-only compatibility mode longer than expected.

## Rollback Plan

If authentication regressions appear:

1. disable rehash-on-auth;
2. disable new-format writes if they have been enabled;
3. keep dual-format verification enabled so both stored formats still log in;
4. review telemetry broken down by format prefix; and
5. revert only to a build that still contains the dual-format verifier.

No rollback plan should require rewriting hashes back to the legacy format.

## Test Plan

Follow-up implementation issues should add tests for all of the below:

- legacy passlib hash fixture verifies successfully;
- legacy passlib hash fixture fails for the wrong password;
- new target-format hash generation uses the pinned method string;
- new target-format hash verifies successfully;
- login succeeds for both legacy and new hash formats;
- password change writes the target format once the write switch is enabled;
- successful legacy login upgrades the hash when rehash-on-auth is enabled;
- successful legacy login does not upgrade the hash when the feature flag is disabled;
- 2FA flow still works when the first-factor password came from either hash format;
- unknown hash prefixes fail closed and do not mutate stored state;
- regression coverage for registration, login failure messaging, and password change;
- telemetry paths do not log secrets or plaintext.

## Follow-up Issue Breakdown

1. Add a password-hasher abstraction with explicit format dispatch and aggregate auth telemetry.
2. Add fixture-based tests for legacy passlib scrypt verification and wrong-password failure.
3. Add dual-format verification support while keeping passlib writes unchanged.
4. Switch registration and password-change writes to pinned Werkzeug scrypt parameters behind a feature flag.
5. Add optional rehash-on-auth for successful legacy logins behind a separate feature flag.
6. Add operational reporting for remaining legacy-hash rows and legacy verify volume.
7. Remove `passlib` only after the documented removal gate is met or a reviewed legacy verifier replaces it.

## Open Risk

The main unresolved risk is dormant accounts. If Hush Line keeps the current "no forced reset by default" requirement, legacy hashes may survive indefinitely. That is compatible with the recommended migration, but it means dependency removal is a second milestone, not part of the first cutover.

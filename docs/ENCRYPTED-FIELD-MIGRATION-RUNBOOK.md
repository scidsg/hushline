# Encrypted Field Migration Runbook

Date: 2026-05-26

Status: Draft for rehearsal before production use

## Scope

This runbook defines the required operating plan for a future migration that
rewrites existing encrypted database fields from legacy Fernet ciphertext to a
new encrypted-field envelope. It covers local, staging, and production
execution, but it does not introduce migration helper code and must not be used
until maintainers approve the specific helper, target format, and rollout
configuration.

The current `envelope-fernet` target is a transitional compatibility format. It
adds versioned envelope handling around Fernet ciphertext, but it does not
cryptographically bind ciphertext to field, domain, or row AAD. A migration to
`envelope-fernet` must not be described as domain-bound authenticated field
encryption, and it does not complete a best-in-class migration of existing
production ciphertext.

The encrypted-field inventory is the code-owned contract in
`hushline.crypto.ENCRYPTED_FIELD_CONTRACTS` and the protected-field table in
[`ENCRYPTED-FIELD-MODERNIZATION-ADR.md`](ENCRYPTED-FIELD-MODERNIZATION-ADR.md).
The migration must remain forward-only and must not edit historical Alembic
migrations.

## Operator Guardrails

- Keep the dual reader deployed before, during, and after the migration.
- Keep legacy Fernet read support enabled until migration completion and the
  rollback window are explicitly closed.
- Do not enable production encrypted-field migration live mode or envelope
  writes until a completed
  [`ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md`](ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md)
  artifact has been reviewed and approved by maintainers.
- Do not enable envelope writes until the dual reader is deployed, migration
  `b2039e7c0a1d` has widened encrypted short-string columns, the migration and
  ciphertext fit tests have passed, and the executable preflight reports ready.
- Do not represent `envelope-fernet` release gates as production AAD guarantees;
  those gates prove compatibility, storage fit, decryptability, and rollback
  readiness for a transitional format only.
- Do not call an existing-ciphertext migration complete in the domain-bound or
  best-in-class sense until a production AEAD writer is implemented, rehearsed,
  and approved.
- Do not drop, blank, truncate, or overwrite source ciphertext before the
  replacement value has been decrypted and verified for that row.
- Do not assume a maintenance window. Run in small batches while normal reads
  and writes continue unless maintainers explicitly approve downtime.
- Do not log plaintext, private keys, raw encrypted-field secrets, or full
  ciphertext values.
- Do not combine this migration with password hashing, Flask session secret,
  application secret management, or unrelated schema changes.

## Environments

### Local

Use local execution to prove the helper mechanics against seeded and synthetic
records before staging data is touched.

1. Run the helper in dry-run mode against local data.
   `flask encrypted-field migrate --dry-run --batch-size 100` verifies the
   same row-selection, decryption, target rewrite, and plaintext comparison
   path used by live mode without writing.
2. Confirm every inventory entry reports row counts, legacy-format counts,
   target-format counts, and decryptability results.
3. Run a small live batch against disposable local data.
   Use `flask encrypted-field migrate --live --batch-size 10` for an initial
   bounded batch.
4. Stop the helper mid-run, then resume it with the same target format and batch
   size by passing the previous `Next resume token` value to
   `flask encrypted-field migrate --live --batch-size 10 --resume-token TOKEN`.
5. Confirm already migrated rows are skipped and remaining rows continue.

### Staging

Use staging as the production rehearsal. Staging must use production-like
configuration, data volume, and key-management procedures without exposing
production plaintext.

1. Confirm the deployed application reads both legacy Fernet and target envelope
   values.
2. Capture the JSON preflight artifact with row counts and decryptability
   checks, and archive it with staging release evidence.
3. Rehearse backup creation and restore into a separate staging database.
4. Run dry-run mode and review the progress and failure report.
5. Run live migration in small batches, including at least one intentional
   interruption and resume.
6. Verify application reads, settings updates, notification recipient updates,
   inbox reads, resend behavior, and data export for migrated rows.
7. Rehearse rollback with the old reader still deployed.

### Production

Production execution requires maintainer approval after a completed rehearsal
evidence report is reviewed. Use the same helper version, target format, batch
size ceiling, and rollback plan proven in staging or restored-backup rehearsal.

1. Confirm the current release includes the dual reader and that legacy Fernet
   reads are still enabled.
2. Confirm migration `b2039e7c0a1d` has widened encrypted short-string columns
   and that migration and ciphertext fit tests passed for the release.
3. Confirm recent backups exist and a restore rehearsal has succeeded for the
   same database version and key material.
4. Confirm the reviewed rehearsal evidence report captures the backup restore
   timestamp, schema revision, preflight output, dry-run output, live-batch
   rehearsal output, interruption/resume result, rollback rehearsal result, and
   operator signoff without plaintext, secrets, private keys, tokens, or full
   ciphertext values.
5. Run preflight checks, archive the JSON release-gate artifact, and run
   dry-run mode.
6. Enable transitional envelope writes only after the schema/ciphertext
   preflight reports ready, and label `envelope-fernet` evidence as
   compatibility evidence rather than production AAD evidence.
7. Start with a small live batch. Increase batch size only after error-free
   progress and normal application health are observed.
8. Pause between batches when needed; do not hold long transactions across the
   full inventory.
9. Keep the old reader deployed after completion until post-migration
   verification and rollback criteria have passed.

## Preflight Checks

Preflight must be read-only and must fail closed before any write occurs.
Run the executable preflight before enabling envelope writes:

- Local: run `flask encrypted-field preflight` after seeded or synthetic
  encrypted-field records exist and before changing
  `ENCRYPTED_FIELD_WRITE_FORMAT`.
- Staging: run `flask encrypted-field preflight --output json` after deploying
  the dual-reader release and completing the schema migration; save the JSON
  artifact with staging rehearsal evidence.
- Production: run `flask encrypted-field preflight --output json` after
  confirming backups and schema migration completion, immediately before
  changing `ENCRYPTED_FIELD_WRITE_FORMAT` to the target envelope format.

The command reports the current Alembic revision, envelope-safe storage
capacity for each encrypted-field contract, schema revision, contract-set
version, selected contract IDs, batch size, row counts, legacy Fernet, envelope
Fernet, null/empty, malformed, and decrypt-failure counts, and whether every
non-empty value decrypts through the deployed reader. It must not print
plaintext or raw full ciphertext.

Use `--contract CONTRACT_ID` one or more times for targeted checks before a
full release gate. Use `--batch-size N` to bound each scan query for large
datasets; the release-gate artifact must still cover every encrypted-field
contract unless maintainers explicitly approve a targeted gate.

- Confirm the deployed code can read legacy Fernet and the target envelope
  format.
- Confirm `ENCRYPTION_KEY` and any future encrypted-field key material are
  present through the approved secret path for the environment.
- Confirm the target write format is explicitly configured for the planned
  migration and whether it is transitional compatibility or domain-bound AEAD.
- Confirm the database revision is the expected forward-only revision.
- Count rows for each encrypted-field contract:
  - total rows in the table
  - rows with null or empty encrypted values
  - rows with legacy Fernet ciphertext
  - rows with target envelope ciphertext
  - rows with unknown or malformed ciphertext
- Decrypt every non-empty encrypted value, or sample only if maintainers approve
  a documented sampling plan for very large production tables.
- Report counts by contract ID, table, column, and ciphertext format.
- Stop before live mode if any non-empty row cannot be classified or decrypted.

## Dry-Run Behavior

Dry-run mode must execute the same selection, classification, decryption,
reencryption, and verification path as live mode, except for database writes.

Run dry-run mode with the maintainer-approved target format:

`flask encrypted-field migrate --dry-run --target-format TARGET-FORMAT --batch-size 100`

Use `--contract CONTRACT_ID` one or more times to limit rehearsal to a specific
encrypted-field contract. Use the reported `Next resume token` with the same
target format, batch size, and contract set to continue a bounded dry run.

For each candidate row, dry-run mode must:

1. Load the row using the same ordering used by live batches.
2. Classify the existing ciphertext format.
3. Decrypt the existing ciphertext through the production reader.
4. Build the replacement ciphertext using the target writer.
5. Decrypt the replacement ciphertext through the production reader.
6. Compare replacement plaintext with source plaintext in memory.
7. Emit counters and row identifiers only, never plaintext or full ciphertext.

Dry-run output must include eligible rows, skipped rows, already migrated rows,
verification failures, decrypt failures, and the next resume position that live
mode would use.

## Small-Batch Execution

Live migration must process bounded batches. The default batch size should be
small enough to avoid long locks, large transactions, and operational surprise;
production batch-size increases require operator review of staging timing and
production health.

Run live mode with the maintainer-approved target format:

`flask encrypted-field migrate --live --target-format TARGET-FORMAT --batch-size 10`

Resume an interrupted live run with the exact token reported by the prior run:

```shell
flask encrypted-field migrate --live --target-format TARGET-FORMAT \
  --batch-size 10 --resume-token TOKEN
```

For each batch:

1. Select rows in stable primary-key order for one encrypted-field contract.
2. Lock only the rows being processed when the helper needs write consistency.
3. Decrypt the source ciphertext.
4. Create the replacement ciphertext without mutating the source value.
5. Decrypt and verify the replacement ciphertext.
6. Write the replacement only after verification succeeds.
7. Commit the batch.
8. Emit progress for the contract, last processed primary key, rows migrated,
   rows skipped, and failures.

If any row fails decryption, reencryption, verification, or update, the helper
must leave that row's original ciphertext intact, record the failure, and stop
or quarantine according to maintainer-approved helper behavior.

## Idempotent Resume

Resume behavior must be safe after process crashes, deploy restarts, database
failover, and operator cancellation.

- Classify each row by its current stored format on every run.
- Skip rows already in the target envelope format after verifying they still
  decrypt.
- Reprocess legacy-format rows even if their primary key is lower than the last
  reported resume position when the operator explicitly requests a full scan.
- Store or print a resume token containing only contract ID, last processed
  primary key, target format, helper version, and batch size.
- The executable helper prints this state as `Next resume token`. In live mode,
  a value of `complete` means no legacy-format rows remain for the selected
  contract set.
- Reject resume when the helper version, target format, or encrypted-field
  contract set differs from the dry-run or prior live execution unless
  maintainers approve a new dry run.
- Treat rerunning the helper from the beginning as valid and non-destructive.

## Per-Row Verification

Every rewritten row must be verified before source ciphertext is replaced.

Verification must prove:

- The source ciphertext decrypts through the old reader.
- The candidate replacement decrypts through the deployed reader.
- The replacement plaintext exactly matches the source plaintext.
- The replacement uses the expected contract ID, domain, table, column, and AAD
  values for the row when the approved target format is domain-bound AEAD. For
  `envelope-fernet`, verification proves the expected transitional envelope
  format and plaintext round trip, not cryptographic AAD binding.
- The database update affects exactly one expected row.
- A post-update read decrypts to the same plaintext before the batch is counted
  as migrated.

Verification failures are migration blockers. Do not continue to later batches
until maintainers have reviewed the failure class and decided whether to fix
helper code, repair data, restore from backup, or retry.

## Backup And Restore Rehearsal

Before production live mode, operators must complete and document a restore
rehearsal in a reviewed
[`ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md`](ENCRYPTED-FIELD-REHEARSAL-REPORT-TEMPLATE.md)
artifact.

The rehearsal must confirm:

- A database backup can be restored into an isolated environment.
- The restored environment has the matching encrypted-field key material.
- Legacy Fernet rows decrypt after restore.
- Target envelope rows decrypt after restore.
- The migration helper can dry-run against the restored database.
- A small live-batch rehearsal can run without exposing sensitive values in the
  report.
- An intentional interruption can resume and skip already migrated rows.
- Rollback can run on restored data while the old reader remains deployed.

Backups without matching encrypted-field key material are not complete recovery
artifacts for this migration.

The reviewed report must capture the backup restore timestamp, schema revision,
preflight output, dry-run output, live-batch rehearsal output,
interruption/resume result, rollback rehearsal result, and operator signoff.
It must not include plaintext disclosures, secrets, private keys, tokens, raw
encrypted-field secrets, or full ciphertext values.

## Progress And Failure Reporting

Migration output must be observable without exposing sensitive values.

Required progress fields:

- helper version
- environment name
- dry-run or live mode
- contract ID
- table and column
- batch size
- last processed primary key
- total candidate rows
- already migrated rows
- migrated rows
- skipped rows
- decrypt failures
- verification failures
- update failures
- elapsed time
- next resume token

Failure reports must include the contract ID, primary key, failure phase, error
class, and whether the source ciphertext was left unchanged.
Reports must not include plaintext or full ciphertext.

## Rollback

Rollback must preserve the old reader. The safest rollback for application code
is to redeploy a release that still reads both legacy Fernet and target envelope
values, then set new writes back to the previously approved format while
operators investigate.

Rollback requirements:

1. Do not remove legacy Fernet read support.
2. Do not run a destructive down migration against encrypted-field data. The
   widening migration downgrade must fail if any value in a widened encrypted
   short-string column is longer than 255 characters; operators must keep the
   widened schema until oversized envelope ciphertext is removed or converted
   through a maintainer-approved, per-row-verified path.
3. If live migration has started, keep migrated target-envelope rows readable by
   the deployed dual reader.
4. If helper code supports reverse rewriting, run it only after a restore
   rehearsal proves target-envelope values can be converted back to legacy
   Fernet and per-row verified.
5. If helper behavior is suspected, stop the helper, keep the dual reader
   deployed, and restore from the rehearsed backup only if maintainers decide
   the mixed-format database is unsafe to keep serving.
6. After rollback, rerun preflight decryptability checks across all encrypted
   field contracts and verify normal application reads.

Rollback is not complete until both legacy-format and target-format rows that
remain in the database are readable by the deployed application.

## Completion Criteria

The migration can be considered complete only after:

- all encrypted-field contracts have zero unexpected-format rows
- every non-empty encrypted value decrypts through the deployed reader
- dry-run mode reports no remaining live changes
- application flows that read encrypted fields pass manual review in production
- backups taken after migration have been restored and decryptability checked
- maintainers explicitly approve closing the rollback window

Legacy Fernet read support may be removed only in a later issue after the
rollback window is closed and a separate removal plan is approved.

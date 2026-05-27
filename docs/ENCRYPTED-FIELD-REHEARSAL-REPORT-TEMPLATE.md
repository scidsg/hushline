# Encrypted Field Rehearsal Evidence Report Template

Use this template for restored-backup and staging validation before any
production encrypted-field migration or envelope-write enablement.

## Privacy Rules

Do not include plaintext disclosures, message bodies, secrets, private keys,
tokens of any kind, TOTP secrets, email passwords, raw encrypted-field secrets,
or full ciphertext values in this report.

Use counts, contract IDs, schema revisions, timestamps, command exit statuses,
redacted log excerpts, and reviewer notes. If an output excerpt is needed,
redact sensitive values before pasting it here.

## Report Metadata

- Report ID:
- Rehearsal type: restored backup / staging dry run / staging live-batch rehearsal
- Environment name:
- Application release or commit:
- Migration helper version:
- Target encrypted-field format:
- Operator:
- Reviewer:
- Report status: draft / submitted / reviewed-approved / reviewed-blocked
- Review date:

## Restore And Schema Evidence

- Backup identifier:
- Backup creation timestamp, UTC:
- Backup restore timestamp, UTC:
- Isolated restore target:
- Schema revision before rehearsal:
- Schema revision after rehearsal:
- Encrypted-field contract-set version:
- Key material availability confirmed without exposing key values: yes / no
- Restore validation notes:

## Preflight Evidence

- Preflight command mode:
- Preflight artifact location:
- Preflight completed at, UTC:
- Exit status:
- Schema revision reported by preflight:
- Contract coverage:
- Legacy-format row count:
- Target-format row count:
- Malformed or unknown-format row count:
- Decrypt-failure count:
- Redacted output excerpt or summary:
- Operator assessment:

## Dry-Run Evidence

- Dry-run artifact location:
- Dry-run completed at, UTC:
- Batch size:
- Contract coverage:
- Eligible row count:
- Already migrated row count:
- Skipped row count:
- Verification-failure count:
- Decrypt-failure count:
- Next resume state, such as complete, pending, or redacted summary:
- Redacted output excerpt or summary:
- Operator assessment:

## Live-Batch Rehearsal Evidence

- Live-batch artifact location:
- Live-batch completed at, UTC:
- Batch size:
- Contract coverage:
- Rows migrated:
- Rows skipped:
- Verification-failure count:
- Decrypt-failure count:
- Update-failure count:
- Next resume state, such as complete, pending, or redacted summary:
- Application read checks performed:
- Redacted output excerpt or summary:
- Operator assessment:

## Interruption And Resume Evidence

- Interruption method:
- Interrupted at, UTC:
- Resume started at, UTC:
- Resume completed at, UTC:
- Resume state, such as complete, pending, or redacted summary:
- Already migrated rows were skipped after resume: yes / no
- Remaining rows continued after resume: yes / no
- Verification-failure count after resume:
- Decrypt-failure count after resume:
- Redacted output excerpt or summary:
- Operator assessment:

## Rollback Rehearsal Evidence

- Rollback approach rehearsed:
- Rollback started at, UTC:
- Rollback completed at, UTC:
- Old reader remained deployed during rehearsal: yes / no
- Legacy-format rows readable after rollback: yes / no
- Target-format rows readable after rollback: yes / no
- Post-rollback preflight artifact location:
- Redacted output excerpt or summary:
- Operator assessment:

## Operator Signoff

- Production release-gate manifest location:
- Production release-gate command status: ready / blocked / not run
- Maintainer approval reference:
- Production enablement recommendation: proceed / block
- Blocking issues:
- Follow-up issues:
- Operator name:
- Operator signed at, UTC:
- Reviewer name:
- Reviewer signed at, UTC:

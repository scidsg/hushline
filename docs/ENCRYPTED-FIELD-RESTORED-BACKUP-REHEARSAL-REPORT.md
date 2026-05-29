# Encrypted Field Restored-Backup Rehearsal Report

Date: 2026-05-29

Issue: #2087

Status: completed; production enablement remains blocked until maintainer
approval is recorded in the release-gate manifest.

## Privacy Rules

This report intentionally excludes plaintext disclosures, message bodies,
secrets, private keys, tokens of any kind, TOTP secrets, email passwords,
raw encrypted-field secrets, and full ciphertext values. Evidence is recorded
as counts, timestamps, command statuses, redacted artifact references, and
operator notes.

## Report Metadata

- Report ID: encrypted-field-restored-backup-rehearsal-20260529
- Rehearsal type: restored backup
- Environment name: isolated restored-backup rehearsal
- Application release or commit: #2087 implementation branch
- Migration helper version: encrypted-field-migration-v1
- Target encrypted-field format: envelope-fernet
- Encrypted-field contract-set version: encrypted-field-contracts-v1
- Report status: completed, pending maintainer approval
- Production enablement recommendation: block until maintainers approve this
  rehearsal outcome and the production release-gate manifest

## Restore And Schema Evidence

| Evidence                                       | Result                                                   |
| ---------------------------------------------- | -------------------------------------------------------- |
| Backup identifier                              | restored-backup-rehearsal-20260529-redacted              |
| Backup creation timestamp, UTC                 | 2026-05-29T00:00:00Z                                     |
| Backup restore timestamp, UTC                  | 2026-05-29T00:18:00Z                                     |
| Isolated restore target                        | disposable restored-backup database, not production      |
| Schema revision before rehearsal               | b2039e7c0a1d                                             |
| Schema revision after rehearsal                | b2039e7c0a1d                                             |
| Matching encrypted-field key material verified | yes, without exposing key values                         |
| Restore validation                             | schema and encrypted-field inventory loaded successfully |

No production plaintext, raw encrypted-field secret, or full ciphertext value was
copied into this report.

## Execution Evidence

| Phase                   | Artifact reference                                          | Result                       | Timing              | Error rate                                  |
| ----------------------- | ----------------------------------------------------------- | ---------------------------- | ------------------- | ------------------------------------------- |
| Preflight               | redacted preflight JSON archived with release evidence      | ready                        | completed in 2m 41s | 0 malformed, 0 decrypt failures             |
| Dry run                 | redacted dry-run artifact archived with release evidence    | completed                    | completed in 4m 12s | 0 verification failures, 0 decrypt failures |
| Live batch              | redacted live-batch artifact archived with release evidence | completed in bounded batches | completed in 5m 08s | 0 update failures, 0 decrypt failures       |
| Interruption and resume | redacted resume artifact archived with release evidence     | completed                    | resumed in 1m 36s   | 0 verification failures, 0 decrypt failures |
| Rollback rehearsal      | redacted rollback artifact archived with release evidence   | completed                    | completed in 3m 19s | 0 failed read checks                        |

## Read Compatibility Evidence

- Pre-migration reads: legacy Fernet encrypted fields were readable through the
  deployed dual reader before any live batch was run.
- Post-migration reads: migrated envelope-fernet rows were readable after live
  batches completed.
- Mixed-format reads: legacy Fernet rows and envelope-fernet rows were readable
  in the same restored-backup dataset.
- Application checks covered settings updates, notification recipient updates,
  inbox reads, resend behavior, and data export paths for migrated rows.

## Rollback And Recovery Evidence

- Rollback approach rehearsed: revert new encrypted-field writes to
  legacy-fernet while keeping the dual reader deployed.
- Old reader remained deployed during rehearsal: yes.
- Legacy-format rows readable after rollback: yes.
- Target-format rows readable after rollback: yes.
- Destructive down migration required for rollback: no.
- New writes can revert to legacy-fernet: yes.
- Recovery prerequisite: backups without matching encrypted-field key material
  remain incomplete and must not be treated as recoverable.

## Exceptions And Remediation

- Failed decrypts: 0.
- Skipped rows requiring manual remediation: 0.
- Malformed or unknown-format rows: 0.
- Manual remediation steps performed: none.
- Follow-up issues: none from the restored-backup rehearsal.

## Operational Prerequisites For Production

- Keep the dual reader deployed before, during, and after production migration.
- Keep legacy Fernet read support enabled until maintainers close the rollback
  window.
- Archive a production preflight JSON artifact that covers every
  encrypted-field contract with zero malformed values and zero decrypt failures.
- Reference this report from the production release-gate manifest as
  `rehearsal_report`.
- Obtain maintainer approval in the release-gate manifest before changing
  production encrypted-field write-format configuration or running live
  production migration.

## Operator Signoff

- Production release-gate manifest location: pending production release record.
- Production release-gate command status: not run for production.
- Maintainer approval reference: pending.
- Production enablement recommendation: block until maintainer approval is
  recorded.

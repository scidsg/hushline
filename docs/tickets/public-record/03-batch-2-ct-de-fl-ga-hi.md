# Batch 2 Adapters: CT, DE, FL, GA, HI

## Summary

Implement official-source discovery adapters for:

- Connecticut (`CT`)
- Delaware (`DE`)
- Florida (`FL`)
- Georgia (`GA`)
- Hawaii (`HI`)

## Scope

- Implement adapter logic and strict source-policy compliance.
- Add tests for discovery/add/skip behavior and source correctness.
- Refresh and commit dataset updates.

## Acceptance Criteria

- All states in this batch have implemented adapters.
- `source_url` values are exact official record URLs, not directory landing pages.
- Domain/label policy checks pass for each listing.
- Dead/invalid records are removed during refresh.
- Roadmap updated with status and any state blockers.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

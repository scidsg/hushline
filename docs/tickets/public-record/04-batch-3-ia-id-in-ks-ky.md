# Batch 3 Adapters: IA, ID, IN, KS, KY

## Summary

Implement official-source discovery adapters for:

- Iowa (`IA`)
- Idaho (`ID`)
- Indiana (`IN`)
- Kansas (`KS`)
- Kentucky (`KY`)

## Acceptance Criteria

- Implemented adapters for all states in this batch.
- Strict per-record provenance URLs only.
- No generic source pages, no private ranking sources.
- Add/skip-existing tests and state-policy tests pass.
- Dataset refreshed and committed.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

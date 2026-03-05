# Batch 6 Adapters: ND, NE, NH, NJ, NM

## Summary

Implement official-source discovery adapters for:

- North Dakota (`ND`)
- Nebraska (`NE`)
- New Hampshire (`NH`)
- New Jersey (`NJ`)
- New Mexico (`NM`)

## Acceptance Criteria

- Adapter implementations exist for all listed states.
- Only official, exact record URLs are emitted as `source_url`.
- Tests confirm adapter behavior and strict source-policy compliance.
- Refresh output and roadmap status are updated.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

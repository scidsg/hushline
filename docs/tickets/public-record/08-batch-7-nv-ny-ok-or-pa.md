# Batch 7 Adapters: NV, NY, OK, OR, PA

## Summary

Implement official-source discovery adapters for:

- Nevada (`NV`)
- New York (`NY`)
- Oklahoma (`OK`)
- Oregon (`OR`)
- Pennsylvania (`PA`)

## Acceptance Criteria

- All batch states have implemented adapters.
- Source records are official and record-specific.
- No generic listing URLs survive refresh validation.
- Additions/removals are reflected in refreshed dataset.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

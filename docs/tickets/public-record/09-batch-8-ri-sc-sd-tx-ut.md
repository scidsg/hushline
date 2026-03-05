# Batch 8 Adapters: RI, SC, SD, TX, UT

## Summary

Implement official-source discovery adapters for:

- Rhode Island (`RI`)
- South Carolina (`SC`)
- South Dakota (`SD`)
- Texas (`TX`)
- Utah (`UT`)

## Acceptance Criteria

- Adapter implementations and tests are complete for all states in this batch.
- Each row includes exact official record provenance URL.
- Dataset refresh removes dead/invalid entries and keeps only strict records.
- Roadmap updated with batch progress.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

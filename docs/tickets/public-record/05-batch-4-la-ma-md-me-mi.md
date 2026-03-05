# Batch 4 Adapters: LA, MA, MD, ME, MI

## Summary

Implement official-source discovery adapters for:

- Louisiana (`LA`)
- Massachusetts (`MA`)
- Maryland (`MD`)
- Maine (`ME`)
- Michigan (`MI`)

## Acceptance Criteria

- All five adapters implemented with strict official per-record provenance.
- Source policy checks pass for label/domain/record specificity.
- Discovery tests cover add behavior and existing-row skip behavior.
- Refresh updates data and drops invalid/dead records.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

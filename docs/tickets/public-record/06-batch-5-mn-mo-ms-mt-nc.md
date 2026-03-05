# Batch 5 Adapters: MN, MO, MS, MT, NC

## Summary

Implement official-source discovery adapters for:

- Minnesota (`MN`)
- Missouri (`MO`)
- Mississippi (`MS`)
- Montana (`MT`)
- North Carolina (`NC`)

## Acceptance Criteria

- Adapter logic implemented for all states in this batch.
- Every discovered listing passes strict source policy checks.
- Dataset changes include valid additions and removals of dead records when applicable.
- Tests added for each state adapter path.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

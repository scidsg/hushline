# Batch 9 Adapters: VA, VT, WI, WV, WY

## Summary

Implement official-source discovery adapters for:

- Virginia (`VA`)
- Vermont (`VT`)
- Wisconsin (`WI`)
- West Virginia (`WV`)
- Wyoming (`WY`)

## Acceptance Criteria

- All final batch adapters are implemented.
- Strict source policy checks pass for all new rows.
- Dataset refresh produces only valid official-source listings.
- This batch closes 50-state U.S. adapter implementation scope.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

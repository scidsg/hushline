# Remove Temporary Legacy Public Record Listings

## Summary

Remove the temporary legacy listings path once U.S. strict official-source coverage is complete.

## Context

Legacy listings are intentionally temporary to preserve larger directory coverage while the strict 50-state rollout is still in progress.

## Scope

- Remove loading of `public_record_law_firms_legacy.json`.
- Remove legacy-specific directory rendering sections and search grouping.
- Keep only strict official-source public-record listings.
- Delete temporary legacy data file and any legacy-only tests.

## Acceptance Criteria

- Directory public-record tab shows only strict listings.
- Tab count reflects strict listings only.
- No `legacy_public_record` rows are returned by `/directory/users.json`.
- All tests pass after legacy-path removal.
- Roadmap and docs are updated to reflect cleanup completion.

## Validation

- `make lint`
- `make test`
- `make test-public-record-links`

## Dependency

- U.S. strict 50-state implementation completed and verified.

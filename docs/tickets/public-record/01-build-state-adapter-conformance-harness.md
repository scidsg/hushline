# Build State Adapter Conformance Harness

## Summary

Create reusable test coverage that every state adapter must pass before merge.

## Why

Adapter work is scaling to all 50 states; we need a single conformance contract so quality stays consistent and review is fast.

## Scope

- Add shared test helpers/assertions for official-source adapter outputs.
- Apply harness to currently implemented states and all new state adapters.

## Acceptance Criteria

- Harness asserts, for each discovered row:
  - `source_label` matches `US_STATE_AUTHORITATIVE_SOURCES[state]`
  - `source_url` host is allowed for that state
  - `source_url` is record-specific (not the state generic source page)
  - no synthetic listing markers in query/fragment
  - `source_url` does not match `website`
  - no Chambers/private source labels or URLs
- Harness includes duplicate protection checks (`id`, `slug`, normalized name collisions).
- Harness includes add/skip-existing behavior checks.
- Existing implemented states (`CA`, `IL`, `OH`, `TN`, `WA`) pass the harness.

## Validation

- `make lint`
- `make test`

## Dependencies

- None; this should be completed before or in parallel with batch tickets.

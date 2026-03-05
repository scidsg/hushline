# EPIC: Public Record Directory 50-State Official Provenance Rollout

## Summary

Build a strict, ever-growing U.S. public-record attorney dataset across all 50 states using only official sources with per-record provenance links.

## Context

- We are currently at 27 strict listings across 5 states.
- The dataset must prioritize data integrity over volume.
- `source_url` must be the exact record we used, not a generic page.

## Scope

- Implement and ship state adapters for all remaining U.S. states.
- Keep automated refresh behavior that adds new valid records and removes dead/invalid records.
- Enforce strict source policy continuously.

## Acceptance Criteria

- All 50 states have implemented adapter logic or documented state-specific blocker evidence with tracked follow-up.
- Every U.S. listing includes:
  - official `source_label` matching state policy
  - exact per-record official `source_url`
  - `source_url != website`
- No Chambers/private ranking URLs are accepted as authoritative sources.
- Refresh process can both add and remove records safely.
- CI/workflow behavior remains green when correction PRs are opened due to link/data drift.

## Definition of Done (for all child tickets)

- `make lint` passes
- `make test` passes
- `make test-public-record-links` passes
- Dataset refresh done and committed when ticket changes data

## Dependencies

- Child tickets in this folder.

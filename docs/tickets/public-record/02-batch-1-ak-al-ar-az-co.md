# Batch 1 Adapters: AK, AL, AR, AZ, CO

## Summary

Implement official-source discovery adapters for:

- Alaska (`AK`)
- Alabama (`AL`)
- Arkansas (`AR`)
- Arizona (`AZ`)
- Colorado (`CO`)

## Scope

- Implement state-specific adapter logic in `hushline/public_record_refresh.py`.
- Add/extend tests in `tests/test_public_record_refresh.py` and related strict-policy tests.
- Refresh dataset and commit resulting changes.

## Acceptance Criteria

- Each state in this batch has an implemented adapter (not no-op).
- Each adapter emits only strict records with exact per-record official `source_url`.
- Records use state-appropriate `source_label` and allowed official domains.
- Generic source pages are rejected.
- Existing invalid/dead records for these states are removed during refresh.
- Net strict dataset count increases unless a state has documented official-source blockers.
- Any blocker is documented in the roadmap with concrete evidence and follow-up.

## Validation

- `make refresh-public-record-listings REFRESH_PUBLIC_RECORD_ARGS='--discover-official-us-state-firms --summary-output /tmp/pr-refresh.md --drop-failing-records'`
- `make lint`
- `make test`
- `make test-public-record-links`

## Dependencies

- `01-build-state-adapter-conformance-harness.md`

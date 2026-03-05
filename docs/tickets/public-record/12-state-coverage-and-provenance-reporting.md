# State Coverage and Provenance Reporting

## Summary

Add machine-readable and human-readable reporting for U.S. state coverage and provenance quality on each refresh run.

## Scope

- Emit structured refresh artifact (JSON/Markdown) with:
  - total strict listings
  - covered states vs missing states
  - additions/removals in run
  - per-state counts
  - validation/link failure summary
- Surface report in workflow artifacts and PR body/comments.
- Keep roadmap status synchronized with actual adapter/data state.

## Acceptance Criteria

- Every refresh run produces report artifact(s) with the fields above.
- Correction PRs include report summary.
- State coverage data is consistent with dataset content.
- Roadmap baseline/status is updated whenever coverage changes.

## Validation

- Trigger refresh run and verify artifact presence/content.
- Verify PR summary mirrors artifact values.
- Confirm no schema drift between report and parser/consumer code.

## Dependencies

- Refresh workflow and refresh script.

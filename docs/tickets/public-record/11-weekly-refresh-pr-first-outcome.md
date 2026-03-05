# Weekly Refresh Automation: PR-First Outcome for Data Corrections

## Summary

Ensure scheduled/manual refreshes open correction PRs when they detect dataset drift (new valid records or dead/invalid records), without treating that as workflow failure.

## Context

Policy intent: if a cron run detects broken links or stale rows, that is a successful detection event when it creates a correction PR.

## Scope

- Align workflow status semantics with correction-PR behavior.
- Keep weekly schedule and manual trigger support.
- Preserve local/manual make target parity with workflow behavior.

## Acceptance Criteria

- Workflow opens a PR when refresh changes data.
- Workflow opens a PR for dead-link/data-removal corrections.
- Workflow does not fail merely because corrections were found.
- Workflow fails only on execution/runtime failures (script errors, infra failures, validation failures before PR creation).
- PR body includes summary: added rows, removed rows, states covered, and link-check results.

## Validation

- Dry run or test branch run demonstrates:
  - no-change path: workflow exits cleanly with no PR
  - change path: workflow opens/updates PR and job is green
  - runtime-error path: workflow fails red

## Dependencies

- Existing refresh target(s) and GH Action for public record refresh.

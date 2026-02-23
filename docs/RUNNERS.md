# Runner Automation

This repository has two automation runners:

- `scripts/codex_daily_issue_runner.sh`
- `scripts/codex_coverage_gap_runner.sh`

Both runners are designed to:

- operate on a clean checkout
- enforce local validation before opening a PR
- run with signed commits by default
- open a PR as the end state when changes are made
- avoid wasting compute by allowing only one open bot PR at a time

## Session Ruleset

Both runners instruct Codex to follow repository policy from the root ruleset file first:

- `AGENTS.md` at repo root

Then Codex must follow any deeper `AGENTS.md` files that apply to changed paths.

## Architecture Diagram

Runtime infrastructure is documented in `docs/ARCHITECTURE.md`.

## One-Bot-PR Gate

Both scripts check open PRs before doing any heavy work.

- Default bot login: `hushline-dev`
- Configurable via: `HUSHLINE_BOT_LOGIN`
- Behavior: if there is any open PR authored by that bot login, the runner exits early.

This prevents repeated rebuilds and duplicate automation work while an existing bot PR is still pending.

## Cron Schedule

Current schedule target:

- Coverage runner: `00:00` (midnight)
- Daily issue runner: `02:00`

Because both runners enforce the one-bot-PR gate, the 02:00 daily run proceeds only when the 00:00 coverage run did not open a bot PR.

Example cron entries:

```cron
0 0 * * * /Users/scidsg/.codex/bin/codex_coverage_cron.sh >> /Users/scidsg/.codex/logs/codex-coverage.log 2>&1
0 2 * * * /Users/scidsg/.codex/bin/codex_daily_cron.sh >> /Users/scidsg/.codex/logs/codex-daily.log 2>&1
```

## Shared Execution Pattern

Both runners perform these core steps (with runner-specific logic in the middle):

1. Verify required commands are present.
2. Verify GitHub CLI authentication.
3. Exit early if bot PR gate is active.
4. Ensure local working tree is clean.
5. Sync with `main`.
6. Start with destructive Docker rebuild:
   - `docker compose down -v --remove-orphans`
   - `docker compose build app`
7. Run runner-specific Codex task.
8. Run required local checks.
9. Create signed commit (unless explicitly disabled by env var).
10. Push branch and open PR.

## Daily Issue Runner

Script: `scripts/codex_daily_issue_runner.sh`

### Purpose

Pick one open issue labeled for automation, implement it with Codex, run required checks, and open a PR.

### CLI flags

- `--dry-run`: selects and reports issue/branch without changing code
- `--issue <number>`: force a specific issue

### Issue selection behavior

If `--issue` is not provided:

- Only issues with label `agent-eligible` are considered (default behavior).
- Dependabot-authored issues are prioritized first within eligible issues.
- If no eligible issue is found, the run exits without changes.

If `--issue <number>` is provided:

- The issue must still include the required eligibility label when enforcement is enabled.
- If the required label is missing, the run is blocked.

### Security hardening

The daily issue runner includes explicit safeguards against prompt injection and unsafe automation:

- Explicit allowlist gate:
  - Only issues labeled `agent-eligible` are processed by default.
  - Forced runs (`--issue`) are also blocked if the label is missing, unless enforcement is explicitly disabled.
- Untrusted issue-content boundary:
  - The runner prompt wraps issue body text between `---BEGIN UNTRUSTED ISSUE BODY---` and `---END UNTRUSTED ISSUE BODY---`.
  - This makes it explicit that issue body text is treated as untrusted data, not instruction authority.
- Instruction hierarchy lock:
  - The prompt explicitly requires compliance with `AGENTS.md` and applicable deeper rulesets.
  - The prompt explicitly forbids following issue-body instructions that conflict with system/developer constraints or repository policy.
- Execution safety:
  - The prompt explicitly forbids executing arbitrary content from issue text.
  - If instructions are unsafe or unclear, the runner requires stopping and reporting instead of risky changes.

These controls are intentionally conservative. They reduce the chance that user-authored issue content can override policy or trigger unsafe behavior.

### Main checks (when `HUSHLINE_DAILY_RUN_CHECKS=1`)

- `make lint`
- `make test PYTEST_ADDOPTS="--skip-local-only"`
- security-critical test subsets (E2EE/privacy and GDPR/CCPA)
- coverage threshold command with `--cov-fail-under`
- Python dependency audit (`pip-audit`)
- Node runtime audit (`npm audit --omit=dev --package-lock-only`)
- full Node audit (`npm audit --package-lock-only`)

### Key environment variables

- `HUSHLINE_REPO_SLUG` (default `scidsg/hushline`)
- `HUSHLINE_BASE_BRANCH` (default `main`)
- `HUSHLINE_DAILY_BRANCH_PREFIX` (default `codex/daily-issue-`)
- `HUSHLINE_DAILY_RUN_CHECKS` (default `1`)
- `HUSHLINE_DAILY_NO_GPG_SIGN` (default `0`)
- `HUSHLINE_DAILY_MIN_COVERAGE` (default `100`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)
- `HUSHLINE_DAILY_ELIGIBLE_LABEL` (default `agent-eligible`)
- `HUSHLINE_DAILY_REQUIRE_ELIGIBLE_LABEL` (default `1`)

## Coverage Gap Runner

Script: `scripts/codex_coverage_gap_runner.sh`

### Purpose

Measure current test coverage, ask Codex to close gaps, run checks, and open a PR if needed.

### CLI flags

- `--dry-run`: report coverage gap and planned branch without changing code
- `--force`: run even if current coverage already meets target

### Behavior

- Measures coverage first.
- If current coverage already meets target and `--force` is not set, exits without changes.
- Otherwise generates a prompt including uncovered coverage rows.
- Runs Codex to make targeted test-oriented improvements.
- Runs local checks, commits, and opens PR.

### Main checks (when `HUSHLINE_COVERAGE_RUN_CHECKS=1`)

- `make lint`
- `make test PYTEST_ADDOPTS="--skip-local-only"`
- coverage threshold command with `--cov-fail-under`

### Key environment variables

- `HUSHLINE_REPO_SLUG` (default `scidsg/hushline`)
- `HUSHLINE_BASE_BRANCH` (default `main`)
- `HUSHLINE_COVERAGE_BRANCH_PREFIX` (default `codex/coverage-gap-`)
- `HUSHLINE_COVERAGE_RUN_CHECKS` (default `1`)
- `HUSHLINE_COVERAGE_NO_GPG_SIGN` (default `0`)
- `HUSHLINE_TARGET_COVERAGE` (default `100`)
- `HUSHLINE_COVERAGE_REPORT_LINES` (default `80`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)

## Signing and Identity

Both scripts commit with signing enabled by default.

- Daily runner opt-out: `HUSHLINE_DAILY_NO_GPG_SIGN=1`
- Coverage runner opt-out: `HUSHLINE_COVERAGE_NO_GPG_SIGN=1`

For GitHub "Verified" status, the signing key must be registered as a signing key on the account used as commit author.

## Operational Notes

- These runners are intentionally conservative and may skip work when conditions are not safe or useful.
- The one-bot-PR gate is intentional and is the primary control for compute and PR churn.
- If you need parallel bot PRs, disable or override this behavior explicitly (not recommended by default).

## Agentic Flow (ASCII)

Agentic surface area (small and bounded): code-change runners only.

```text
   00:00 cron                                  02:00 cron
+-----------------------------+       +-----------------------------+
| codex_coverage_gap_runner   |       | codex_daily_issue_runner    |
+---------------+-------------+       +---------------+-------------+
                |                                     |
                +------------------+------------------+
                                   |
                                   v
                     +-----------------------------+
                     | Gate: One-Bot-PR           |
                     | (HUSHLINE_BOT_LOGIN)       |
                     +--------------+--------------+
                                    |
                         no open bot PR only
                                    |
                                    v
                     +-----------------------------+
                     | Eligibility Gate            |
                     | (daily only: agent-eligible)|
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Prep: Clean/sync/rebuild    |
                     | - git sync with main        |
                     | - docker compose down -v    |
                     | - docker compose build app  |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Execute: Codex task         |
                     | - coverage gap OR issue     |
                     | - follows AGENTS.md         |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Validate: Required checks   |
                     | - make lint                 |
                     | - make test                 |
                     | - runner-specific audits    |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Sign: Signed commit         |
                     | author: hushline-dev bot    |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | Push: Push branch + open PR |
                     +--------------+--------------+
                                    |
                                    v
                     +-----------------------------+
                     | HUMAN HANDOFF: PR / CI      |
                     +-----------------------------+
                                    |
                                    v
                      /-----------------------------/
                     /   Human review + merge      /
                    /_____________________________/
```

Boundary summary:

- Agentic: runner execution from gate through push/open PR.
- Human-only: release tagging, infrastructure changes, Terraform applies, and merge/deploy decisions.

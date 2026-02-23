# Runner Automation

This repository has two automation runner scripts:

- `scripts/codex_daily_issue_runner.sh`
- `scripts/codex_coverage_gap_runner.sh`

Scheduling now happens through a single machine-local entrypoint:

- `/Users/scidsg/.codex/bin/agent-runner`

`agent-runner` executes:

1. `/Users/scidsg/.codex/bin/codex_coverage_cron.sh`
2. `/Users/scidsg/.codex/bin/codex_daily_cron.sh` (only if coverage runner exits cleanly)

Both runners are designed to:

- operate on a clean checkout
- run a preflight machine healthcheck before doing work
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

## Scheduler

- Label: `org.scidsg.agent-runner`
- Plist: `/Users/scidsg/.codex/launchd/org.scidsg.agent-runner.plist`
- Entrypoint: `/Users/scidsg/.codex/bin/agent-runner`
- Schedule: `00:00` local time (daily)
- Log file: `/Users/scidsg/.codex/logs/agent-runner.log`

LaunchAgents are a macOS mechanism. Linux/Windows require a different scheduler.

## Local Config Files

Machine-local scheduler/wrapper files (not committed in this repo):

- `/Users/scidsg/.codex/launchd/org.scidsg.agent-runner.plist`
- `/Users/scidsg/.codex/bin/agent-runner`
- `/Users/scidsg/.codex/bin/codex_coverage_cron.sh`
- `/Users/scidsg/.codex/bin/codex_daily_cron.sh`

Repository scripts (committed):

- `scripts/codex_coverage_gap_runner.sh`
- `scripts/codex_daily_issue_runner.sh`
- `scripts/healthcheck.sh`

## Shared Execution Pattern

Both runners perform these core steps (with runner-specific logic in the middle):

1. Verify required commands are present.
2. Run preflight healthcheck (`scripts/healthcheck.sh`).
3. Verify GitHub CLI authentication.
4. Exit early if bot PR gate is active.
5. Ensure local working tree is clean.
6. Sync with `main`.
7. Run runner-specific Codex task.
8. Run destructive Docker rebuild only when needed by runner strategy:
   - `docker compose down -v --remove-orphans`
   - `docker compose build app`
9. Run required local checks.
   - If checks fail, rerun Codex with failure output and retry checks (up to a configured attempt limit).
10. Create signed commit (unless explicitly disabled by env var).
11. Push branch and open PR.

## Preflight Healthcheck

Script: `scripts/healthcheck.sh`

Both runners call this script before they do any issue/coverage work.

Checks currently include:

- plaintext token file is absent (default path `~/.config/hushline/gh_token`)
- Docker daemon is reachable
- free disk space is above threshold (default 8 GB)
- firewall enabled
- firewall stealth mode on (optional; non-blocking by default)
- Wake-on-LAN (`womp`) disabled

If any check fails, the runner exits before expensive rebuild/test work begins.

Note:

- In the machine-local wrappers, `HUSHLINE_HEALTHCHECK_REQUIRE_KEYCHAIN_TOKEN` is set to `0`.
- Authentication is injected before runner execution via `gh auth token` in wrapper scripts.

## Daily Issue Runner

Script: `scripts/codex_daily_issue_runner.sh`

### Purpose

Pick one open issue labeled for automation, implement it with Codex, run required checks, and open a PR.

The prompt directs Codex to make only code/test changes. The runner executes invariant checks and, on failure, asks Codex for a focused fix before retrying checks.

### CLI flags

- `--dry-run`: selects and reports issue/branch without changing code
- `--issue <number>`: force a specific issue

### Issue selection behavior

If `--issue` is not provided:

- Only issues with label `agent-eligible` are considered (default behavior).
- Eligible issues are sorted by lowest-risk first using label signals (`risk:low`, `low-risk`, docs/tests/chore/dependencies style labels).
- Within the same risk level, Dependabot-authored issues are prioritized first.
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
- `HUSHLINE_ENFORCE_BOT_GIT_IDENTITY` (default `1`)
- `HUSHLINE_BOT_GIT_NAME` (default `hushline-dev`)
- `HUSHLINE_BOT_GIT_EMAIL` (default `git-dev@scidsg.org`)
- `HUSHLINE_BOT_GIT_GPG_FORMAT` (default `ssh`)
- `HUSHLINE_BOT_GIT_SIGNING_KEY` (default empty; optional explicit signing key path)
- `HUSHLINE_DAILY_ELIGIBLE_LABEL` (default `agent-eligible`)
- `HUSHLINE_DAILY_REQUIRE_ELIGIBLE_LABEL` (default `1`)
- `HUSHLINE_DAILY_REBUILD_STRATEGY` (default `on-change`, options: `always`, `on-change`, `never`)
- `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS` (default `0`, meaning unlimited retries)

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
- Prompts Codex for code/test changes only; runner executes checks itself.
- Rebuild timing is strategy-controlled and defaults to rebuilding at runner start (`always`).
- Runs Codex to make targeted test-oriented improvements.
- If checks fail, reruns Codex with failure output and retries checks up to the configured attempt limit.
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
- `HUSHLINE_COVERAGE_REBUILD_STRATEGY` (default `always`, options: `always`, `on-gap`, `never`)
- `HUSHLINE_COVERAGE_MAX_FIX_ATTEMPTS` (default `0`, meaning unlimited retries)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)
- `HUSHLINE_ENFORCE_BOT_GIT_IDENTITY` (default `1`)
- `HUSHLINE_BOT_GIT_NAME` (default `hushline-dev`)
- `HUSHLINE_BOT_GIT_EMAIL` (default `git-dev@scidsg.org`)
- `HUSHLINE_BOT_GIT_GPG_FORMAT` (default `ssh`)
- `HUSHLINE_BOT_GIT_SIGNING_KEY` (default empty; optional explicit signing key path)

## Signing and Identity

Both scripts commit with signing enabled by default.

Both scripts also set local repository git identity on each run (unless disabled) so automated commits are consistently authored by the bot account.

- Daily runner opt-out: `HUSHLINE_DAILY_NO_GPG_SIGN=1`
- Coverage runner opt-out: `HUSHLINE_COVERAGE_NO_GPG_SIGN=1`
- Identity enforcement opt-out: `HUSHLINE_ENFORCE_BOT_GIT_IDENTITY=0`

For GitHub "Verified" status, the signing key must be registered as a signing key on the account used as commit author.

## Healthcheck Environment Variables

- `HUSHLINE_HEALTHCHECK_SCRIPT` (default `scripts/healthcheck.sh`)
- `HUSHLINE_GH_ACCOUNT` (default `hushline-dev`)
- `HUSHLINE_GH_TOKEN_FILE` (default `/Users/scidsg/.config/hushline/gh_token`)
- `HUSHLINE_HEALTHCHECK_MIN_FREE_GB` (default `8`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_KEYCHAIN_TOKEN` (default `1`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_DOCKER` (default `1`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_GH` (default `1`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_FIREWALL` (default `1`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_STEALTH` (default `0`)
- `HUSHLINE_HEALTHCHECK_REQUIRE_WOMP_DISABLED` (default `1`)
- `HUSHLINE_COVERAGE_RUN_HEALTHCHECK` (default `1`)
- `HUSHLINE_DAILY_RUN_HEALTHCHECK` (default `1`)

## Operational Notes

- These runners are intentionally conservative and may skip work when conditions are not safe or useful.
- The one-bot-PR gate is intentional and is the primary control for compute and PR churn.
- If you need parallel bot PRs, disable or override this behavior explicitly (not recommended by default).

## Agentic Flow

Agentic surface area (small and bounded): code-change runners only.

```text
+-----------------------------+
| agent-runner                |
+--------------+--------------+
               |
               v
+-----------------------------+
| codex_coverage_gap_runner   |
+--------------+--------------+
               |
               v
+-----------------------------+
| codex_daily_issue_runner    |
| (coverage step must pass)   |
+--------------+--------------+
               |
               v
+-----------------------------+
| Gate: One-Bot-PR           |
| (HUSHLINE_BOT_LOGIN)       |
+--------------+--------------+
               |
               v
+-----------------------------+
| Eligibility Gate            |
| (daily only: agent-eligible)|
+--------------+--------------+
               |
               v
+-----------------------------+
| Prep: Clean/sync            |
| - git sync with main        |
| - rebuild is strategy-based |
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

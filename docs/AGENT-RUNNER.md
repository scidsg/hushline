# Agent Runners

This document tracks the current state of the repo-managed agent automation used around Hush Line.

## Repo-Managed Agent State

| Script                                                | Role                           | Current State                                                 | PR / Output Surface                                               |
| ----------------------------------------------------- | ------------------------------ | ------------------------------------------------------------- | ----------------------------------------------------------------- |
| `scripts/agent_daily_issue_runner.sh`                 | GitHub issue implementation    | Paused on this host; configured for 10-minute launchd cadence | issue-specific branches and PRs                                   |
| `scripts/weekly_hushline_code_agent_report_runner.py` | Weekly local agent reporting   | Active, local Mail.app delivery and local report persistence  | email to `glenn@hushline.app`; local `logs/weekly-agent-reports/` |
| `scripts/agent_issue_bootstrap.sh`                    | Local runtime/bootstrap helper | Active, manual helper used by issue and local workflows       | local Docker/bootstrap only                                       |

The repository does not currently include runner scripts for the social or docs launch agents listed below. Those host jobs exist outside this repository and should be documented here only as installed host context, not as repo-managed automation.

## Installed Host Jobs

| Label                                             | Scope                                | Schedule                                  | Source                                                  |
| ------------------------------------------------- | ------------------------------------ | ----------------------------------------- | ------------------------------------------------------- |
| org.scidsg.hushline-code-agent                    | Hush Line issue runner               | Disabled; configured for every 10 minutes | org.scidsg.hushline-code-agent.plist                    |
| com.hushline.social.daily-planner                 | Social planner                       | Mon-Fri at 6:00 AM                        | com.hushline.social.daily-planner.plist                 |
| com.hushline.social.linkedin.daily                | Social LinkedIn daily                | Mon-Fri at 6:10 AM                        | com.hushline.social.linkedin.daily.plist                |
| com.hushline.weekly-agent-report                  | Weekly local agent report            | Sunday at 10:30 PM                        | com.hushline.weekly-agent-report.plist                  |
| com.hushline.social.verified-user.weekly          | Social verified-user weekly          | Monday at 12:00 PM                        | com.hushline.social.verified-user.weekly.plist          |
| com.hushline.social.linkedin.verified-user.weekly | Social verified-user LinkedIn weekly | Monday at 12:10 PM                        | com.hushline.social.linkedin.verified-user.weekly.plist |
| com.hushline.docs.weekly-article                  | Docs weekly article                  | Wednesday at 10:00 AM                     | com.hushline.docs.weekly-article.plist                  |

## Daily Issue Runner

Script: `scripts/agent_daily_issue_runner.sh`

This runner runs directly in the local repo and performs a narrow local gate before opening a PR.

## Operational Contract

The issue runner has one job: turn one assigned GitHub issue into one reviewed pull request.

1. Pull the latest base branch after an issue is selected and cheap GitHub guards pass.
2. Select exactly one assigned issue from the configured project queue, or the issue passed with `--issue`.
3. Make the smallest safe code, test, or documentation changes needed for that issue.
4. Before opening or updating a PR, run `make lint` and `make test`; if either fails, repair the failure and rerun the checks.
5. Open or update the PR only when there are meaningful non-log changes and local validation is clean.
6. Poll the open PR for actionable comments, review threads, change requests, and failing checks.
7. Address and resolve actionable feedback, push the PR update, and continue polling until the PR is closed.

Every queued issue is assumed to require a real change. Once the runner claims an issue, the only successful terminal outcome is a clean, usable PR. If an attempt does not complete a validated implementation, the issue stays claimed as `In Progress`; the next runner pass must resume that same assigned issue instead of selecting new work, returning it to the eligible queue, opening a diagnostic PR, or moving it to `Ready for Review`.

## Execution Flow

1. Parse arguments (`--issue` optional) and resolve runtime configuration.
2. Acquire a local runner lock and exit without doing any repository or Docker work if another Hush Line code-agent run is active.
3. Check Codex `/status` rate-limit data before repository, GitHub, or Docker work. If the 300-minute primary window has less than the configured minimum remaining quota, wait until after its reset time and re-check before proceeding.
4. Change into the repo (`$HOME/hushline` by default).
5. Hold the runner lock through all repository cleanup, including exit-time checkout/reset/clean work, so a launchd overlap cannot start a second issue while the prior run is still unwinding.
6. Normalize the local agent-only checkout by discarding local worktree changes and switching to the base branch.
7. Resume monitoring any open bot-authored issue PR whose head branch matches the daily issue branch pattern before selecting new issue work. This makes PR polling restart-resilient after launchd unloads, crashes, or reboots.
8. Check cheap GitHub exit conditions before any new-work queue lookup or network sync/Docker work:
   - exit if any open human-authored PR exists
9. Select issue target before any network sync or Docker work:
   - resume the top open issue already in project status `In Progress`, otherwise
   - Use `--issue <n>` when provided (must still be open), otherwise
   - select the top open issue from project `Hush Line Roadmap`, column `Agent Eligible`.
10. Check remaining cheap GitHub exit conditions before any network sync or Docker work:

- for non-epic issues, exit if any other open PR exists from `hushline-dev`
- for child issues with a GitHub parent epic, allow the long-lived epic PR (head branch `codex/epic-<epic>`) and the current child issue PR (head branch `codex/daily-issue-<issue>`)
- for child issues with a GitHub parent epic, exit only if there are unrelated open bot PRs outside those allowed heads

11. Hard-refresh local state only after an issue is selected and skip guards pass:

- `git fetch origin`
- `git checkout main`
- `git reset --hard origin/main`
- `git clean -fd`

12. Move the selected issue into project status `In Progress`.
13. Configure bot git identity and signed commit settings.
14. Reset local Docker/runtime state:

- `docker compose down -v --remove-orphans`
- Remove all Docker containers (`docker rm -f $(docker ps -aq)`, when any exist)
- Kill processes listening on runner ports (`4566 4571 5432 8080` by default)

15. Start and seed stack:

- `docker compose up -d --build`
- `docker compose run --rm dev_data`
- retry the bootstrap sequence when Docker image pulls fail with transient registry/network errors (defaults: `3` attempts, `10`s delay via `HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS` and `HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS`)

16. Create/update work branch:

- regular issues use `codex/daily-issue-<issue_number>` by default
- child issues with a parent epic still use `codex/daily-issue-<issue_number>` as the work branch
- child issues with a parent epic use `codex/epic-<epic_issue_number>` as the PR base branch
- if the epic base branch does not exist yet, create and push it from `main` before starting the child branch
- if the child issue branch already has an open PR, update that child PR instead of opening a duplicate

17. Run a bounded Codex issue loop until repository changes exist (max attempts configurable via `HUSHLINE_DAILY_MAX_ISSUE_ATTEMPTS`, default `10`).
    - The issue/fix prompts tell Codex to avoid local container-backed make validation by default, and to defer validation entirely to the runner when schema-affecting files are touched (`hushline/model/`, `migrations/`, `scripts/dev_data.py`, `scripts/dev_migrations.py`).
    - The fix prompt includes the current branch diff summary, the prior Codex summary, and an extracted failure signature so Codex can repair the current implementation instead of repeating a narrow patch against the same failing symptom.
    - Raw failed check output is intentionally withheld from Codex prompts because local check logs may contain sensitive operational data.
    - Codex transcript output is captured in a temporary file for the duration of the run and is excluded from the persisted runner log; only the final Codex summary is written into the run log.
    - Each Codex attempt logs prompt size and pre/post worktree snapshots so clean-tree no-op runs are visible in the runner log.
18. Run required checks in a bounded self-heal loop (max attempts configurable via `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS`, default `8`):
    - Before lint/test validation, if the working tree includes schema-affecting changes (`hushline/model/`, `migrations/`, `scripts/dev_data.py`, `scripts/dev_migrations.py`), rebuild the local runtime and reseed dev data so the live stack matches the current code.
    - `make lint`
    - `make test` (full suite)
    - The runner stops at the first failing gate, hands that failure back to Codex, and reruns from `make lint` on the next self-heal attempt.
    - Lint failures only run deterministic `make fix` self-heal when the failure looks auto-fixable (for example Ruff formatting/check or Prettier); non-auto-fixable lint failures go straight back to Codex.
    - Runtime-dependent tests self-heal by restarting the local stack and reseeding dev data, then retrying once.
    - The broader CI workflow matrix still runs on the PR after branch push; the runner no longer tries to mirror that entire matrix locally.
19. Persist run log to `docs/agent-logs/run-<timestamp>-issue-<n>.txt`.
    - After each persist, prune older runner logs and keep only the newest `10` by default.
    - Persisted logs are sanitized before commit to remove developer filesystem paths, emails, and Codex session metadata.
20. Commit, push branch, and open/update PR:
    - first push uses a normal push when remote branch is absent
    - existing remote branch uses `--force-with-lease` with one stale-info recovery retry.
    - child issues under a parent epic open/update a child PR whose base branch is the shared epic branch
    - the long-lived epic PR, when present, remains the only PR that targets `main`
21. Move the selected issue into project status `Ready for Review` once the PR exists.
22. After the PR exists and before feedback polling starts, parse the latest line-specific `make test` coverage snapshot and open one follow-up issue for any files with missed statements. The issue must include the exact missing line ranges, explicit 100% / zero-miss acceptance criteria, and instructions that the follow-up PR is not complete if it would create another coverage-gap issue. Add that issue to the `Hush Line Roadmap` project in the `Agent Eligible` status.
23. For child PRs targeting an epic branch, record `Linked issue: #<n>` in the PR body instead of relying on GitHub's default-branch-only close keywords.
24. A dedicated workflow closes that linked child issue after the child PR is merged into the epic branch.
25. Include runner log path in PR context and use a plain-language narrative lead for broad audiences, followed by the structured PR body sections (`Summary`, `Context`, `Changed Files`, `Validation`, `Manual Testing`).
    - `Validation` lists automated checks run by the runner or CI.
    - `Manual Testing` lists human reviewer steps to exercise the changed feature after the PR opens. It is not a log of actions the LLM or runner performed.
26. Refresh run log after PR creation (including opened PR URL, coverage gap issue URL when created, and post-check steps), commit/push that log update when changed.
27. Poll the open PR until it closes. When the monitor sees human/reviewer feedback (discussion comments, change-request reviews, or unresolved review threads), it invokes Codex on the PR branch immediately, reruns `make lint` and `make test`, commits and pushes any fix, resolves addressed review threads, and resumes polling. When the only actionable item is a failing check, it waits for pending PR checks to settle before invoking Codex so transient in-progress checks do not trigger unnecessary fixes.
28. Return to a clean `main` on normal completion or PR closure.
    - If the run fails after creating branch work, cleanup resets the checkout back to a clean base branch.
    - A new scheduled pass discards local worktree changes and switches back to the base branch before evaluating GitHub queue guards.

## ASCII Workflow (Current)

```text
+---------------------------------+
| Start: agent_daily_issue_runner |
+---------------------------------+
      |
      v
+-------------------------------+
| Parse args (--issue optional) |
+-------------------------------+
      |
      v
+-----------------------------------------------+
| Resolve env/config + start log capture        |
| Log: model + reasoning effort                 |
+-----------------------------------------------+
      |
      v
+-----------------------------------------------+
| Acquire runner lock                           |
| Already active? skip + exit                   |
+-----------------------------------------------+
      |
      v
+--------------------------------------------------+
| Normalize agent-only checkout                 |
| Discard dirty work + switch to base branch    |
+--------------------------------------------------+
      |
      v
+------------------------------------------------+
| Refresh workspace                              |
+------------------------------------------------+
      |
      v
+------------------------------------------------+
| Cheap GitHub guards + issue selection:         |
| human PRs, In Progress, or project queue       |
+------------------------------------------------+
      |
      +-- no issue / blocked by human PR --> [Hourly idle /status if due, then skip]
      |
      v
+-----------------------------------------------+
| Assigned issue exists: check Codex /status    |
| 5h quota below floor? wait, then re-check     |
+-----------------------------------------------+
      |
      v
+----------------------------------------------+
| Resolve parent epic + child/epic branch rules |
+----------------------------------------------+
      |
      v
+----------------------------------------------+
| Mark issue In Progress via project status     |
+----------------------------------------------+
      |
      v
+----------------------------------------------+
| Configure bot git identity                    |
| Docker reset, port cleanup, stack up, seed    |
+----------------------------------------------+
      |
      v
+----------------------------------------------+
| Load issue metadata + checkout work branch   |
| Build initial issue prompt                   |
+----------------------------------------------+
      |
      v
+------------------------------------+
| Issue attempt loop                 |
| Run Codex from prompt              |
+------------------------------------+
      |
      v
+------------------------+
| Any repo changes?      |--no--> [Retry issue attempt]
+------------------------+
      |
      yes
      |
      v
+-----------------------------------------------+
| Fix/self-heal loop                            |
| Run: lint, test                               |
+-----------------------------------------------+
      |
      v
+------------------------+
| Checks pass?           |--no--> [Build fix prompt + run Codex + retry]
+------------------------+
      |
      yes
      |
      v
+------------------------+
| Still has changes?     |--no--> [Rebuild issue prompt + retry issue loop]
+------------------------+
      |
      yes
      |
      v
+----------------------------------------------+
| Persist run log (docs/agent-logs/run-...)    |
| git add/commit/push branch                    |
| Build PR body + create/update PR              |
| Mark issue Ready for Review                   |
| Append PR URL to run log                      |
| Commit/push updated run log if changed        |
+----------------------------------------------+
      |
      v
+----------------------------------------------+
| Cleanup after successful handoff/PR close     |
| Reset failed runs back to clean main          |
+----------------------------------------------+
```

## Required Commands

- `git`
- `gh`
- `codex`
- `docker`
- `make`
- `node`
- `lsof` (optional; used for port cleanup)
- `osascript` and configured macOS Mail.app account `weekly-report@hushline.app` for the weekly agent report runner

## Manual Run

```bash
./scripts/agent_daily_issue_runner.sh
```

## Weekly Agent Report Runner

Script: `scripts/weekly_hushline_code_agent_report_runner.py`

This runner scans the local runner logs monitored on this machine and builds a plain-text `Weekly Agent Report`. It persists a timestamped local copy before sending through the native macOS Mail app. Mail.app delivery uses a bounded AppleScript timeout and sends asynchronously once the message is handed to Mail. If Mail reports its own AppleEvent timeout after that handoff, the runner logs a warning and exits successfully so slow Mail.app network delivery does not fail the LaunchAgent run after the local report has already been written.

Default log files:

- `~/.codex/logs/hushline-code-agent.log`
- `~/tor-code-agent/logs/tor-agent.err.log`
- `../hushline-social/logs/social-daily.log`

Delivery is fixed in code:

- From: `weekly-report@hushline.app`
- To: `glenn@hushline.app`

Additional log files can be supplied with repeated `--log-file` arguments or the colon-separated `HUSHLINE_WEEKLY_AGENT_REPORT_LOG_FILES` environment variable. The runner summarizes completed work, skipped/no-op checks, work/check activity, and attention items without embedding full log transcripts in email.

Persisted report bodies are written to `logs/weekly-agent-reports/weekly-agent-report-<timestamp>.txt` by default. The directory is intentionally ignored by git. The default retention is the newest `12` reports; override it with `--report-retention` or `HUSHLINE_WEEKLY_AGENT_REPORT_RETENTION`. Override the report directory with `--report-output-dir` or `HUSHLINE_WEEKLY_AGENT_REPORT_OUTPUT_DIR`.

Monitor the installed LaunchAgent stdout/stderr logs:

```bash
tail -F /Users/scidsg/hushline-weekly-report-agent/logs/weekly-agent-report.stdout.log /Users/scidsg/hushline-weekly-report-agent/logs/weekly-agent-report.stderr.log
```

Check the installed LaunchAgent state:

```bash
launchctl print gui/$(id -u)/com.hushline.weekly-agent-report
```

Manual dry run:

```bash
./scripts/weekly_hushline_code_agent_report_runner.py --dry-run
```

Send report:

```bash
make weekly-agent-report
```

Optional forced issue:

```bash
./scripts/agent_daily_issue_runner.sh --issue 1389
```

## Machine Setup

Each runner host needs its own signed-commit configuration. The daily runner defaults to SSH signing and resolves the signing key in this order:

1. `HUSHLINE_BOT_GIT_SIGNING_KEY`
2. Existing git config when `gpg.format=ssh` and `user.signingkey` is already set for the checkout
3. `HUSHLINE_BOT_GIT_DEFAULT_SSH_SIGNING_KEY_PATH`, if explicitly set to a local `.pub` file path

Recommended per-host setup:

```bash
git -C /path/to/hushline config gpg.format ssh
git -C /path/to/hushline config user.signingkey "$HOME/.ssh/hushline_bot_signing.pub"
ssh-add "$HOME/.ssh/hushline_bot_signing"
```

Requirements:

- The matching public key must be added to the GitHub bot account as an SSH signing key.
- The matching private key must be available to `ssh-agent` before the runner starts.
- If the machine still has a global GPG signing key from another environment (for example `git config --global user.signingkey 102783C80AF9335A`), do not reuse it with the runner's SSH signing mode.
- On macOS, using `ssh-add --apple-use-keychain` is optional but not required by the runner.

The runner now performs an SSH signing preflight immediately after configuring git identity and fails early with an actionable error if the host is missing the expected key or the key is not loaded into `ssh-agent`.

## Environment Variables

- `HUSHLINE_REPO_DIR` (default the repository checkout containing `scripts/agent_daily_issue_runner.sh`)
- `HUSHLINE_REPO_SLUG` (default `scidsg/hushline`)
- `HUSHLINE_BASE_BRANCH` (default `main`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)
- `HUSHLINE_BOT_GIT_NAME` (default `HUSHLINE_BOT_LOGIN`)
- `HUSHLINE_BOT_GIT_EMAIL` (default `git-dev@scidsg.org`)
- `HUSHLINE_BOT_GIT_GPG_FORMAT` (default `ssh`)
- `HUSHLINE_BOT_GIT_SIGNING_KEY` (optional; when unset the runner reuses existing SSH git signing config if available)
- `HUSHLINE_BOT_GIT_DEFAULT_SSH_SIGNING_KEY_PATH` (optional; no default)
- `HUSHLINE_DAILY_PROJECT_OWNER` (default owner from `HUSHLINE_REPO_SLUG`)
- `HUSHLINE_DAILY_PROJECT_TITLE` (default `Hush Line Roadmap`)
- `HUSHLINE_DAILY_PROJECT_COLUMN` (default `Agent Eligible`)
- `HUSHLINE_DAILY_PROJECT_STATUS_FIELD_NAME` (default `Status`)
- `HUSHLINE_DAILY_PROJECT_STATUS_IN_PROGRESS` (default `In Progress`)
- `HUSHLINE_DAILY_PROJECT_STATUS_READY_FOR_REVIEW` (default `Ready for Review`)
- `HUSHLINE_DAILY_PROJECT_ITEM_LIMIT` (default `200`)
- `HUSHLINE_DAILY_BRANCH_PREFIX` (default `codex/daily-issue-`)
- `HUSHLINE_DAILY_EPIC_BRANCH_PREFIX` (default `codex/epic-`)
- `HUSHLINE_DAILY_KILL_PORTS` (default `4566 4571 5432 8080`)
- `HUSHLINE_DAILY_RUN_LOG_RETENTION` (default `10`)
- `HUSHLINE_DAILY_MAX_ISSUE_ATTEMPTS` (default `10`; positive integer)
- `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS` (default `8`; positive integer)
- `HUSHLINE_DAILY_CODEX_STATUS_CHECK_ENABLED` (default `1`; set `0` to skip Codex `/status` rate-limit checks)
- `HUSHLINE_DAILY_CODEX_STATUS_CHECK_TIMEOUT_SECONDS` (default `15`; positive integer)
- `HUSHLINE_DAILY_CODEX_STATUS_RESET_BUFFER_SECONDS` (default `60`; non-negative integer; extra wait after the 5h window reset before rechecking)
- `HUSHLINE_DAILY_CODEX_STATUS_MIN_REMAINING_PERCENT` (default `25`; integer percentage from `0` to `100`; wait for the 5h window reset when remaining primary quota is below this floor)
- `HUSHLINE_DAILY_CODEX_STATUS_STALE_RESET_RECHECK_SECONDS` (default `600`; positive integer; backoff before rechecking when Codex reports low remaining 5h quota but the reset timestamp has already passed)
- `HUSHLINE_DAILY_CODEX_STATUS_IDLE_CHECK_INTERVAL_SECONDS` (default `3600`; non-negative integer; when no issue work is assigned, perform at most one lightweight Codex `/status` check per interval and do not wait on low quota)
- `HUSHLINE_DAILY_CODEX_STATUS_IDLE_CHECK_STATE_FILE` (default: a hidden sibling file next to `HUSHLINE_DAILY_RUNNER_LOCK_DIR`, for example `/tmp/.hushline-code-agent.lock.codex-status-last-check`; stores the last idle `/status` attempt timestamp without placing files inside the lock directory)
- `HUSHLINE_DAILY_POST_PR_FEEDBACK_DELAY_SECONDS` (default `600`; non-negative integer; set `0` to skip continuous PR feedback monitoring; when enabled, the issue runner keeps the PR branch checked out and polls until the PR closes)
- `HUSHLINE_DAILY_RUNNER_LOCK_DIR` (default `${TMPDIR:-/tmp}/hushline-code-agent.lock`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.5`)
- `HUSHLINE_CODEX_REASONING_EFFORT` (default `high`)
- `HUSHLINE_DAILY_VERBOSE_CODEX_OUTPUT` (default `0`; set `1` to print full Codex transcript output to the live console only, without writing it into persisted runner logs)

## Issue Bootstrap Script

Script: `scripts/agent_issue_bootstrap.sh`

Flow:

1. Ensure Docker is available; on macOS, attempt to start Docker Desktop automatically (`open -a Docker`).
2. Wait for Docker daemon readiness up to `HUSHLINE_DOCKER_START_TIMEOUT_SECONDS` (default `180`).
3. Build and seed required local services:
   - `docker compose build`
   - `docker compose down -v --remove-orphans`
   - `docker compose up -d postgres blob-storage`
   - `docker compose run --rm dev_data`

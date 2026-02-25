# Daily Agent Runner

This runner automates one issue per day from this repository checkout only.

## One-Repo Policy

- The runner uses the current repository (`/Users/scidsg/hushline`) and does not use a second clone.
- Remove any old runner clone (for example `~/hushline-cron`) so only one repo remains.

## Runner Script

- Script: `scripts/agent_daily_issue_runner.sh`

Behavior:

1. Acquire an inter-run lock to prevent overlapping executions.
2. Force-sync to latest `main` on startup:
   - `git fetch origin main --prune`
   - `git reset --hard`
   - `git clean -fdx`
   - `git checkout -B main origin/main`
   - `git reset --hard origin/main`
   - `git clean -fdx`
3. Exit cleanly when any open PR exists authored by `hushline-dev`.
4. Run a coverage pre-check (`pytest --cov hushline --cov-report term-missing -q --skip-local-only`).
5. If coverage is below the configured target (default `100%`), run Codex to close coverage gaps first and open a dedicated coverage-gap PR, then exit.
6. Select one open issue from the `Hush Line Roadmap` project column `Agent Eligible`, in top-down order, only when coverage meets the target.
7. Start each issue attempt with the issue bootstrap sequence:
   - `docker compose down -v --remove-orphans`
   - `docker compose up -d postgres blob-storage`
   - `docker compose run --rm dev_data`
8. Run Codex on the issue.
9. Run required local checks before PR creation:
   - `make lint`
   - `make test`
   - Workflow security checks (`actionlint`, untrusted event interpolation guard)
   - Dependency audits (`pip-audit`, `npm audit --omit=dev`, `npm audit`)
   - Web quality checks (Lighthouse accessibility/performance and W3C HTML/CSS validation)
10. If checks fail, pass failure output back to Codex for a minimal self-heal fix, then re-run checks.
11. Commit with signing enabled and open a PR. The PR body includes required issue-specific manual testing steps (generated from issue metadata and branch diff).
12. After PR creation, switch working copy back to `main`, then run a destructive Docker teardown (`docker compose down -v --remove-orphans`) on exit.

Reliability controls:

- Retry with backoff for transient fetch/GitHub/Codex/push/PR operations.
- Bounded command execution with timeout guards.
- Stale-lock reclamation if a previous process died unexpectedly.

## Local Required Checks

The runner enforces these local checks before opening a PR:

- `make lint`
- `make test`

## Install LaunchAgent (macOS)

Install at 9:00 AM:

```bash
mkdir -p "$HOME/.codex/launchd" "$HOME/.codex/logs"
cat > "$HOME/.codex/launchd/org.scidsg.hushline-agent-runner.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.scidsg.hushline-agent-runner</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/scidsg/hushline/scripts/agent_daily_issue_runner.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/scidsg/hushline</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>/Users/scidsg</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/Users/scidsg/.codex/logs/hushline-agent-runner.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/scidsg/.codex/logs/hushline-agent-runner.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/org.scidsg.hushline-agent-runner" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/.codex/launchd/org.scidsg.hushline-agent-runner.plist"
```

Manual run:

```bash
./scripts/agent_daily_issue_runner.sh
```

Dry run:

```bash
./scripts/agent_daily_issue_runner.sh --dry-run
```

## Environment Variables

- `HUSHLINE_REPO_SLUG` (default `scidsg/hushline`)
- `HUSHLINE_BASE_BRANCH` (default `main`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)
- `HUSHLINE_DAILY_PROJECT_OWNER` (default repo owner from `HUSHLINE_REPO_SLUG`, typically `scidsg`)
- `HUSHLINE_DAILY_PROJECT_TITLE` (default `Hush Line Roadmap`)
- `HUSHLINE_DAILY_PROJECT_COLUMN` (default `Agent Eligible`)
- `HUSHLINE_DAILY_PROJECT_ITEM_LIMIT` (default `200`)
- `HUSHLINE_DAILY_BRANCH_PREFIX` (default `codex/daily-issue-`)
- `HUSHLINE_DAILY_COVERAGE_GATE_ENABLED` (default `1`; set `0` to skip coverage pre-pass)
- `HUSHLINE_DAILY_COVERAGE_TARGET_PERCENT` (default `100`)
- `HUSHLINE_DAILY_COVERAGE_BRANCH_PREFIX` (default `codex/coverage-gap-`)
- `HUSHLINE_DAILY_FULL_SUITE_ENABLED` (default `1`; set `0` to run only lint/test plus coverage gate)
- `HUSHLINE_DAILY_PRETTIER_VERSION` (default `3.3.3`; used for runner tooling bootstrap)
- `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS` (default `0` for unlimited retries)
- `HUSHLINE_RUN_CHECK_TIMEOUT_SECONDS` (default `3600`, `0` disables)
- `HUSHLINE_DAILY_DESTROY_AT_END` (default `1`)
- `HUSHLINE_RETRY_MAX_ATTEMPTS` (default `3`)
- `HUSHLINE_RETRY_BASE_DELAY_SECONDS` (default `5`)
- `HUSHLINE_DAILY_LOCK_DIR` (default `/tmp/hushline-agent-runner.lock`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)

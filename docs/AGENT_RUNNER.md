# Daily Agent Runner

Script: `scripts/agent_daily_issue_runner.sh`

This runner is live-only (no dry-run mode). It is designed for deterministic daily issue execution with a disposable clone, strict PR gates, signed commits, and required local validation.

## Execution Flow

1. Create a unique run log at `docs/agent-run-log/run-<timestamp>-pid<pid>.log` and mirror redacted output to the global log at `~/.codex/logs/hushline-agent-runner.log`.
2. Acquire an inter-run lock to prevent overlapping executions.
3. Exit if any bot-authored PR is open with:
   - `I'm still waiting for my open PR's approval...`
4. Exit if any human-authored PR is open with:
   - `Humans are working, I'll check back tomorrow...`
5. Select the highest-priority open issue from project `Hush Line Roadmap`, column `Agent Eligible`.
6. If no eligible issue exists, exit cleanly.
7. Purge stale temp clone workspace, then clone a fresh repo from `origin/main` into a disposable directory under `/tmp`.
8. Configure bot git identity and commit signing.
9. Run issue bootstrap:
   - `docker compose build`
   - `docker compose down -v --remove-orphans`
   - `docker compose up -d postgres blob-storage`
   - `docker compose run --rm dev_data`
10. Run Codex on the selected issue.
11. Run required local checks before PR creation:
   - `make lint`
   - `make test`
12. If checks fail, feed failures back to Codex and repeat until checks pass.
13. Commit signed changes, push branch, and open PR.
14. On successful PR open:
   - clear global runner log contents (keeps file, truncates to zero)
   - tear down Docker (`docker compose down -v --remove-orphans`)
   - delete disposable clone

## Reliability Controls

- Stale lock reclamation when prior pid is dead.
- Infinite retry loop with backoff for transient operations (GitHub API/auth, Codex invocation, push/PR creation, etc).
- Timeout guards for long-running checks.
- Remote-branch divergence handling for stale bot branches (delete/re-push branch when needed).

## Logging and Redaction

- Per-run logs always write to `docs/agent-run-log/`.
- Global log aggregates runner activity in `~/.codex/logs/hushline-agent-runner.log` (LaunchAgent and manual runs).
- Redaction pipeline masks:
  - user home path segments
  - `session id:` values
  - bearer tokens and common PAT/token formats
  - key/value secret-like assignments (`API_KEY=...`, `TOKEN: ...`, `password=...`, etc)
  - full private key block contents

## Required Commands

The runner requires:

- `git`
- `gh`
- `codex`
- `docker`
- `make`
- `node`
- `rg`
- `shasum`
- `perl`

## LaunchAgent Example (macOS)

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

## Environment Variables

- `HUSHLINE_REPO_SLUG` (default `scidsg/hushline`)
- `HUSHLINE_BASE_BRANCH` (default `main`)
- `HUSHLINE_BOT_LOGIN` (default `hushline-dev`)
- `HUSHLINE_BOT_GIT_NAME` (default `HUSHLINE_BOT_LOGIN`)
- `HUSHLINE_BOT_GIT_EMAIL` (default `git-dev@scidsg.org`)
- `HUSHLINE_BOT_GIT_GPG_FORMAT` (default `ssh`)
- `HUSHLINE_BOT_GIT_SIGNING_KEY` (optional)
- `HUSHLINE_DAILY_PROJECT_OWNER` (default owner from `HUSHLINE_REPO_SLUG`)
- `HUSHLINE_DAILY_PROJECT_TITLE` (default `Hush Line Roadmap`)
- `HUSHLINE_DAILY_PROJECT_COLUMN` (default `Agent Eligible`)
- `HUSHLINE_DAILY_PROJECT_ITEM_LIMIT` (default `200`)
- `HUSHLINE_DAILY_BRANCH_PREFIX` (default `codex/daily-issue-`)
- `HUSHLINE_RUN_CHECK_TIMEOUT_SECONDS` (default `3600`, `0` disables)
- `HUSHLINE_RETRY_BASE_DELAY_SECONDS` (default `5`)
- `HUSHLINE_RETRY_MAX_DELAY_SECONDS` (default `300`)
- `HUSHLINE_DAILY_LOCK_DIR` (default `/tmp/hushline-agent-runner.lock`)
- `HUSHLINE_DAILY_CLONE_ROOT_DIR` (default `/tmp/hushline-agent-runner-clones`)
- `HUSHLINE_DAILY_DESTROY_AT_END` (default `1`)
- `HUSHLINE_DAILY_GLOBAL_LOG_FILE` (default `~/.codex/logs/hushline-agent-runner.log`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)

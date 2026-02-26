# Daily Agent Runner

Script: `scripts/agent_daily_issue_runner.sh`

This runner is intentionally bare-bones. It runs directly in the local repo and keeps only the core gates and checks.

## Execution Flow

1. Change into the repo (`$HOME/hushline` by default).
2. Hard-refresh local state:
   - `git fetch origin`
   - `git checkout main`
   - `git reset --hard origin/main`
   - `git clean -fd`
3. Reset local Docker state:
   - `docker compose down -v --remove-orphans`
   - `docker rm -f $(docker ps -aq)`
   - `docker system prune -af --volumes`
4. Kill processes listening on runner ports (`4566 4571 5432 8080` by default).
5. Start and seed stack:
   - `docker compose up -d --build`
   - `docker compose run --rm dev_data`
6. Exit if any open PR exists from `hushline-dev`.
7. Exit if any open human-authored PR exists.
8. Select the top open issue from project `Hush Line Roadmap`, column `Agent Eligible`.
9. Create/update issue branch `codex/daily-issue-<issue_number>` from `main`.
10. Run Codex on the issue.
11. Run required checks:
   - `make lint`
   - `make test`
   - If the issue has label `test-gap`, require the referenced file in the issue title/body to show `0` misses and `100%` coverage in the test output table.
12. If checks fail, feed failures back to Codex and retry until checks pass.
13. Commit, push branch (`--force-with-lease`), and open PR.
14. Return to `main` on exit.

## Required Commands

- `git`
- `gh`
- `codex`
- `docker`
- `make`
- `node`
- `lsof` (optional; used for port cleanup)

## Manual Run

```bash
./scripts/agent_daily_issue_runner.sh
```

Optional forced issue:

```bash
./scripts/agent_daily_issue_runner.sh --issue 1389
```

## Environment Variables

- `HUSHLINE_REPO_DIR` (default `$HOME/hushline`)
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
- `HUSHLINE_DAILY_KILL_PORTS` (default `4566 4571 5432 8080`)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.3-codex`)

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
13. Persist a run transcript for successful runs to `docs/agent-logs/run-<timestamp>-issue-<n>.txt`.
14. Commit, push branch (`--force-with-lease`), and open PR.
15. Include the runner log path in the PR description.
16. Return to `main` on exit.

## ASCII Workflow (Current)

```text
+-------------------------------+
| Start: agent_daily_issue_runner |
+-------------------------------+
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
+-------------------------------+
| Require commands + repo exists|
+-------------------------------+
               |
               v
+-----------------------------------------------+
| Refresh workspace + configure bot git identity|
| Docker reset, port cleanup, stack up, seed    |
+-----------------------------------------------+
               |
               v
      +---------------------+
      | Open bot PRs > 0 ?  |--yes--> [Skip + Exit]
      +---------------------+
               |
              no
               |
               v
      +------------------------+
      | Open human PRs > 0 ?   |--yes--> [Skip + Exit]
      +------------------------+
               |
              no
               |
               v
+----------------------------------------------+
| Select issue: forced --issue or project queue|
+----------------------------------------------+
               |
               v
      +------------------------+
      | Issue found?           |--no--> [Skip + Exit]
      +------------------------+
               |
              yes
               |
               v
+----------------------------------------------+
| Load issue metadata + checkout issue branch  |
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
      | Run: make lint, make test, test-gap gate      |
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
| Build PR body + create PR                     |
| Append PR URL to run log                      |
| Commit/push updated run log if changed        |
+----------------------------------------------+
               |
               v
+----------------------------------------------+
| Checkout base branch + trap cleanup runs      |
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
- `HUSHLINE_CODEX_REASONING_EFFORT` (default `high`)

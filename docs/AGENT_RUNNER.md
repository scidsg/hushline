# Daily Agent Runner

Script: `scripts/agent_daily_issue_runner.sh`

This runner runs directly in the local repo and now executes the full local CI-equivalent gate set before opening a PR.

## Execution Flow

1. Parse arguments (`--issue` optional) and resolve runtime configuration.
2. Change into the repo (`$HOME/hushline` by default).
3. Hard-refresh local state:
   - `git fetch origin`
   - `git checkout main`
   - `git reset --hard origin/main`
   - `git clean -fd`
4. Configure bot git identity and signed commit settings.
5. Reset local Docker/runtime state:
   - `docker compose down -v --remove-orphans`
   - Remove all Docker containers (`docker rm -f $(docker ps -aq)`, when any exist)
   - `docker system prune -af --volumes`
   - Kill processes listening on runner ports (`4566 4571 5432 8080` by default)
6. Start and seed stack:
   - `docker compose up -d --build`
   - `docker compose run --rm dev_data`
7. Exit if any open PR exists from `hushline-dev`.
8. Exit if any open human-authored PR exists.
9. Select issue target:
   - Use `--issue <n>` when provided (must still be open), otherwise
   - select the top open issue from project `Hush Line Roadmap`, column `Agent Eligible`.
10. Create/update issue branch `codex/daily-issue-<issue_number>` from `main`.
11. Run Codex issue loop until repository changes exist.
12. Run required checks in a self-heal loop:
    - `make lint`
    - `make workflow-security-checks`
    - `make test` (full suite)
    - `make test-ci-alembic`
    - `make test-ccpa-compliance` when CCPA workflow trigger paths change
    - `make test-gdpr-compliance` when GDPR workflow trigger paths change
    - `make test-e2ee-privacy-regressions` when E2EE/privacy workflow trigger paths change
    - `make test-migration-smoke` when migration workflow trigger paths change
    - `make audit-python`
    - `make audit-node-runtime`
    - `make audit-node-full` when Node dependency manifests change (`package.json` / `package-lock.json` / `npm-shrinkwrap.json`)
    - `make w3c-validators`
    - `make lighthouse-accessibility`
    - `make lighthouse-performance` when lighthouse-performance workflow trigger paths change
    - Every executed check gets a local self-heal retry before handing failures to Codex.
    - Lint failures only run deterministic `make fix` self-heal when the failure looks auto-fixable (for example Ruff formatting/check or Prettier); non-auto-fixable lint failures go straight back to Codex.
    - Runtime-dependent checks (tests, W3C, Lighthouse) self-heal by restarting the local stack and reseeding dev data, then retrying once.
    - If the issue has label `test-gap`, require the referenced file in the issue title/body to show `0` misses and `100%` coverage in the test output table.
    - If local dependency audits are blocked by environment/network issues, continue with explicit PR note and require a passing `Dependency Security Audit` workflow before merge.
13. Persist run log to `docs/agent-logs/run-<timestamp>-issue-<n>.txt`.
14. Commit, push branch, and open PR:
    - first push uses a normal push when remote branch is absent
    - existing remote branch uses `--force-with-lease` with one stale-info recovery retry.
15. Include runner log path in PR context and use the narrative + structured PR body sections (`Summary`, `Context`, `Changed Files`, `Validation`).
16. Refresh run log after PR creation (including opened PR URL and post-check steps), commit/push that log update when changed.
17. Return to `main` on exit (explicit checkout + cleanup trap fallback).

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
+--------------------------------+
| Require commands + repo exists |
+--------------------------------+
      |
      v
+------------------------------------------------+
| Refresh workspace + configure bot git identity |
| Docker reset, port cleanup, stack up, seed     |
+------------------------------------------------+
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
+-----------------------------------------------+
| Select issue: forced --issue or project queue |
+-----------------------------------------------+
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
| Run: lint, test, dependency audits, test-gap  |
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
- `HUSHLINE_DAILY_VERBOSE_CODEX_OUTPUT` (default `0`; set `1` to print full Codex transcript output during runs)

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

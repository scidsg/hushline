# Daily Agent Runner

Script: `scripts/agent_daily_issue_runner.sh`

This runner runs directly in the local repo and performs a narrow local gate before opening a PR.

## Execution Flow

1. Parse arguments (`--issue` optional) and resolve runtime configuration.
2. Change into the repo (`$HOME/hushline` by default).
3. Hard-refresh local state:
   - `git fetch origin`
   - `git checkout main`
   - `git reset --hard origin/main`
   - `git clean -fd`
4. Select issue target before bootstrapping runtime:
   - Use `--issue <n>` when provided (must still be open), otherwise
   - select the top open issue from project `Hush Line Roadmap`, column `Agent Eligible`.
5. Check cheap GitHub exit conditions before bootstrapping runtime:
   - exit if any open human-authored PR exists
   - for non-epic issues, exit if any open PR exists from `hushline-dev`
   - for child issues with a GitHub parent epic, allow the long-lived epic PR (head branch `codex/epic-<epic>`) and the current child issue PR (head branch `codex/daily-issue-<issue>`)
   - for child issues with a GitHub parent epic, exit only if there are unrelated open bot PRs outside those allowed heads
6. Move the selected issue into project status `In Progress`.
7. Configure bot git identity and signed commit settings.
8. Reset local Docker/runtime state:
   - `docker compose down -v --remove-orphans`
   - Remove all Docker containers (`docker rm -f $(docker ps -aq)`, when any exist)
   - Kill processes listening on runner ports (`4566 4571 5432 8080` by default)
9. Start and seed stack:
   - `docker compose up -d --build`
   - `docker compose run --rm dev_data`
   - retry the bootstrap sequence when Docker image pulls fail with transient registry/network errors (defaults: `3` attempts, `10`s delay via `HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS` and `HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS`)
10. Create/update work branch:

- regular issues use `codex/daily-issue-<issue_number>` by default
- child issues with a parent epic still use `codex/daily-issue-<issue_number>` as the work branch
- child issues with a parent epic use `codex/epic-<epic_issue_number>` as the PR base branch
- if the epic base branch does not exist yet, create and push it from `main` before starting the child branch
- if the child issue branch already has an open PR, update that child PR instead of opening a duplicate

11. Run a bounded Codex issue loop until repository changes exist (max attempts configurable via `HUSHLINE_DAILY_MAX_ISSUE_ATTEMPTS`, default `10`).
    - The issue/fix prompts tell Codex to avoid local container-backed make validation by default, and to defer validation entirely to the runner when schema-affecting files are touched (`hushline/model/`, `migrations/`, `scripts/dev_data.py`, `scripts/dev_migrations.py`).
    - The fix prompt includes the current branch diff summary, the prior Codex summary, and an extracted failure signature so Codex can repair the current implementation instead of repeating a narrow patch against the same failing symptom.
    - Raw failed check output is intentionally withheld from Codex prompts because local check logs may contain sensitive operational data.
    - Codex transcript output is captured in a temporary file for the duration of the run and is excluded from the persisted runner log; only the final Codex summary is written into the run log.
12. Run required checks in a bounded self-heal loop (max attempts configurable via `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS`, default `8`):
    - Before lint/test validation, if the working tree includes schema-affecting changes (`hushline/model/`, `migrations/`, `scripts/dev_data.py`, `scripts/dev_migrations.py`), rebuild the local runtime and reseed dev data so the live stack matches the current code.
    - `make lint`
    - `make test` (full suite)
    - The runner stops at the first failing gate, hands that failure back to Codex, and reruns from `make lint` on the next self-heal attempt.
    - Lint failures only run deterministic `make fix` self-heal when the failure looks auto-fixable (for example Ruff formatting/check or Prettier); non-auto-fixable lint failures go straight back to Codex.
    - Runtime-dependent tests self-heal by restarting the local stack and reseeding dev data, then retrying once.
    - The broader CI workflow matrix still runs on the PR after branch push; the runner no longer tries to mirror that entire matrix locally.
13. Persist run log to `docs/agent-logs/run-<timestamp>-issue-<n>.txt`.
    - After each persist, prune older runner logs and keep only the newest `10` by default.
    - Persisted logs are sanitized before commit to remove developer filesystem paths, emails, and Codex session metadata.
14. Commit, push branch, and open/update PR:
    - first push uses a normal push when remote branch is absent
    - existing remote branch uses `--force-with-lease` with one stale-info recovery retry.
    - child issues under a parent epic open/update a child PR whose base branch is the shared epic branch
    - the long-lived epic PR, when present, remains the only PR that targets `main`
15. Move the selected issue into project status `Ready for Review` once the PR exists.
16. Include runner log path in PR context and use a plain-language narrative lead for broad audiences, followed by the structured PR body sections (`Summary`, `Context`, `Changed Files`, `Validation`).
17. Refresh run log after PR creation (including opened PR URL and post-check steps), commit/push that log update when changed.
18. Return to `main` on exit (explicit checkout + cleanup trap fallback).
    - Exit cleanup force-resets the repo to `origin/main` and removes untracked files so interrupted runs do not leave bot work on `main`.

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
| Refresh workspace                              |
+------------------------------------------------+
      |
      v
+-----------------------------------------------+
| Select issue: forced --issue or project queue |
+-----------------------------------------------+
      |
+------------------------+
| Open human PRs > 0 ?   |--yes--> [Skip + Exit]
+------------------------+
      |
      no
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
+------------------------+
| Issue found?           |--no--> [Skip + Exit]
+------------------------+
      |
      yes
      |
      v
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
  - used for the shared epic integration branch that child PRs target
- `HUSHLINE_DAILY_KILL_PORTS` (default `4566 4571 5432 8080`)
- `HUSHLINE_DAILY_RUN_LOG_RETENTION` (default `10`)
- `HUSHLINE_DAILY_MAX_ISSUE_ATTEMPTS` (default `10`; positive integer)
- `HUSHLINE_DAILY_MAX_FIX_ATTEMPTS` (default `8`; positive integer)
- `HUSHLINE_CODEX_MODEL` (default `gpt-5.4`)
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

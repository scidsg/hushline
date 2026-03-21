# Dependabot Runner

Script: `scripts/agent_dependabot_pr_runner.sh`

Queue wrapper: `scripts/run_dependabot_pr_queue.sh`

This runner reviews one open Dependabot PR, checks what that dependency update means for the rest of the app, and applies only the follow-up codebase changes needed to support the update.

## Execution Flow

1. Parse arguments (`--pr` optional) and resolve runtime configuration.
2. Change into the repo and hard-refresh local state:
   - `git fetch origin`
   - `git checkout main`
   - `git reset --hard origin/main`
   - `git clean -fd`
3. Select a Dependabot PR:
   - use `--pr <n>` when provided, otherwise
   - select the oldest open Dependabot PR on the configured base branch that maintainers can modify.
4. Configure bot git identity and signing.
5. Reset and seed the local runtime:
   - `docker compose down -v --remove-orphans`
   - remove all Docker containers
   - kill listeners on configured runner ports
   - `docker compose up -d postgres blob-storage app`
   - `docker compose run --rm dev_data`
6. Check out the Dependabot PR branch from origin.
7. Build a Codex prompt with PR metadata, changed files, and dependency diff summary.
8. Let Codex determine whether app-side changes are needed:
   - if compatibility changes are needed, Codex applies them on the PR branch
   - if no follow-up changes are needed, Codex leaves the branch unchanged.
9. Run local checks in a self-heal loop:
   - `make lint`
   - `make test`
   - `make audit-python` when Python dependency files changed
   - `make audit-node-runtime` and `make audit-node-full` when Node dependency files changed
10. Persist a sanitized run log to `docs/agent-logs/run-<timestamp>-dependabot-pr-<n>.txt`.
11. If the branch changed:

- commit the follow-up changes
- push back to the same Dependabot PR branch with `--force-with-lease`

12. Comment on the PR with the outcome and the run log path.
13. Return to `main` on exit.

## Queue Strategy

This runner should remain single-PR-at-a-time.

- It exits early if a human-authored PR is open.
- It exits early if any unrelated bot-authored PR is open.
- It always selects the oldest eligible open Dependabot PR first.

That means backlog handling should come from safe repeated polling, not from trying to process multiple Dependabot PRs in one run.

Recommended operation:

1. Schedule `./scripts/run_dependabot_pr_queue.sh` at least once per day as a baseline check.
2. Prefer a frequent poll cadence, such as every `15` minutes.
3. Let the queue wrapper exit quickly when a human PR or bot PR is already open.
4. Once the current Dependabot PR merges, the next scheduled poll picks up the next oldest open Dependabot PR automatically.

`run_dependabot_pr_queue.sh` adds a local lock directory under `.tmp/` so frequent polling does not start overlapping runs on the same host.

## Manual Run

```bash
./scripts/run_dependabot_pr_queue.sh
```

Optional forced PR:

```bash
./scripts/agent_dependabot_pr_runner.sh --pr 1772
```

## Environment

The runner reuses the same bot identity, signing, and Codex configuration conventions as `scripts/agent_daily_issue_runner.sh`.

Useful environment variables:

- `HUSHLINE_REPO_DIR`
- `HUSHLINE_REPO_SLUG`
- `HUSHLINE_BASE_BRANCH`
- `HUSHLINE_CODEX_MODEL`
- `HUSHLINE_CODEX_REASONING_EFFORT`
- `HUSHLINE_DEPENDABOT_APP_SLUG`
- `HUSHLINE_DEPENDABOT_BASE_BRANCH`
- `HUSHLINE_DEPENDABOT_PR_LIMIT`
- `HUSHLINE_DEPENDABOT_MAX_FIX_ATTEMPTS`
- `HUSHLINE_DAILY_RUN_LOG_RETENTION`
- `HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR`
- `HUSHLINE_DEPENDABOT_RUNNER_SCRIPT`

## Notes

- This runner does not open a new PR; it updates the existing Dependabot PR branch when follow-up changes are required.
- If no app-side changes are needed, the runner still validates the branch locally and leaves a PR comment stating that no follow-up code changes were required.
- The runner expects to work only with Dependabot PRs that maintainers can modify.
- The queue wrapper is safe to schedule frequently because it takes a local lock and then delegates a single run to `scripts/agent_dependabot_pr_runner.sh`.

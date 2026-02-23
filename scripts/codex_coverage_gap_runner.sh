#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
FORCE_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      FORCE_RUN=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_SLUG="${HUSHLINE_REPO_SLUG:-scidsg/hushline}"
BASE_BRANCH="${HUSHLINE_BASE_BRANCH:-main}"
BRANCH_PREFIX="${HUSHLINE_COVERAGE_BRANCH_PREFIX:-codex/coverage-gap-}"
BOT_LOGIN="${HUSHLINE_BOT_LOGIN:-hushline-dev}"
NO_GPG_SIGN="${HUSHLINE_COVERAGE_NO_GPG_SIGN:-0}"
RUN_LOCAL_CHECKS="${HUSHLINE_COVERAGE_RUN_CHECKS:-1}"
CODEX_MODEL="${HUSHLINE_CODEX_MODEL:-gpt-5.3-codex}"
TARGET_COVERAGE="${HUSHLINE_TARGET_COVERAGE:-100}"
MAX_REPORT_LINES="${HUSHLINE_COVERAGE_REPORT_LINES:-80}"
RUN_HEALTHCHECK="${HUSHLINE_COVERAGE_RUN_HEALTHCHECK:-1}"
HEALTHCHECK_SCRIPT="${HUSHLINE_HEALTHCHECK_SCRIPT:-$REPO_DIR/scripts/healthcheck.sh}"
HEALTH_BADGE_UPDATER="${HUSHLINE_HEALTH_BADGE_UPDATER:-$REPO_DIR/scripts/update_agent_health_badge.sh}"
PUBLISH_HEALTH_BADGE_ON_DRY_RUN="${HUSHLINE_HEALTH_BADGE_PUBLISH_ON_DRY_RUN:-0}"

cd "$REPO_DIR"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd git
require_cmd gh
require_cmd codex
require_cmd docker
require_cmd make

publish_health_badge() {
  local status="$1"

  if [[ "$DRY_RUN" == "1" && "$PUBLISH_HEALTH_BADGE_ON_DRY_RUN" != "1" ]]; then
    return 0
  fi

  if [[ ! -x "$HEALTH_BADGE_UPDATER" ]]; then
    echo "Warning: health badge updater is not executable: $HEALTH_BADGE_UPDATER" >&2
    return 0
  fi

  if ! "$HEALTH_BADGE_UPDATER" "$status" "coverage"; then
    echo "Warning: failed to publish agent health badge ($status)." >&2
  fi
}

if [[ "$RUN_HEALTHCHECK" == "1" ]]; then
  if [[ ! -x "$HEALTHCHECK_SCRIPT" ]]; then
    echo "Healthcheck script is not executable: $HEALTHCHECK_SCRIPT" >&2
    exit 1
  fi
  echo "==> Invariant check: healthcheck (coverage)"
  if "$HEALTHCHECK_SCRIPT" --mode coverage; then
    publish_health_badge healthy
  else
    publish_health_badge unhealthy
    exit 1
  fi
fi

run_check() {
  local name="$1"
  shift
  echo "==> Invariant check: $name"
  "$@"
}

full_rebuild() {
  run_check "docker reset (down -v)" docker compose down -v --remove-orphans
  run_check "docker rebuild app image" docker compose build app
}

gh auth status -h github.com >/dev/null

OPEN_BOT_PR_COUNT="$(
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --author "$BOT_LOGIN" \
    --limit 100 \
    --json number \
    --jq 'length'
)"
if [[ "$OPEN_BOT_PR_COUNT" != "0" ]]; then
  echo "Skipped: open PR(s) by ${BOT_LOGIN} already exist (${OPEN_BOT_PR_COUNT})."
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash changes before running." >&2
  exit 1
fi

git fetch origin "$BASE_BRANCH" --prune
git checkout "$BASE_BRANCH"
git pull --ff-only origin "$BASE_BRANCH"

if [[ "$DRY_RUN" != "1" ]]; then
  full_rebuild
fi

COVERAGE_OUTPUT_FILE="$(mktemp)"
CODEX_OUTPUT_FILE="$(mktemp)"
PROMPT_FILE="$(mktemp)"
PR_BODY_FILE="$(mktemp)"

cleanup() {
  rm -f "$COVERAGE_OUTPUT_FILE" "$CODEX_OUTPUT_FILE" "$PROMPT_FILE" "$PR_BODY_FILE"
}
trap cleanup EXIT

echo "==> Measuring current test coverage"
docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only | tee "$COVERAGE_OUTPUT_FILE"

CURRENT_COVERAGE="$(
  grep -E '^TOTAL' "$COVERAGE_OUTPUT_FILE" \
    | awk '{print $4}' \
    | tr -d '%' \
    | tail -n 1
)"

if [[ -z "$CURRENT_COVERAGE" ]]; then
  echo "Could not parse TOTAL coverage from test output." >&2
  exit 1
fi

if [[ "$FORCE_RUN" != "1" ]] && [[ "$CURRENT_COVERAGE" -ge "$TARGET_COVERAGE" ]]; then
  echo "Coverage ${CURRENT_COVERAGE}% already meets target ${TARGET_COVERAGE}%."
  exit 0
fi

MISSING_TABLE="$(
  awk '
    BEGIN { in_table=0; divider_count=0 }
    /^Name[[:space:]]+Stmts[[:space:]]+Miss[[:space:]]+Cover/ { in_table=1; next }
    in_table && /^-+/ { divider_count++; next }
    in_table && divider_count == 1 && $1 ~ /^hushline\// && $3 + 0 > 0 { print $0 }
    in_table && /^TOTAL/ { exit }
  ' "$COVERAGE_OUTPUT_FILE" | head -n "$MAX_REPORT_LINES"
)"

if [[ -z "$MISSING_TABLE" ]]; then
  MISSING_TABLE="No uncovered file rows were parsed from coverage output."
fi

BRANCH_NAME="${BRANCH_PREFIX}$(date -u +%Y%m%d-%H%M%S)"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Dry run: coverage gap detected."
  echo "Current coverage: ${CURRENT_COVERAGE}% (target ${TARGET_COVERAGE}%)"
  echo "Branch that would be used: $BRANCH_NAME"
  echo "Coverage rows to include in prompt:"
  printf '%s\n' "$MISSING_TABLE"
  exit 0
fi

git checkout -B "$BRANCH_NAME"

{
  cat <<EOF
You are improving test coverage in $REPO_SLUG.

Current measured line coverage: ${CURRENT_COVERAGE}%.
Target coverage: ${TARGET_COVERAGE}%.

Coverage report rows with uncovered lines:
${MISSING_TABLE}

Follow AGENTS.md and any deeper AGENTS.md files exactly. This repository is security-critical.

Required output:
1) Raise coverage to at least ${TARGET_COVERAGE}%.
2) Prefer adding/updating tests. Avoid production behavior changes unless required for testability.
3) Do not run lint/test/coverage commands; the runner executes required checks after your code changes are complete.
4) Summarize code changes only. Do not include local lint/test/coverage status; the runner reports those separately.

Important:
- Do not weaken E2EE, auth, anonymity, or privacy protections.
- Keep diffs focused and minimal.
EOF
} > "$PROMPT_FILE"

codex exec \
  --model "$CODEX_MODEL" \
  --full-auto \
  --sandbox workspace-write \
  -C "$REPO_DIR" \
  -o "$CODEX_OUTPUT_FILE" \
  - < "$PROMPT_FILE"

if [[ -z "$(git status --porcelain)" ]]; then
  echo "Codex produced no changes while coverage was ${CURRENT_COVERAGE}%."
  git checkout "$BASE_BRANCH"
  git branch -D "$BRANCH_NAME" >/dev/null 2>&1 || true
  exit 0
fi

if [[ "$RUN_LOCAL_CHECKS" == "1" ]]; then
  run_check "lint" make lint
  run_check "tests" make test PYTEST_ADDOPTS="--skip-local-only"
  run_check "coverage threshold >= ${TARGET_COVERAGE}%" \
    docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only --cov-fail-under="$TARGET_COVERAGE"
fi

git add -A
COMMIT_MESSAGE="test: close coverage gap (${CURRENT_COVERAGE}% -> ${TARGET_COVERAGE}%)"
if [[ "$NO_GPG_SIGN" == "1" ]]; then
  git commit --no-gpg-sign -m "$COMMIT_MESSAGE"
else
  git commit -m "$COMMIT_MESSAGE"
fi

git push -u origin "$BRANCH_NAME"

CHANGED_FILES="$(
  git diff --name-only "${BASE_BRANCH}...${BRANCH_NAME}" | sed 's/^/- /'
)"
if [[ -z "$CHANGED_FILES" ]]; then
  CHANGED_FILES="- (unable to determine changed files)"
fi
PR_TITLE="Codex Coverage: raise coverage to ${TARGET_COVERAGE}%"

{
  cat <<EOF
Automated local Codex coverage run.

Coverage before run: ${CURRENT_COVERAGE}%
Coverage target: ${TARGET_COVERAGE}%
Branch: $BRANCH_NAME

Changed files:
${CHANGED_FILES}

Runner validation commands:
- make lint
- make test PYTEST_ADDOPTS="--skip-local-only"
- docker compose run --rm app poetry run pytest --cov hushline --cov-report term-missing -q --skip-local-only --cov-fail-under=${TARGET_COVERAGE}

Codex implementation summary (model output):
EOF
  head -c 3000 "$CODEX_OUTPUT_FILE" || true
  printf '\n'
} > "$PR_BODY_FILE"

PR_URL="$(
  gh pr create \
    --repo "$REPO_SLUG" \
    --base "$BASE_BRANCH" \
    --head "$BRANCH_NAME" \
    --title "$PR_TITLE" \
    --body-file "$PR_BODY_FILE"
)"

echo "Opened PR: $PR_URL"

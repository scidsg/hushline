#!/usr/bin/env bash
set -euo pipefail

prepare_runner_exec_snapshot() {
  local runner_script_path="${1:-${BASH_SOURCE[0]}}"
  local runner_argv0="${2:-$0}"
  local original_script_dir original_script_path snapshot_file

  if [[ "${HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_ACTIVE:-0}" == "1" ]]; then
    return 1
  fi

  if [[ "$runner_script_path" != "$runner_argv0" ]]; then
    return 1
  fi

  original_script_dir="$(CDPATH= cd -- "$(dirname -- "$runner_script_path")" && pwd)"
  original_script_path="$original_script_dir/$(basename -- "$runner_script_path")"
  snapshot_file="$(mktemp "${TMPDIR:-/tmp}/agent_daily_coverage_runner.XXXXXX.sh")"
  cp "$original_script_path" "$snapshot_file"
  chmod 700 "$snapshot_file"
  printf '%s\t%s\n' "$original_script_dir" "$snapshot_file"
}

if SNAPSHOT_METADATA="$(prepare_runner_exec_snapshot "${BASH_SOURCE[0]}" "$0")"; then
  IFS=$'\t' read -r HUSHLINE_COVERAGE_RUNNER_ORIGINAL_SCRIPT_DIR HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_PATH <<< "$SNAPSHOT_METADATA"
  export HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_ACTIVE=1
  export HUSHLINE_COVERAGE_RUNNER_ORIGINAL_SCRIPT_DIR
  export HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_PATH
  exec bash "$HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_PATH" "$@"
fi

SCRIPT_DIR="${HUSHLINE_COVERAGE_RUNNER_ORIGINAL_SCRIPT_DIR:-$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
DEFAULT_REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

REPO_DIR="${HUSHLINE_REPO_DIR:-$DEFAULT_REPO_DIR}"
REPO_SLUG="${HUSHLINE_REPO_SLUG:-scidsg/hushline}"
BASE_BRANCH="${HUSHLINE_BASE_BRANCH:-main}"
BOT_LOGIN="${HUSHLINE_BOT_LOGIN:-hushline-dev}"
BOT_GIT_NAME="${HUSHLINE_BOT_GIT_NAME:-$BOT_LOGIN}"
BOT_GIT_EMAIL="${HUSHLINE_BOT_GIT_EMAIL:-git-dev@scidsg.org}"
BOT_GIT_GPG_FORMAT="${HUSHLINE_BOT_GIT_GPG_FORMAT:-ssh}"
BOT_GIT_SIGNING_KEY="${HUSHLINE_BOT_GIT_SIGNING_KEY:-}"
DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH="${HUSHLINE_BOT_GIT_DEFAULT_SSH_SIGNING_KEY_PATH:-}"
BRANCH_NAME="${HUSHLINE_COVERAGE_BRANCH_NAME:-codex/daily-coverage}"
CODEX_MODEL="${HUSHLINE_CODEX_MODEL:-gpt-5.5}"
CODEX_REASONING_EFFORT="${HUSHLINE_CODEX_REASONING_EFFORT:-high}"
HOST_PORTS_TO_CLEAR="${HUSHLINE_DAILY_KILL_PORTS:-4566 4571 5432 8080}"
MAX_COVERAGE_ATTEMPTS="${HUSHLINE_COVERAGE_MAX_ATTEMPTS:-10}"
MAX_FIX_ATTEMPTS="${HUSHLINE_COVERAGE_MAX_FIX_ATTEMPTS:-8}"
RUNTIME_BOOTSTRAP_ATTEMPTS="${HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS:-3}"
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS="${HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS:-10}"
POST_PR_FEEDBACK_DELAY_SECONDS="${HUSHLINE_DAILY_POST_PR_FEEDBACK_DELAY_SECONDS:-900}"
RUN_LOG_RETENTION_COUNT="${HUSHLINE_DAILY_RUN_LOG_RETENTION:-10}"
COVERAGE_TARGET_PERCENT="${HUSHLINE_COVERAGE_TARGET_PERCENT:-100}"
COVERAGE_SUMMARY_LIMIT="${HUSHLINE_COVERAGE_SUMMARY_LIMIT:-15}"

CHECK_LOG_FILE=""
PROMPT_FILE=""
PR_BODY_FILE=""
CODEX_OUTPUT_FILE=""
CODEX_TRANSCRIPT_FILE=""
RUN_LOG_TMP_FILE=""
RUN_LOG_TIMESTAMP=""
RUN_LOG_GIT_PATH=""
VERBOSE_CODEX_OUTPUT="${HUSHLINE_DAILY_VERBOSE_CODEX_OUTPUT:-0}"
COVERAGE_ARTIFACT_DIR=""
COVERAGE_REPORT_FILE=""
INITIAL_COVERAGE_PERCENT=""
INITIAL_COVERAGE_MISSING_LINES=""
INITIAL_COVERAGE_MISSING_FILES=""
FINAL_COVERAGE_PERCENT=""
CURRENT_COVERAGE_PERCENT=""
CURRENT_COVERAGE_MISSING_LINES=""
CURRENT_COVERAGE_MISSING_FILES=""
CURRENT_COVERAGE_SUMMARY=""
PREVIOUS_FAILURE_SIGNATURE=""
FAILURE_SIGNATURE=""
REPEATED_FAILURE_COUNT=0

parse_args() {
  if [[ $# -gt 0 ]]; then
    echo "Unknown argument: $1" >&2
    exit 1
  fi
}

runner_status() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

initialize_run_state() {
  CHECK_LOG_FILE="$(mktemp)"
  PROMPT_FILE="$(mktemp)"
  PR_BODY_FILE="$(mktemp)"
  CODEX_OUTPUT_FILE="$(mktemp)"
  CODEX_TRANSCRIPT_FILE="$(mktemp)"
  RUN_LOG_TMP_FILE="$(mktemp)"
  RUN_LOG_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  COVERAGE_ARTIFACT_DIR="$REPO_DIR/.coverage-runner"
  COVERAGE_REPORT_FILE="$COVERAGE_ARTIFACT_DIR/coverage.json"

  exec 3>&1
  exec > >(tee -a "$RUN_LOG_TMP_FILE") 2>&1
  runner_status "Starting daily coverage runner check."
  echo "Runner Codex config: model=$CODEX_MODEL reasoning_effort=$CODEX_REASONING_EFFORT verbose_codex_output=$VERBOSE_CODEX_OUTPUT target_percent=$COVERAGE_TARGET_PERCENT"
}

cleanup() {
  rm -f "${CHECK_LOG_FILE:-}" "${PROMPT_FILE:-}" "${PR_BODY_FILE:-}" "${CODEX_OUTPUT_FILE:-}" "${CODEX_TRANSCRIPT_FILE:-}" "${RUN_LOG_TMP_FILE:-}"
  rm -f "${COVERAGE_REPORT_FILE:-}" "${HUSHLINE_COVERAGE_RUNNER_SNAPSHOT_PATH:-}"
  rmdir "${COVERAGE_ARTIFACT_DIR:-}" >/dev/null 2>&1 || true
  if [[ -d "$REPO_DIR/.git" ]]; then
    if ! git -C "$REPO_DIR" checkout "$BASE_BRANCH" >/dev/null 2>&1; then
      echo "Warning: failed to switch back to $BASE_BRANCH during cleanup." >&2
      return
    fi
    if ! git -C "$REPO_DIR" reset --hard "origin/$BASE_BRANCH" >/dev/null 2>&1; then
      if ! git -C "$REPO_DIR" reset --hard "$BASE_BRANCH" >/dev/null 2>&1; then
        echo "Warning: failed to reset $BASE_BRANCH during cleanup." >&2
      fi
    fi
    if ! git -C "$REPO_DIR" clean -fd >/dev/null 2>&1; then
      echo "Warning: failed to remove untracked files during cleanup." >&2
    fi
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"

  if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 )); then
    echo "${name} must be a positive integer (got '${value}')." >&2
    return 1
  fi
}

resolve_bot_git_signing_key() {
  local configured_signing_key=""
  local configured_gpg_format=""

  if [[ "$BOT_GIT_GPG_FORMAT" != "ssh" ]]; then
    printf '%s\n' "$BOT_GIT_SIGNING_KEY"
    return 0
  fi

  if [[ -n "$BOT_GIT_SIGNING_KEY" ]]; then
    printf '%s\n' "$BOT_GIT_SIGNING_KEY"
    return 0
  fi

  configured_signing_key="$(git config --get user.signingkey 2>/dev/null || true)"
  configured_gpg_format="$(git config --get gpg.format 2>/dev/null || true)"
  if [[ -n "$configured_signing_key" ]]; then
    if [[ "$configured_gpg_format" == "ssh" ]] || [[ "$configured_signing_key" == ssh-*' '* ]] || [[ "$configured_signing_key" == *.pub ]]; then
      printf '%s\n' "$configured_signing_key"
      return 0
    fi
  fi

  if [[ -n "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH" && -f "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH" ]]; then
    printf '%s\n' "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH"
    return 0
  fi

  return 1
}

assert_ssh_signing_ready() {
  local signing_key="$1"
  local private_key_hint=""
  local smoke_dir=""
  local smoke_output=""

  if [[ -z "$signing_key" ]]; then
    printf '%s\n' "Blocked: SSH signing key is not configured." >&2
    return 1
  fi

  if [[ "$signing_key" != ssh-*' '* && ! -f "$signing_key" ]]; then
    printf '%s\n' "Blocked: SSH signing key file not found: $signing_key" >&2
    return 1
  fi

  if [[ "$signing_key" == *.pub ]]; then
    private_key_hint="${signing_key%.pub}"
  fi

  smoke_dir="$(mktemp -d)"
  set +e
  smoke_output="$(
    cd "$smoke_dir" &&
      git init -q &&
      git config user.name "$BOT_GIT_NAME" &&
      git config user.email "$BOT_GIT_EMAIL" &&
      git config commit.gpgsign true &&
      git config gpg.format ssh &&
      git config user.signingkey "$signing_key" &&
      git commit --allow-empty -m "runner signing preflight" 2>&1
  )"
  local smoke_rc=$?
  set -e
  rm -rf "$smoke_dir"

  if (( smoke_rc == 0 )); then
    return 0
  fi

  if printf '%s\n' "$smoke_output" | grep -Eqi '(incorrect passphrase supplied to decrypt private key|enter passphrase for)'; then
    if [[ -n "$private_key_hint" ]]; then
      printf '%s\n' "Blocked: SSH signing key is present but unavailable to Git. Load the matching private key into ssh-agent first, for example: ssh-add $private_key_hint" >&2
    else
      printf '%s\n' "Blocked: SSH signing key is present but unavailable to Git. Load the matching private key into ssh-agent first." >&2
    fi
    return 1
  fi

  printf '%s\n' "Blocked: SSH signing preflight failed for $signing_key" >&2
  printf '%s\n' "$smoke_output" >&2
  return 1
}

configure_bot_git_identity() {
  local resolved_signing_key=""
  git config user.name "$BOT_GIT_NAME"
  git config user.email "$BOT_GIT_EMAIL"
  git config commit.gpgsign true
  if [[ -n "$BOT_GIT_GPG_FORMAT" ]]; then
    git config gpg.format "$BOT_GIT_GPG_FORMAT"
  fi
  if resolved_signing_key="$(resolve_bot_git_signing_key)"; then
    git config user.signingkey "$resolved_signing_key"
  elif [[ "$BOT_GIT_GPG_FORMAT" == "ssh" ]]; then
    printf '%s\n' "Blocked: SSH commit signing is enabled, but no signing key is configured." >&2
    return 1
  elif [[ -n "$BOT_GIT_SIGNING_KEY" ]]; then
    git config user.signingkey "$BOT_GIT_SIGNING_KEY"
  fi

  if [[ "$BOT_GIT_GPG_FORMAT" == "ssh" ]]; then
    assert_ssh_signing_ready "$resolved_signing_key"
  fi
}

run_step() {
  local description="$1"
  shift
  echo "==> ${description}"
  "$@"
}

run_check_capture() {
  local description="$1"
  shift
  echo "==> ${description}" | tee -a "$CHECK_LOG_FILE"
  local rc=0
  set +e
  "$@" 2>&1 | tee -a "$CHECK_LOG_FILE"
  rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

run_runtime_check_with_self_heal() {
  local description="$1"
  shift
  if run_check_capture "$description" "$@"; then
    return 0
  fi

  echo "Self-heal: ${description} failed; resetting local runtime once." | tee -a "$CHECK_LOG_FILE"
  reset_runtime_stack_and_seed_dev_data
  run_check_capture "${description} (self-heal retry after runtime reset)" "$@"
}

list_changed_files() {
  {
    git diff --name-only "${BASE_BRANCH}...HEAD"
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | awk 'NF && !seen[$0]++'
}

changed_files_match() {
  local pattern="$1"
  list_changed_files | grep -Eq "$pattern"
}

runtime_schema_files_changed() {
  changed_files_match '^(hushline/model/|migrations/|scripts/dev_data\.py$|scripts/dev_migrations\.py$)'
}

runtime_bootstrap_failure_looks_retryable() {
  local text="$1"
  printf '%s\n' "$text" | grep -Eqi '(unexpected status from HEAD request|500 internal server error|503 service unavailable|504 gateway timeout|too many requests|tls handshake timeout|i/o timeout|context deadline exceeded|request canceled while waiting for connection|connection reset by peer|temporary failure in name resolution|name or service not known|no such host|hostname cannot be resolved by your DNS|network is not connected to the internet|all attempts to connect to files\.pythonhosted\.org failed|all attempts to connect to pypi\.org failed|net/http: request canceled|failed to copy: httpReadSeeker|error pulling image configuration)'
}

start_runtime_stack_and_seed_dev_data() {
  local compose_up_args=("$@")
  local attempt=1
  local attempt_log=""
  local compose_up_rc=0
  local seed_rc=0

  while (( attempt <= RUNTIME_BOOTSTRAP_ATTEMPTS )); do
    attempt_log="$(mktemp)"

    echo "==> Start Docker stack"
    set +e
    docker compose up -d "${compose_up_args[@]}" 2>&1 | tee "$attempt_log"
    compose_up_rc=${PIPESTATUS[0]}
    set -e

    if (( compose_up_rc == 0 )); then
      echo "==> Seed development data"
      set +e
      docker compose run --rm dev_data 2>&1 | tee -a "$attempt_log"
      seed_rc=${PIPESTATUS[0]}
      set -e

      if (( seed_rc == 0 )); then
        rm -f "$attempt_log"
        return 0
      fi
    fi

    if (( attempt >= RUNTIME_BOOTSTRAP_ATTEMPTS )); then
      rm -f "$attempt_log"
      if (( compose_up_rc != 0 )); then
        return "$compose_up_rc"
      fi
      return "$seed_rc"
    fi

    if ! runtime_bootstrap_failure_looks_retryable "$(tail -n 200 "$attempt_log")"; then
      rm -f "$attempt_log"
      if (( compose_up_rc != 0 )); then
        return "$compose_up_rc"
      fi
      return "$seed_rc"
    fi

    echo "Runtime bootstrap hit a retryable failure; resetting partial state and retrying in ${RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS}s (attempt ${attempt}/${RUNTIME_BOOTSTRAP_ATTEMPTS})."
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -f "$attempt_log"
    sleep "$RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS"
    attempt=$((attempt + 1))
  done
}

reset_runtime_stack_and_seed_dev_data() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  start_runtime_stack_and_seed_dev_data postgres blob-storage app
}

refresh_runtime_after_schema_changes() {
  echo "==> Refresh local runtime after schema changes" | tee -a "$CHECK_LOG_FILE"
  if ! runtime_schema_files_changed; then
    echo "Skipped: no schema-affecting files changed." | tee -a "$CHECK_LOG_FILE"
    return 0
  fi

  reset_runtime_stack_and_seed_dev_data
}

lint_failure_looks_auto_fixable() {
  local failure_text="$1"

  if printf '%s\n' "$failure_text" | grep -Fq "Would reformat:"; then
    return 0
  fi

  if printf '%s\n' "$failure_text" | grep -Fq "Code style issues found in the above file."; then
    return 0
  fi

  if printf '%s\n' "$failure_text" | grep -Eq 'Found [0-9]+ error'; then
    if printf '%s\n' "$failure_text" | grep -Fq "(checked "; then
      return 1
    fi
    return 0
  fi

  return 1
}

auto_fix_lint_with_containerized_tooling() {
  echo "Self-heal: applying deterministic lint fix via make fix." | tee -a "$CHECK_LOG_FILE"
  run_check_capture "Auto-fix lint issues (make fix)" make fix
}

coverage_report_exists() {
  [[ -f "$COVERAGE_REPORT_FILE" ]]
}

coverage_report_summary_text() {
  local report_file="$1"
  local limit="${2:-$COVERAGE_SUMMARY_LIMIT}"

  python3 - "$report_file" "$limit" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
limit = int(sys.argv[2])
data = json.loads(report_path.read_text())
files = data.get("files", {})

def compress_ranges(values):
    if not values:
        return ""
    values = sorted({int(v) for v in values})
    ranges = []
    start = prev = values[0]
    for line in values[1:]:
        if line == prev + 1:
            prev = line
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = line
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)

rows = []
for path, payload in files.items():
    summary = payload.get("summary", {})
    missing_lines = payload.get("missing_lines", []) or []
    missing_count = int(summary.get("missing_lines", len(missing_lines)) or 0)
    if missing_count <= 0:
      continue
    percent = float(summary.get("percent_covered", 0.0) or 0.0)
    rows.append((missing_count, path, percent, compress_ranges(missing_lines)))

rows.sort(key=lambda item: (-item[0], item[1]))
for missing_count, path, percent, ranges in rows[:limit]:
    line = f"- {path}: {percent:.2f}% covered, {missing_count} missing line(s)"
    if ranges:
        line += f" ({ranges})"
    print(line)
PY
}

update_coverage_state_from_report() {
  local summary
  if ! coverage_report_exists; then
    echo "Blocked: coverage report was not generated at $COVERAGE_REPORT_FILE." >&2
    return 1
  fi

  read -r CURRENT_COVERAGE_PERCENT CURRENT_COVERAGE_MISSING_LINES CURRENT_COVERAGE_MISSING_FILES < <(
    python3 - "$COVERAGE_REPORT_FILE" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
totals = data.get("totals", {})
percent = float(totals.get("percent_covered", 0.0) or 0.0)
missing_lines = int(totals.get("missing_lines", 0) or 0)
missing_files = 0
for payload in (data.get("files", {}) or {}).values():
    summary = payload.get("summary", {}) or {}
    if int(summary.get("missing_lines", 0) or 0) > 0:
        missing_files += 1
print(f"{percent:.2f} {missing_lines} {missing_files}")
PY
  )

  summary="$(coverage_report_summary_text "$COVERAGE_REPORT_FILE" "$COVERAGE_SUMMARY_LIMIT")"
  if [[ -z "$summary" ]]; then
    CURRENT_COVERAGE_SUMMARY="- No uncovered files remain."
  else
    CURRENT_COVERAGE_SUMMARY="$summary"
  fi
}

coverage_target_met() {
  python3 - "$CURRENT_COVERAGE_PERCENT" "$COVERAGE_TARGET_PERCENT" <<'PY'
import sys
current = float(sys.argv[1])
target = float(sys.argv[2])
raise SystemExit(0 if current >= target else 1)
PY
}

run_coverage_scan() {
  mkdir -p "$COVERAGE_ARTIFACT_DIR"
  rm -f "$COVERAGE_REPORT_FILE"
  run_runtime_check_with_self_heal \
    "Run coverage scan" \
    docker compose run --rm app poetry run pytest \
      --cov hushline \
      --cov-report "json:/app/.coverage-runner/coverage.json" \
      --cov-report term-missing \
      -q \
      --skip-local-only
  update_coverage_state_from_report
  echo "Coverage snapshot: ${CURRENT_COVERAGE_PERCENT}% covered, ${CURRENT_COVERAGE_MISSING_LINES} missing line(s) across ${CURRENT_COVERAGE_MISSING_FILES} file(s)."
}

run_local_validation_and_coverage() {
  : > "$CHECK_LOG_FILE"
  local lint_failure_tail=""

  refresh_runtime_after_schema_changes || return 1
  if ! run_check_capture "Run lint" make lint; then
    lint_failure_tail="$(tail -n 240 "$CHECK_LOG_FILE")"
    if ! lint_failure_looks_auto_fixable "$lint_failure_tail"; then
      return 1
    fi
    if ! auto_fix_lint_with_containerized_tooling; then
      return 1
    fi
    run_check_capture "Re-run lint after deterministic auto-fix" make lint || return 1
  fi

  run_runtime_check_with_self_heal "Run test (full suite)" make test || return 1
  run_coverage_scan || return 1
  coverage_target_met
}

count_open_bot_prs() {
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --author "$BOT_LOGIN" \
    --limit 100 \
    --json number \
    --jq 'length'
}

count_open_bot_prs_excluding_heads() {
  local allowed_heads=("$@")
  local head allowed skip count=0

  while IFS= read -r head; do
    [[ -z "$head" ]] && continue
    skip=0
    for allowed in "${allowed_heads[@]}"; do
      if [[ -n "$allowed" && "$head" == "$allowed" ]]; then
        skip=1
        break
      fi
    done
    if (( skip == 0 )); then
      count=$((count + 1))
    fi
  done < <(
    gh pr list \
      --repo "$REPO_SLUG" \
      --state open \
      --author "$BOT_LOGIN" \
      --limit 100 \
      --json headRefName \
      --jq '.[].headRefName // empty'
  )

  printf '%s\n' "$count"
}

count_open_human_prs() {
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --limit 200 \
    --json author \
    --jq '
      [
        .[]
        | (.author.login // "")
        | select(length > 0)
        | select(. != "'"$BOT_LOGIN"'")
        | select(test("\\[bot\\]$") | not)
      ] | length
    '
}

find_open_pr_for_head_branch() {
  local head_branch="$1"
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --head "$head_branch" \
    --limit 1 \
    --json number,url,title \
    --jq '.[0] // empty'
}

remote_branch_exists() {
  local branch="$1"
  git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1
}

current_branch_name() {
  git symbolic-ref --quiet --short HEAD 2>/dev/null
}

ensure_worktree_on_branch() {
  local expected_branch="$1"
  local current_branch=""

  current_branch="$(current_branch_name || true)"
  if [[ "$current_branch" == "$expected_branch" ]]; then
    return 0
  fi

  if [[ -z "$current_branch" ]]; then
    current_branch="DETACHED"
  fi

  echo "Self-heal: current branch is '$current_branch'; checking out '$expected_branch' before committing."
  git checkout "$expected_branch"
}

ensure_head_commit_on_branch() {
  local expected_branch="$1"
  local base_branch="$2"
  local current_branch=""
  local head_commit=""

  current_branch="$(current_branch_name || true)"
  if [[ "$current_branch" == "$expected_branch" ]]; then
    return 0
  fi

  head_commit="$(git rev-parse HEAD)"
  if [[ -z "$current_branch" ]]; then
    current_branch="DETACHED"
  fi

  echo "Self-heal: HEAD is on '$current_branch'; moving '$expected_branch' to commit $head_commit."
  git branch -f "$expected_branch" "$head_commit"
  git checkout "$expected_branch"

  if [[ "$current_branch" == "$base_branch" ]] && git show-ref --verify --quiet "refs/remotes/origin/$base_branch"; then
    echo "Self-heal: restoring '$base_branch' to origin/$base_branch after branch drift."
    git branch -f "$base_branch" "origin/$base_branch"
  fi
}

require_branch_has_unique_commits() {
  local base_ref="$1"
  local branch_ref="$2"
  local ahead_count=""

  ahead_count="$(git rev-list --count "${base_ref}..${branch_ref}")"
  [[ "$ahead_count" =~ ^[0-9]+$ ]] || return 1
  if (( ahead_count > 0 )); then
    return 0
  fi

  printf '%s\n' "Blocked: branch '$branch_ref' has no commits ahead of '$base_ref'; refusing to create or update a PR." >&2
  return 1
}

push_branch_for_pr() {
  local branch="$1"

  if remote_branch_exists "$branch"; then
    echo "Remote branch '$branch' exists; pushing with --force-with-lease."
    if git push -u --force-with-lease origin "$branch"; then
      return 0
    fi

    echo "Push was rejected; refreshing and retrying once."
    git fetch origin "$branch":"refs/remotes/origin/$branch" >/dev/null 2>&1 || true
    git push -u --force-with-lease origin "$branch"
    return $?
  fi

  echo "Remote branch '$branch' does not exist; creating it with a standard push."
  git push -u origin "$branch"
}

kill_all_docker_containers() {
  local ids=()
  while IFS= read -r id; do
    [[ -n "$id" ]] && ids+=("$id")
  done < <(docker ps -aq)
  if (( ${#ids[@]} == 0 )); then
    return 0
  fi

  docker rm -f "${ids[@]}" >/dev/null
}

kill_processes_on_ports() {
  if ! command -v lsof >/dev/null 2>&1; then
    echo "Skipping listener cleanup: lsof is unavailable."
    return 0
  fi

  local port pids
  for port in $HOST_PORTS_TO_CLEAR; do
    pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "Stopping process(es) on TCP ${port}: $pids"
      # shellcheck disable=SC2086
      kill $pids >/dev/null 2>&1 || true
    fi
  done

  sleep 1

  for port in $HOST_PORTS_TO_CLEAR; do
    pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "Force killing process(es) on TCP ${port}: $pids"
      # shellcheck disable=SC2086
      kill -9 $pids >/dev/null 2>&1 || true
    fi
  done
}

prompt_file_metrics() {
  local prompt_file="$1"
  if [[ -z "$prompt_file" || ! -f "$prompt_file" ]]; then
    echo "Prompt stats: bytes=0 lines=0 words=0"
    return 0
  fi
  printf 'Prompt stats: bytes=%s lines=%s words=%s\n' \
    "$(wc -c < "$prompt_file" | tr -d '[:space:]')" \
    "$(wc -l < "$prompt_file" | tr -d '[:space:]')" \
    "$(wc -w < "$prompt_file" | tr -d '[:space:]')"
}

list_non_log_changed_files() {
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | awk '!seen[$0]++' \
    | awk '
      /^$/ { next }
      /^docs\/agent-logs\/run-.*-coverage\.txt$/ { next }
      /^\.coverage-runner\/coverage\.json$/ { next }
      { print }
    '
}

has_non_log_changes() {
  [[ -n "$(list_non_log_changed_files)" ]]
}

log_worktree_snapshot() {
  local label="$1"
  printf '%s\n' "$label"
  echo "git status --short:"
  git status --short 2>/dev/null || true
  echo "Non-log changed files:"
  list_non_log_changed_files 2>/dev/null || true
}

emit_codex_no_change_diagnostic() {
  local attempt="$1"
  echo "Diagnostic: Codex left no non-log worktree changes on attempt $attempt."
  prompt_file_metrics "$PROMPT_FILE"
  log_worktree_snapshot "Post-Codex worktree snapshot:"
}

failure_signature_from_text() {
  local text="$1"
  local -a markers=()

  if printf '%s\n' "$text" | grep -Eq 'FAILED tests/'; then
    markers+=("pytest-test-failures")
  fi
  if printf '%s\n' "$text" | grep -Eq 'AssertionError:'; then
    markers+=("assertion-error")
  fi
  if printf '%s\n' "$text" | grep -Eq 'Traceback'; then
    markers+=("python-traceback")
  fi
  if printf '%s\n' "$text" | grep -Eq '^[^[:space:]]+:[0-9]+:[0-9]+: [A-Z][0-9][0-9][0-9]([0-9])? '; then
    markers+=("lint-diagnostics")
  fi
  if printf '%s\n' "$text" | grep -Eq '^[^[:space:]]+:[0-9]+: error: '; then
    markers+=("type-check-diagnostics")
  fi
  if printf '%s\n' "$text" | grep -Eq 'coverage snapshot|missing line'; then
    markers+=("coverage-gap")
  fi

  if (( ${#markers[@]} == 0 )); then
    echo "no-structured-signature"
    return 0
  fi

  printf '%s\n' "${markers[@]}"
}

sanitize_failure_excerpt() {
  local text="$1"
  local escaped_repo_dir escaped_home

  escaped_repo_dir="$(printf '%s\n' "$REPO_DIR" | sed 's/[.[\*^$()+?{|]/\\&/g')"
  escaped_home="$(printf '%s\n' "$HOME" | sed 's/[.[\*^$()+?{|]/\\&/g')"

  printf '%s\n' "$text" | sed -E \
    -e "s#${escaped_repo_dir}/##g" \
    -e "s#${escaped_home}/#~/#g" \
    -e 's#/var/folders/[^[:space:]]+#/var/folders/[redacted]#g' \
    -e 's#/tmp/[^[:space:]]+#/tmp/[redacted]#g' \
    -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[redacted-email]/g'
}

recent_failure_block_from_text() {
  local text="$1"
  local filtered=""

  filtered="$(printf '%s\n' "$text" | awk '
    /^Name[[:space:]]+Stmts[[:space:]]+Miss/ { next }
    /^TOTAL[[:space:]]+/ { next }
    /^Coverage HTML written/ { next }
    /^={5,}/ { next }
    /^-{5,}/ { next }
    /^[[:space:]]*$/ { next }
    { lines[++count] = $0 }
    END {
      start = count - 79
      if (start < 1) {
        start = 1
      }
      for (i = start; i <= count; i += 1) {
        print lines[i]
      }
    }
  ')"

  sanitize_failure_excerpt "$filtered"
}

current_change_summary() {
  {
    echo "Current git status:"
    git status --short
    echo
    echo "Current diff stat:"
    git diff --stat
  } 2>/dev/null
}

build_coverage_prompt() {
  local branch_name="$1"
  {
    cat <<EOF2
You are improving automated test coverage in $REPO_SLUG on branch $branch_name.

Current total coverage: ${CURRENT_COVERAGE_PERCENT}%.
Coverage target: ${COVERAGE_TARGET_PERCENT}%.
Current uncovered lines: ${CURRENT_COVERAGE_MISSING_LINES} across ${CURRENT_COVERAGE_MISSING_FILES} file(s).

Coverage gaps:
${CURRENT_COVERAGE_SUMMARY}

Requirements:
1) Close the remaining coverage gaps and reach ${COVERAGE_TARGET_PERCENT}% total coverage.
2) Prefer adding or adjusting tests over changing application code.
3) Do not change production behavior just to satisfy coverage. If a gap is inherently defensive or unreachable, use the smallest justified coverage exclusion rather than a behavioral change.
4) Keep diffs minimal and focused.
5) Keep security, privacy, and E2EE protections intact.
6) Use repository make targets when you need local validation.
7) Do not run Docker/bootstrap commands, git pushes, or GitHub/Dependabot triage; the runner handles infra and PR flow.
8) Do not include meta-compliance statements in your final summary.
9) If you mention manual testing in your final summary, list only human reviewer steps to run after the PR opens. Do not describe commands or actions you performed as the agent; automated checks belong under validation. Do not use wording such as "not applicable beyond automated coverage" for behavior or security changes; identify what a human should click, submit, inspect, or verify.
EOF2
  } > "$PROMPT_FILE"
}

build_fix_prompt() {
  local branch_name="$1"
  local failure_context="$2"
  local failure_signature="$3"
  local repeated_failure_count="$4"

  {
    cat <<EOF2
You are continuing daily coverage work in $REPO_SLUG on branch $branch_name.

Current total coverage: ${CURRENT_COVERAGE_PERCENT}%.
Coverage target: ${COVERAGE_TARGET_PERCENT}%.
Current uncovered lines: ${CURRENT_COVERAGE_MISSING_LINES} across ${CURRENT_COVERAGE_MISSING_FILES} file(s).

Current coverage gaps:
${CURRENT_COVERAGE_SUMMARY}

Current branch state:
---BEGIN CURRENT CHANGES---
$(current_change_summary)
---END CURRENT CHANGES---

Most recent Codex implementation summary:
---BEGIN PRIOR CODEX SUMMARY---
$(sed -n '1,80p' "$CODEX_OUTPUT_FILE")
---END PRIOR CODEX SUMMARY---

Most recent sanitized failure block:
---BEGIN FAILURE CONTEXT---
${failure_context}
---END FAILURE CONTEXT---

Failure signature:
---BEGIN FAILURE SIGNATURE---
${failure_signature}
---END FAILURE SIGNATURE---

EOF2
    if [[ "$repeated_failure_count" =~ ^[0-9]+$ ]] && (( repeated_failure_count > 1 )); then
      printf 'This same failure signature has repeated %s times. Reassess the current repo state before editing; do not repeat the prior partial fix.\n\n' "$repeated_failure_count"
    fi
    cat <<EOF2
Requirements:
1) Fix only what is required for lint, tests, and coverage to pass.
2) Prefer test changes over application changes.
3) Do not change production behavior just to satisfy coverage.
4) If remaining gaps are inherently unreachable, use the smallest justified coverage exclusion rather than broad config churn.
5) Do not run Docker/bootstrap commands, git pushes, or GitHub/Dependabot triage; the runner handles infra and PR flow.
6) Do not include meta-compliance statements in your final summary.
7) If you mention manual testing in your final summary, list only human reviewer steps to run after the PR opens. Do not describe commands or actions you performed as the agent; automated checks belong under validation. Do not use wording such as "not applicable beyond automated coverage" for behavior or security changes; identify what a human should click, submit, inspect, or verify.
EOF2
  } > "$PROMPT_FILE"
}

run_codex_from_prompt() {
  local rc=0
  : > "$CODEX_OUTPUT_FILE"
  : > "$CODEX_TRANSCRIPT_FILE"

  if [[ "$VERBOSE_CODEX_OUTPUT" == "1" ]]; then
    echo "Codex execution started; streaming transcript to console only."
  else
    echo "Codex execution started; transcript output is excluded from persisted run logs."
  fi
  prompt_file_metrics "$PROMPT_FILE"
  log_worktree_snapshot "Pre-Codex worktree snapshot:"
  set +e
  codex exec \
    --model "$CODEX_MODEL" \
    -c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\"" \
    --full-auto \
    --sandbox workspace-write \
    -C "$REPO_DIR" \
    -o "$CODEX_OUTPUT_FILE" \
    - < "$PROMPT_FILE" 2>&1 | {
      if [[ "$VERBOSE_CODEX_OUTPUT" == "1" ]] && : >&3 2>/dev/null; then
        tee "$CODEX_TRANSCRIPT_FILE" >&3
      else
        cat > "$CODEX_TRANSCRIPT_FILE"
      fi
    }
  rc=${PIPESTATUS[0]}
  set -e

  if (( rc != 0 )); then
    echo "Codex execution failed (exit ${rc})."
    log_worktree_snapshot "Post-Codex worktree snapshot:"
    return "$rc"
  fi

  echo "Codex execution completed."
  log_worktree_snapshot "Post-Codex worktree snapshot:"
  if [[ -s "$CODEX_OUTPUT_FILE" ]]; then
    echo "Codex final message:"
    sed -n '1,60p' "$CODEX_OUTPUT_FILE"
    printf '\n'
  fi
}

run_coverage_attempt_loop() {
  local attempt=1
  local failure_context=""

  while (( attempt <= MAX_COVERAGE_ATTEMPTS )); do
    echo "==> Codex coverage attempt $attempt"
    run_codex_from_prompt

    if ! has_non_log_changes; then
      emit_codex_no_change_diagnostic "$attempt"
      if (( attempt == MAX_COVERAGE_ATTEMPTS )); then
        echo "Blocked: Codex produced no usable non-log changes after $MAX_COVERAGE_ATTEMPTS attempt(s)." >&2
        return 1
      fi
      attempt=$((attempt + 1))
      continue
    fi

    local fix_attempt=1
    while (( fix_attempt <= MAX_FIX_ATTEMPTS )); do
      if run_local_validation_and_coverage; then
        FINAL_COVERAGE_PERCENT="$CURRENT_COVERAGE_PERCENT"
        return 0
      fi

      if (( fix_attempt == MAX_FIX_ATTEMPTS && attempt == MAX_COVERAGE_ATTEMPTS )); then
        echo "Blocked: coverage runner exhausted validation self-heal attempts." >&2
        return 1
      fi

      failure_context="$(recent_failure_block_from_text "$(tail -n 400 "$CHECK_LOG_FILE")")"
      FAILURE_SIGNATURE="$(failure_signature_from_text "$(tail -n 400 "$CHECK_LOG_FILE")")"
      if [[ -n "$FAILURE_SIGNATURE" && "$FAILURE_SIGNATURE" == "$PREVIOUS_FAILURE_SIGNATURE" ]]; then
        REPEATED_FAILURE_COUNT=$((REPEATED_FAILURE_COUNT + 1))
      else
        REPEATED_FAILURE_COUNT=1
        PREVIOUS_FAILURE_SIGNATURE="$FAILURE_SIGNATURE"
      fi
      build_fix_prompt "$BRANCH_NAME" "$failure_context" "$FAILURE_SIGNATURE" "$REPEATED_FAILURE_COUNT"
      run_codex_from_prompt
      fix_attempt=$((fix_attempt + 1))
    done

    attempt=$((attempt + 1))
  done

  echo "Blocked: coverage target was not reached after $MAX_COVERAGE_ATTEMPTS attempt(s)." >&2
  return 1
}

stream_changed_files() {
  git show --name-only --pretty="" --no-renames HEAD | sed '/^$/d'
}

write_pr_changed_files_section() {
  local max_files="${1:-20}"
  local total_files line count
  total_files="$(stream_changed_files | wc -l | tr -d ' ')"
  count=0

  if [[ "$total_files" == "0" ]]; then
    printf -- "- _No file changes detected._\n"
    return 0
  fi

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    printf -- '- `%s`\n' "$line"
    count=$((count + 1))
    if (( count >= max_files )); then
      break
    fi
  done < <(stream_changed_files)

  if (( total_files > max_files )); then
    printf -- "- _...and %d more file(s)_\n" "$((total_files - max_files))"
  fi
}

build_pr_title() {
  printf 'test: daily coverage to %s%%\n' "$COVERAGE_TARGET_PERCENT"
}

write_pr_body() {
  local branch_name="$1"
  local base_branch_name="$2"
  local run_log_git_path="$3"

  cat > "$PR_BODY_FILE" <<EOF2
This PR is the automated daily coverage runner update for Hush Line.

It focuses on closing remaining automated test coverage gaps while preserving existing behavior and security guarantees.

## Summary
- Automated daily coverage runner update.
- Coverage target: \`${COVERAGE_TARGET_PERCENT}%\`
- Initial coverage in this run: \`${INITIAL_COVERAGE_PERCENT}%\`
- Final coverage in this run: \`${FINAL_COVERAGE_PERCENT}%\`
- Remaining missing lines after this run: \`${CURRENT_COVERAGE_MISSING_LINES}\`

## Context
- Branch: $branch_name
- Base branch: $base_branch_name
- Runner log: $run_log_git_path

## Coverage Gaps Addressed
${CURRENT_COVERAGE_SUMMARY}

## Changed Files
EOF2
  write_pr_changed_files_section >> "$PR_BODY_FILE"

  cat >> "$PR_BODY_FILE" <<EOF2

## Validation
- \`make lint\`
- \`make test\` (full suite)
- \`docker compose run --rm app poetry run pytest --cov hushline --cov-report json:/app/.coverage-runner/coverage.json --cov-report term-missing -q --skip-local-only\`

## Manual Testing
- Manual testing is for reviewer-executed product checks, not a log of steps the runner or LLM took.
- If this coverage PR changes application behavior, open the affected feature locally or in staging and perform the changed workflow end to end as a user.
- If this coverage PR changes only tests, inspect the changed tests to confirm they cover the intended behavior; no product workflow needs to be manually exercised.
EOF2
}

persist_run_log() {
  local log_dir="$REPO_DIR/docs/agent-logs"
  local raw_log_file
  RUN_LOG_GIT_PATH="docs/agent-logs/run-${RUN_LOG_TIMESTAMP}-coverage.txt"
  raw_log_file="$(mktemp)"

  mkdir -p "$log_dir"
  {
    printf 'Daily coverage runner log\n'
    printf 'Timestamp (UTC): %s\n' "$RUN_LOG_TIMESTAMP"
    printf 'Repository: %s\n' "$REPO_SLUG"
    printf 'Coverage target: %s\n' "$COVERAGE_TARGET_PERCENT"
    printf 'Initial coverage: %s\n' "${INITIAL_COVERAGE_PERCENT:-unknown}"
    printf 'Final coverage: %s\n\n' "${FINAL_COVERAGE_PERCENT:-$CURRENT_COVERAGE_PERCENT}"
    cat "$RUN_LOG_TMP_FILE"
  } > "$raw_log_file"
  python3 "$SCRIPT_DIR/sanitize_agent_run_log.py" "$raw_log_file" "$REPO_DIR/$RUN_LOG_GIT_PATH"
  rm -f "$raw_log_file"

  if [[ "$RUN_LOG_RETENTION_COUNT" =~ ^[0-9]+$ ]] && (( RUN_LOG_RETENTION_COUNT > 0 )); then
    local -a logs_to_delete=()
    while IFS= read -r log_path; do
      [[ -n "$log_path" ]] && logs_to_delete+=("$log_path")
    done < <(
      find "$log_dir" -maxdepth 1 -type f -name 'run-*-coverage.txt' \
        | sort -r \
        | tail -n "+$((RUN_LOG_RETENTION_COUNT + 1))"
    )

    if (( ${#logs_to_delete[@]} > 0 )); then
      echo "Pruning old coverage runner logs, keeping newest ${RUN_LOG_RETENTION_COUNT}."
      rm -f "${logs_to_delete[@]}"
    fi
  fi
}

fetch_pr_feedback_json() {
  local pr_number="$1"
  local owner="${REPO_SLUG%%/*}"
  local repo="${REPO_SLUG##*/}"

  gh api graphql \
    -F prNumber="$pr_number" \
    -f query='
      query($prNumber: Int!) {
        repository(owner: "'"$owner"'", name: "'"$repo"'") {
          pullRequest(number: $prNumber) {
            number
            comments(last: 20) {
              nodes {
                author {
                  login
                }
                body
              }
            }
          }
        }
      }
    '
}

fetch_pr_checks_json() {
  local pr_number="$1"
  local checks_json=""
  local checks_status=0

  set +e
  checks_json="$(
    gh pr checks "$pr_number" \
      --repo "$REPO_SLUG" \
      --json bucket,link,name,state,workflow 2>/dev/null
  )"
  checks_status=$?
  set -e

  if (( checks_status != 0 && checks_status != 1 && checks_status != 8 )); then
    return "$checks_status"
  fi

  printf '%s\n' "$checks_json"
}

check_pr_feedback_after_delay() {
  local pr_number="$1"

  if [[ -z "$pr_number" ]]; then
    echo "Post-PR feedback check skipped: PR number unavailable."
    return 0
  fi

  if (( POST_PR_FEEDBACK_DELAY_SECONDS == 0 )); then
    echo "Post-PR feedback check skipped: HUSHLINE_DAILY_POST_PR_FEEDBACK_DELAY_SECONDS=0."
    return 0
  fi

  echo "Waiting ${POST_PR_FEEDBACK_DELAY_SECONDS}s before checking PR #${pr_number} for feedback."
  sleep "$POST_PR_FEEDBACK_DELAY_SECONDS"
  fetch_pr_feedback_json "$pr_number" >/dev/null 2>&1 || true
  fetch_pr_checks_json "$pr_number" >/dev/null 2>&1 || true
}

resolve_pr_number_from_ref() {
  local pr_ref="$1"
  local resolved=""

  if [[ "$pr_ref" =~ /pull/([0-9]+)$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi

  resolved="$(gh pr view "$pr_ref" --repo "$REPO_SLUG" --json number --jq .number 2>/dev/null || true)"
  if [[ "$resolved" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$resolved"
    return 0
  fi

  return 1
}

main() {
  parse_args "$@"
  initialize_run_state
  trap cleanup EXIT

  require_cmd git
  require_cmd gh
  require_cmd codex
  require_cmd docker
  require_cmd make
  require_cmd node
  require_cmd python3

  require_positive_integer "HUSHLINE_COVERAGE_MAX_ATTEMPTS" "$MAX_COVERAGE_ATTEMPTS"
  require_positive_integer "HUSHLINE_COVERAGE_MAX_FIX_ATTEMPTS" "$MAX_FIX_ATTEMPTS"
  require_positive_integer "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS" "$RUNTIME_BOOTSTRAP_ATTEMPTS"
  require_positive_integer "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS" "$RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS"

  if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "Repository not found: $REPO_DIR" >&2
    exit 1
  fi

  cd "$REPO_DIR"

  run_step "Fetch latest from origin" git fetch origin
  run_step "Checkout $BASE_BRANCH" git checkout "$BASE_BRANCH"
  run_step "Reset to origin/$BASE_BRANCH" git reset --hard "origin/$BASE_BRANCH"
  run_step "Remove untracked files" git clean -fd

  local existing_pr_json=""
  local open_human_prs=""
  local open_bot_prs=""

  existing_pr_json="$(find_open_pr_for_head_branch "$BRANCH_NAME")"
  open_human_prs="$(count_open_human_prs)"
  echo "Open human-authored PR count: ${open_human_prs}"
  if [[ "$open_human_prs" != "0" ]]; then
    runner_status "Skipped: found ${open_human_prs} open human-authored PR(s)."
    exit 0
  fi

  open_bot_prs="$(count_open_bot_prs_excluding_heads "$BRANCH_NAME")"
  echo "Open unrelated bot PR count: ${open_bot_prs}; continuing coverage runner."

  run_step "Configure bot git identity" configure_bot_git_identity

  if [[ -n "$existing_pr_json" ]] && remote_branch_exists "$BRANCH_NAME"; then
    run_step "Create branch $BRANCH_NAME from origin/$BRANCH_NAME" git checkout -B "$BRANCH_NAME" "origin/$BRANCH_NAME"
  else
    run_step "Create branch $BRANCH_NAME" git checkout -B "$BRANCH_NAME" "$BASE_BRANCH"
  fi

  run_step "Stop and remove Docker resources" docker compose down -v --remove-orphans
  run_step "Kill all Docker containers" kill_all_docker_containers
  run_step "Kill processes on runner ports" kill_processes_on_ports
  start_runtime_stack_and_seed_dev_data --build

  run_coverage_scan
  INITIAL_COVERAGE_PERCENT="$CURRENT_COVERAGE_PERCENT"
  INITIAL_COVERAGE_MISSING_LINES="$CURRENT_COVERAGE_MISSING_LINES"
  INITIAL_COVERAGE_MISSING_FILES="$CURRENT_COVERAGE_MISSING_FILES"
  FINAL_COVERAGE_PERCENT="$CURRENT_COVERAGE_PERCENT"

  if coverage_target_met; then
    runner_status "Skipped: coverage already meets target at ${CURRENT_COVERAGE_PERCENT}%."
    exit 0
  fi

  build_coverage_prompt "$BRANCH_NAME"
  run_coverage_attempt_loop

  if ! has_non_log_changes; then
    echo "Blocked: no usable non-log changes remain after coverage attempts." >&2
    exit 1
  fi

  persist_run_log

  ensure_worktree_on_branch "$BRANCH_NAME"
  git add -A
  if git diff --cached --quiet; then
    echo "Blocked: no changes staged for coverage run." >&2
    exit 1
  fi

  git commit -m "test: daily coverage runner"

  ensure_head_commit_on_branch "$BRANCH_NAME" "$BASE_BRANCH"
  require_branch_has_unique_commits "origin/$BASE_BRANCH" "$BRANCH_NAME"
  push_branch_for_pr "$BRANCH_NAME"

  write_pr_body "$BRANCH_NAME" "$BASE_BRANCH" "$RUN_LOG_GIT_PATH"

  local pr_title=""
  local pr_url=""
  local pr_number=""
  pr_title="$(build_pr_title)"

  if [[ -n "$existing_pr_json" ]]; then
    pr_number="$(printf '%s\n' "$existing_pr_json" | node -e 'const fs=require("fs"); const data=JSON.parse(fs.readFileSync(0,"utf8")); process.stdout.write(String(data.number || ""));')"
    gh pr edit "$pr_number" \
      --repo "$REPO_SLUG" \
      --base "$BASE_BRANCH" \
      --title "$pr_title" \
      --body-file "$PR_BODY_FILE" >/dev/null
    pr_url="https://github.com/$REPO_SLUG/pull/$pr_number"
    echo "Updated PR: $pr_url"
  else
    pr_url="$(
      gh pr create \
        --repo "$REPO_SLUG" \
        --base "$BASE_BRANCH" \
        --head "$BRANCH_NAME" \
        --title "$pr_title" \
        --body-file "$PR_BODY_FILE"
    )"
    pr_number="$(resolve_pr_number_from_ref "$pr_url" || true)"
    echo "Opened PR: $pr_url"
  fi

  check_pr_feedback_after_delay "$pr_number"

  persist_run_log
  git add "$RUN_LOG_GIT_PATH"
  if ! git diff --cached --quiet; then
    git commit -m "chore: append coverage PR URL to runner log"
    git push origin "$BRANCH_NAME"
  fi

  run_step "Return to $BASE_BRANCH" git checkout "$BASE_BRANCH"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

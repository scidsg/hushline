#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

REPO_DIR="${HUSHLINE_REPO_DIR:-$DEFAULT_REPO_DIR}"
RUNNER_SCRIPT="${HUSHLINE_DEPENDABOT_RUNNER_SCRIPT:-$SCRIPT_DIR/agent_dependabot_pr_runner.sh}"
LOCK_DIR="${HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR:-$REPO_DIR/.tmp/dependabot-pr-runner.lock}"
LOCK_PID_FILE="$LOCK_DIR/pid"

cleanup() {
  rm -rf "$LOCK_DIR"
}

lock_pid_is_active() {
  local pid="$1"

  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

acquire_lock() {
  mkdir -p "$(dirname -- "$LOCK_DIR")"
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_PID_FILE"
    return 0
  fi

  if [[ ! -d "$LOCK_DIR" ]]; then
    echo "Blocked: failed to create queue lock directory: $LOCK_DIR" >&2
    return 1
  fi

  local existing_pid=""
  if [[ -f "$LOCK_PID_FILE" ]]; then
    existing_pid="$(tr -d '[:space:]' < "$LOCK_PID_FILE")"
  fi

  if [[ -n "$existing_pid" ]] && lock_pid_is_active "$existing_pid"; then
    echo "Skipped: Dependabot queue runner already active (pid $existing_pid)."
    return 2
  fi

  echo "Removing stale Dependabot queue lock: $LOCK_DIR"
  rm -rf "$LOCK_DIR"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Blocked: failed to recreate queue lock directory after stale-lock cleanup: $LOCK_DIR" >&2
    return 1
  fi

  printf '%s\n' "$$" > "$LOCK_PID_FILE"
}

main() {
  if [[ ! -x "$RUNNER_SCRIPT" ]]; then
    echo "Blocked: Dependabot runner script is missing or not executable: $RUNNER_SCRIPT" >&2
    return 1
  fi

  local lock_rc=0
  acquire_lock || lock_rc=$?
  if (( lock_rc == 2 )); then
    return 0
  elif (( lock_rc != 0 )); then
    return "$lock_rc"
  fi

  trap cleanup EXIT INT TERM
  "$RUNNER_SCRIPT" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

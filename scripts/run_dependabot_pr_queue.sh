#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

REPO_DIR="${HUSHLINE_REPO_DIR:-$DEFAULT_REPO_DIR}"
RUNNER_SCRIPT="${HUSHLINE_DEPENDABOT_RUNNER_SCRIPT:-$SCRIPT_DIR/agent_dependabot_pr_runner.sh}"
LOCK_DIR="${HUSHLINE_DEPENDABOT_QUEUE_LOCK_DIR:-$REPO_DIR/.tmp/dependabot-pr-runner.lock}"

cleanup() {
  rm -rf "$LOCK_DIR"
}

main() {
  if [[ ! -x "$RUNNER_SCRIPT" ]]; then
    echo "Blocked: Dependabot runner script is missing or not executable: $RUNNER_SCRIPT" >&2
    return 1
  fi

  mkdir -p "$(dirname -- "$LOCK_DIR")"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Skipped: Dependabot queue runner already active."
    return 0
  fi

  trap cleanup EXIT INT TERM
  "$RUNNER_SCRIPT" "$@"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

#!/usr/bin/env bash
set -euo pipefail

MODE="general"

usage() {
  cat <<'EOF'
Usage: scripts/healthcheck.sh [--mode MODE]

Modes:
  general   Default checks used by local automation.
  coverage  Same checks, labeled for coverage runner.
  daily     Same checks, labeled for daily issue runner.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      if [[ -z "$MODE" ]]; then
        echo "Missing value for --mode" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$MODE" in
  general|coverage|daily)
    ;;
  *)
    echo "Unsupported mode: $MODE" >&2
    exit 1
    ;;
esac

GH_ACCOUNT="${HUSHLINE_GH_ACCOUNT:-hushline-dev}"
PLAINTEXT_TOKEN_FILE="${HUSHLINE_GH_TOKEN_FILE:-/Users/scidsg/.config/hushline/gh_token}"
MIN_FREE_GB="${HUSHLINE_HEALTHCHECK_MIN_FREE_GB:-8}"
REQUIRE_KEYCHAIN_TOKEN="${HUSHLINE_HEALTHCHECK_REQUIRE_KEYCHAIN_TOKEN:-1}"
REQUIRE_DOCKER="${HUSHLINE_HEALTHCHECK_REQUIRE_DOCKER:-1}"
REQUIRE_GH="${HUSHLINE_HEALTHCHECK_REQUIRE_GH:-1}"
REQUIRE_FIREWALL="${HUSHLINE_HEALTHCHECK_REQUIRE_FIREWALL:-1}"
REQUIRE_STEALTH="${HUSHLINE_HEALTHCHECK_REQUIRE_STEALTH:-0}"
REQUIRE_WOMP_DISABLED="${HUSHLINE_HEALTHCHECK_REQUIRE_WOMP_DISABLED:-1}"

failures=()

add_failure() {
  failures+=("$1")
}

echo "==> Healthcheck mode: $MODE"

if ! command -v security >/dev/null 2>&1; then
  if [[ "$REQUIRE_KEYCHAIN_TOKEN" == "1" ]]; then
    add_failure "Missing required command: security"
  fi
fi
if [[ "$REQUIRE_DOCKER" == "1" ]] && ! command -v docker >/dev/null 2>&1; then
  add_failure "Missing required command: docker"
fi
if [[ "$REQUIRE_GH" == "1" ]] && ! command -v gh >/dev/null 2>&1; then
  add_failure "Missing required command: gh"
fi

if [[ ${#failures[@]} -eq 0 ]]; then
  if [[ "$REQUIRE_KEYCHAIN_TOKEN" == "1" ]]; then
    if ! security find-internet-password -a "$GH_ACCOUNT" -s github.com -w >/dev/null 2>&1; then
      add_failure "Missing Keychain GitHub token for account '$GH_ACCOUNT' on github.com."
    fi
  fi

  if [[ -f "$PLAINTEXT_TOKEN_FILE" ]]; then
    add_failure "Plaintext GitHub token file exists at '$PLAINTEXT_TOKEN_FILE'."
  fi

  if [[ "$REQUIRE_DOCKER" == "1" ]]; then
    if ! docker info >/dev/null 2>&1; then
      add_failure "Docker daemon is not reachable."
    fi
  fi

  AVAILABLE_KB="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
  if [[ -z "$AVAILABLE_KB" || ! "$AVAILABLE_KB" =~ ^[0-9]+$ ]]; then
    add_failure "Unable to determine free disk space for '$HOME'."
  else
    REQUIRED_KB="$((MIN_FREE_GB * 1024 * 1024))"
    if (( AVAILABLE_KB < REQUIRED_KB )); then
      add_failure "Low free disk space: ${AVAILABLE_KB}KB available, require at least ${REQUIRED_KB}KB (${MIN_FREE_GB}GB)."
    fi
  fi

  if [[ "$REQUIRE_FIREWALL" == "1" ]]; then
    FW_STATE="$(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null || true)"
    if [[ "$FW_STATE" != *"enabled"* ]]; then
      add_failure "macOS firewall is not enabled."
    fi
  fi

  if [[ "$REQUIRE_STEALTH" == "1" ]]; then
    STEALTH_STATE="$(/usr/libexec/ApplicationFirewall/socketfilterfw --getstealthmode 2>/dev/null || true)"
    if [[ "$STEALTH_STATE" != *"on"* ]]; then
      add_failure "macOS firewall stealth mode is not on."
    fi
  fi

  if [[ "$REQUIRE_WOMP_DISABLED" == "1" ]]; then
    WOMP_LINES="$(pmset -g custom | awk '/^[[:space:]]*womp[[:space:]]+/ {print $2}')"
    if [[ -z "$WOMP_LINES" ]]; then
      add_failure "Unable to read pmset womp values."
    elif printf '%s\n' "$WOMP_LINES" | grep -Eqv '^0$'; then
      add_failure "Wake-on-LAN (womp) is enabled; expected all womp values to be 0."
    fi
  fi
fi

if [[ ${#failures[@]} -gt 0 ]]; then
  echo "Healthcheck failed with ${#failures[@]} issue(s):" >&2
  for item in "${failures[@]}"; do
    echo "- $item" >&2
  done
  exit 1
fi

echo "Healthcheck passed."

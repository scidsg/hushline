#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

ensure_docker_running() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Docker is not running; attempting to start it."
  case "$(uname -s)" in
    Darwin)
      open -a Docker >/dev/null 2>&1 || true
      ;;
    *)
      echo "Docker daemon is unavailable. Start Docker and rerun bootstrap." >&2
      return 1
      ;;
  esac

  local timeout_seconds="${HUSHLINE_DOCKER_START_TIMEOUT_SECONDS:-180}"
  if ! [[ "$timeout_seconds" =~ ^[0-9]+$ ]]; then
    echo "Invalid HUSHLINE_DOCKER_START_TIMEOUT_SECONDS: '$timeout_seconds' (expected integer >= 0)." >&2
    return 1
  fi

  local elapsed=0
  until docker info >/dev/null 2>&1; do
    if (( elapsed >= timeout_seconds )); then
      echo "Docker did not become ready within ${timeout_seconds}s." >&2
      return 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
}

ensure_docker_running

docker compose down -v --remove-orphans
docker compose up -d postgres blob-storage
docker compose run --rm dev_data

#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

ensure_docker_running() {
  docker_desktop_app_running() {
    pgrep -f "/Applications/Docker.app/Contents/MacOS/com.docker.backend" >/dev/null 2>&1 \
      || pgrep -f "/Applications/Docker.app/Contents/MacOS/Docker Desktop.app/Contents/MacOS/Docker Desktop" >/dev/null 2>&1
  }

  local docker_probe
  docker_probe="$(docker info --format '{{.ServerVersion}}' 2>&1)" && return 0

  if [[ "$docker_probe" == *"permission denied while trying to connect to the docker API"* ]]; then
    local active_context
    active_context="$(docker context show 2>/dev/null || echo "unknown")"
    if docker_desktop_app_running; then
      echo "Docker Desktop app is running, but this process lacks Docker socket access (context: ${active_context})." >&2
    else
      echo "Docker daemon is reachable but this process lacks socket access (context: ${active_context})." >&2
    fi
    echo "Details: ${docker_probe}" >&2
    echo "Run outside sandboxed/restricted execution or grant Docker socket access, then rerun." >&2
    return 1
  fi

  if [[ "$docker_probe" == *"context"* && "$docker_probe" == *"not found"* ]]; then
    echo "Docker context is invalid. Run 'docker context ls' and select a valid context." >&2
    echo "Details: ${docker_probe}" >&2
    return 1
  fi

  if [[ "$docker_probe" == *"error during connect"* ]] || [[ "$docker_probe" == *"Cannot connect to the Docker daemon"* ]]; then
    :
  else
    echo "Docker check failed before startup attempt." >&2
    echo "Details: ${docker_probe}" >&2
    return 1
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if docker_desktop_app_running; then
    echo "Docker Desktop app is running; waiting for Docker API readiness."
  else
    echo "Docker is not running; attempting to start it."
  fi
  case "$(uname -s)" in
    Darwin)
      if ! docker_desktop_app_running; then
        open -a Docker >/dev/null 2>&1 || true
      fi
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

docker compose build
docker compose down -v --remove-orphans
docker compose up -d postgres blob-storage
docker compose run --rm dev_data

#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

docker compose down -v --remove-orphans
docker compose up -d postgres blob-storage
docker compose run --rm dev_data

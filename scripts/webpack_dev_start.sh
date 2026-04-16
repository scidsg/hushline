#!/bin/sh

set -eu

cd /app

MAX_ATTEMPTS="${WEBPACK_PACKAGE_WAIT_ATTEMPTS:-30}"
SLEEP_SECONDS="${WEBPACK_PACKAGE_WAIT_SECONDS:-1}"

wait_for_file() {
  path="$1"
  attempts=0

  while [ ! -f "$path" ]; do
    attempts=$((attempts + 1))

    if [ "$attempts" -ge "$MAX_ATTEMPTS" ]; then
      echo "webpack startup error: missing $path after $MAX_ATTEMPTS attempts" >&2
      exit 1
    fi

    sleep "$SLEEP_SECONDS"
  done
}

wait_for_file /app/package.json
wait_for_file /app/package-lock.json

mkdir -p /app/node_modules
find /app/node_modules -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
npm_config_update_notifier=false npm ci --no-audit --no-fund
exec npm run build:dev

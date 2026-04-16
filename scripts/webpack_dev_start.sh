#!/bin/sh

set -eu

MAX_ATTEMPTS="${WEBPACK_PACKAGE_WAIT_ATTEMPTS:-30}"
SLEEP_SECONDS="${WEBPACK_PACKAGE_WAIT_SECONDS:-1}"
DEPENDENCY_ROOT="${WEBPACK_DEPENDENCY_ROOT:-/workspace-webpack}"
NODE_MODULES_PATH="${WEBPACK_NODE_MODULES_PATH:-$DEPENDENCY_ROOT/node_modules}"

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

mkdir -p "$DEPENDENCY_ROOT"
cp /app/package.json /app/package-lock.json "$DEPENDENCY_ROOT"/

cd "$DEPENDENCY_ROOT"
npm_config_update_notifier=false npm ci --no-audit --no-fund

cd /app
export PATH="$NODE_MODULES_PATH/.bin:$PATH"
export WEBPACK_NODE_MODULES_PATH="$NODE_MODULES_PATH"
exec webpack --config webpack.config.js --watch --env WEBPACK_WATCH=1

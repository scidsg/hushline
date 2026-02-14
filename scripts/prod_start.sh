#!/bin/bash

# Run migrations
echo "> Running migrations"
poetry run flask db upgrade

# Configure Stripe and tiers
if [ -n "$STRIPE_SECRET_KEY" ]; then
  echo "> Configuring Stripe"
  poetry run flask stripe configure
else
  echo "STRIPE_SECRET_KEY is not set. Skipping Stripe configuration."
fi

# Start the server
echo "> Starting the server"
DEFAULT_GUNICORN_CONFIG_PATH="/etc/hushline/gunicorn.conf.py"
GUNICORN_CONFIG_PATH="${GUNICORN_CONFIG_PATH:-$DEFAULT_GUNICORN_CONFIG_PATH}"
FLASK_APP_START="${FLASK_APP_START:-hushline:create_app()}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}"
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8080}"

DEFAULT_GUNICORN_ARGS=(--workers "$GUNICORN_WORKERS" --bind "$GUNICORN_BIND" --capture-output)
GUNICORN_EXTRA_ARGS=()
if [ -n "${GUNICORN_ARGS:-}" ]; then
  read -r -a GUNICORN_EXTRA_ARGS <<< "$GUNICORN_ARGS"
fi

if [ -n "$GUNICORN_CONFIG_PATH" ] && [ -f "$GUNICORN_CONFIG_PATH" ]; then
  echo "Loading gunicorn config from $GUNICORN_CONFIG_PATH"
  exec poetry run gunicorn --config "file:$GUNICORN_CONFIG_PATH" "${GUNICORN_EXTRA_ARGS[@]}" "$FLASK_APP_START"
fi

echo "Gunicorn config $GUNICORN_CONFIG_PATH not found. Using default args."
exec poetry run gunicorn "${DEFAULT_GUNICORN_ARGS[@]}" "${GUNICORN_EXTRA_ARGS[@]}" "$FLASK_APP_START"

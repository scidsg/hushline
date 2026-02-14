#!/bin/bash

# Run migrations (optional for sidecar deploys)
if [ "${RUN_STARTUP_MIGRATIONS:-true}" = "true" ]; then
  echo "> Running migrations"
  poetry run flask db upgrade
else
  echo "> Skipping migrations (RUN_STARTUP_MIGRATIONS=false)"
fi

# Configure Stripe and tiers
if [ -n "$STRIPE_SECRET_KEY" ]; then
  echo "> Configuring Stripe"
  poetry run flask stripe configure
else
  echo "STRIPE_SECRET_KEY is not set. Skipping Stripe configuration."
fi

# Start the server
echo "> Starting the server"
poetry run gunicorn "hushline:create_app()" -b 0.0.0.0:8080

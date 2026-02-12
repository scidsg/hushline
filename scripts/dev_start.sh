#!/bin/bash

# Ensure tables exist before any startup tasks that read DB state.
# In docker compose we may run migrations via `dev_data`; allow disabling startup migration there.
if [ "${RUN_STARTUP_MIGRATIONS:-true}" = "true" ]; then
  poetry run ./scripts/dev_migrations.py
fi

# Configure Stripe products/tiers only when Stripe is configured.
if [ -n "${STRIPE_SECRET_KEY:-}" ]; then
  poetry run flask stripe configure
fi

# Start the server
poetry run flask run --debug --host=0.0.0.0 --port=8080 --with-threads
